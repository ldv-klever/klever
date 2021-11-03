#
# Copyright (c) 2021 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
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
#

import pytest
import logging

from klever.core.vtg.emg.decomposition.modelfactory import ModelFactory
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy
from klever.core.vtg.emg.common.process.model_for_testing import model_preset

# todo: Implement models for combinatorial strategy


@pytest.fixture
def model():
    return model_preset()


def test_default_models(model):
    separation = ModelFactory(logging.Logger('default'), {})
    scenario_generator = SeparationStrategy(logging.Logger('default'), dict())
    processes_to_scenarios = {str(process): list(scenario_generator(process, model))
                              for process in model.environment.values()}
    models = list(separation(processes_to_scenarios, model))

    cnt = 1  # Original model
    for process in model.environment.values():
        for action_name in process.actions.first_actions():
            action = process.actions[action_name]
            cnt += len(action.savepoints) if hasattr(action, 'savepoints') and action.savepoints else 0
    assert len(models) == cnt

    # Compare processes itself
    for new_model in models:
        assert len(list(new_model.models.keys())) > 0
        assert len(list(new_model.environment.keys())) > 0

        for name, process in model.environment.items():
            if name in new_model.environment:
                for label in process.labels:
                    # Check labels
                    assert label in new_model.environment[name].labels, f'Missing label {label}'

                assert new_model.environment[name].actions
            elif new_model.name in process.actions.savepoints:
                for label in process.labels:
                    # Check labels
                    assert label in new_model.entry.labels, f'Missing label {label}'

                assert new_model.entry.actions
