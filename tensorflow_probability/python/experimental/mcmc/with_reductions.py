# Copyright 2020 The TensorFlow Probability Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""WithReductions Transition Kernel."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import collections

import tensorflow.compat.v2 as tf

from tensorflow_probability.python.mcmc import kernel as kernel_base
from tensorflow_probability.python.mcmc.internal import util as mcmc_util
# Direct import for map_structure_up_to
from tensorflow.python.util import nest  # pylint: disable=g-direct-tensorflow-import


__all__ = [
    'WithReductions',
]


class WithReductionsKernelResults(
    mcmc_util.PrettyNamedTupleMixin,
    collections.namedtuple('WithReductionsKernelResults',
                           ['streaming_calculations',
                            'inner_results'])):
  """Reducer state and diagnostics for `WithReductions`."""
  __slots__ = ()


class WithReductions(kernel_base.TransitionKernel):
  """Applies `Reducer`s to stream over MCMC samples.

  `WithReductions` augments an inner MCMC kernel with
  side-computations that can read the stream of samples as they
  are generated.  This is relevant for streaming uses of MCMC,
  where materializing the entire Markov chain history is undesirable,
  e.g. due to memory limits.

  One `WithReductions` instance can attach an arbitrary collection
  of side-computations, each of which must be packaged as a
  `Reducer`.  `WithReductions` operates by generating a
  sample with its `inner_kernel`'s `one_step`, then invoking each
  `Reducer`'s `one_step` method on that sample. The updated reducer
  states are stored in the `streaming_calculations` field of
  `WithReductions`' kernel results.
  """

  def __init__(self, inner_kernel, reducers, name=None):
    """Instantiates this object.

    Args:
      inner_kernel: `TransitionKernel` whose `one_step` will generate
        MCMC sample(s).
      reducers: A (possibly nested) structure of `Reducer`s to be evaluated
        on the `inner_kernel`'s samples.
      name: Python `str` name prefixed to Ops created by this function.
        Default value: `None` (i.e., "reduced_kernel").
    """
    self._parameters = dict(
        inner_kernel=inner_kernel,
        reducers=reducers,
        name=name or 'reduced_kernel'
    )

  def one_step(
      self, current_state, previous_kernel_results, seed=None
  ):
    """Updates all `Reducer`s with a new sample from the `inner_kernel`.

    Args:
      current_state: `Tensor` or Python `list` of `Tensor`s
        representing the current state(s) of the Markov chain(s),
      previous_kernel_results: `WithReductionsKernelResults` named tuple.
        `WithReductionsKernelResults` contain the state of
        `streaming_calculations` and a reference to kernel results of
        nested `TransitionKernel`s.
      seed: Optional seed for reproducible sampling.

    Returns:
      new_state: Newest MCMC state drawn from the `inner_kernel`.
      kernel_results: `WithReductionsKernelResults` representing updated
        kernel results. Reducer states are stored in the
        `streaming_calculations` field. The state structure is identical
        to `self.reducers`.
    """
    with tf.name_scope(
        mcmc_util.make_name(self.name, 'with_reductions', 'one_step')):
      new_state, inner_kernel_results = self.inner_kernel.one_step(
          current_state, previous_kernel_results.inner_results, seed=seed)
      def step_reducer(r, state):
        return r.one_step(
            new_state,
            state,
            previous_kernel_results=inner_kernel_results)
      new_reducers_state = nest.map_structure_up_to(
          self.reducers,
          step_reducer,
          self.reducers, previous_kernel_results.streaming_calculations,
          check_types=False)
      kernel_results = WithReductionsKernelResults(
          new_reducers_state, inner_kernel_results)
      return new_state, kernel_results

  def bootstrap_results(self, init_state):
    """Instantiates reducer states with identical structure to the `init_state`.

    Args:
      init_state: `Tensor` or Python `list` of `Tensor`s representing the
        state(s) of the Markov chain(s). For consistency across sampling
        procedures (i.e. `tfp.mcmc.sample_chain` follows similar semantics),
        the initial state does not count as a "sample". Hence, all reducer
        states will reflect empty streams.

    Returns:
      kernel_results: `WithReductionsKernelResults` representing updated
        kernel results. Reducer states are stored in the
        `streaming_calculations` field. The state structure is identical
        to `self.reducers`.
    """
    with tf.name_scope(
        mcmc_util.make_name(self.name, 'with_reductions', 'bootstrap_results')):
      inner_kernel_results = self.inner_kernel.bootstrap_results(init_state)
      return WithReductionsKernelResults(
          tf.nest.map_structure(
              lambda r: r.initialize(init_state, inner_kernel_results),
              self.reducers),
          inner_kernel_results)

  @property
  def is_calibrated(self):
    return self.inner_kernel.is_calibrated

  @property
  def parameters(self):
    return self._parameters

  @property
  def inner_kernel(self):
    return self._parameters['inner_kernel']

  @property
  def reducers(self):
    return self._parameters['reducers']

  @property
  def name(self):
    return self._parameters['name']