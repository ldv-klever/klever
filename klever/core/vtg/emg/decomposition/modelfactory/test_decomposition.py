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
from klever.core.vtg.emg.decomposition.separation.reqs import ReqsStrategy
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy
from klever.core.vtg.emg.decomposition.separation.linear import LinearStrategy
from klever.core.vtg.emg.decomposition.modelfactory.combinatorial import CombinatorialFactory
from klever.core.vtg.emg.common.process.model_for_testing import model_preset


@pytest.fixture
def model():
    return model_preset()

def _obtain_model(logger, model, specification):
    separation = CombinatorialFactory(logger, specification)
    scenario_generator = SeparationStrategy(logger, dict())
    processes_to_scenarios = {str(process): list(scenario_generator(process, model))
                              for process in model.environment.values()}
    return processes_to_scenarios, list(separation(processes_to_scenarios, model))


def _obtain_linear_model(logger, model, specification, separate_dispatches=False):
    separation = CombinatorialFactory(logger, specification)
    scenario_generator = LinearStrategy(logger, dict() if not separate_dispatches else
    {'add scenarios without dispatches': True})
    processes_to_scenarios = {str(process): list(scenario_generator(process, model))
                              for process in model.environment.values()}
    return processes_to_scenarios, list(separation(processes_to_scenarios, model))


def _obtain_reqs_model(logger, model, specification, separate_dispatches=False):
    separation = ReqsStrategy(logger, specification)
    scenario_generator = ReqsStrategy(logger, dict() if not separate_dispatches else
    {'add scenarios without dispatches': True})
    processes_to_scenarios = {str(process): list(scenario_generator(process, model))
                              for process in model.environment.values()}
    return processes_to_scenarios, list(separation(processes_to_scenarios, model))


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

def test_inclusion_p1(logger, model):
    spec = {
        "must contain": {"c/p1": {}},
        "cover scenarios": {"c/p1": {}}
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, model, spec)

    # Cover all scenarios from c2p1
    p1scenarios = processes_to_scenarios['c/p1']
    assert len(p1scenarios) == len(models)
    actions = [m.environment['c/p1'].actions for m in models if 'c/p1' in m.environment] + \
              [m.entry.actions for m in models]
    for scenario in p1scenarios:
        assert scenario.actions in actions

    # No savepoints from c2p2
    c2p2_withsavepoint = [s for s in processes_to_scenarios['c/p2'] if s.savepoint].pop()
    for model in models:
        if model.entry.actions == c2p2_withsavepoint.actions:
            assert False, f"Model {model.attributed_name} has a savepoint from p2"


def test_deletion(logger, model):
    spec = {
        "must not contain": {"c/p2": {}},
        "cover scenarios": {"c/p1": {}}
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, model, spec)

    # Cover all scenarios from p1
    p1scenarios = {s for s in processes_to_scenarios['c/p1']}
    assert len(p1scenarios) == len(models)
    actions = [m.environment['c/p1'].actions for m in models if 'c/p1' in m.environment] + \
              [m.entry.actions for m in models]
    for scenario in p1scenarios:
        assert scenario.actions in actions

    # No savepoints from p2
    p2_withsavepoint = [s for s in processes_to_scenarios['c/p2'] if s.savepoint].pop()
    assert all([True if p2_withsavepoint.actions != m.entry.actions else False for m in models])

    # No other actions
    for model in models:
        assert 'c/p2' not in model.environment


# todo: Test with only savepoints option
# todo: Move the last tests from the selective dir
