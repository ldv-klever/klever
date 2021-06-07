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
from klever.core.vtg.emg.decomposition.separation.linear import LinearStrategy
from klever.core.vtg.emg.common.process.model_for_testing import model_preset_c2
from klever.core.vtg.emg.decomposition.modelfactory.selective import SelectiveFactory


@pytest.fixture
def model():
    return model_preset_c2()


def test_inclusion_p2(model):
    spec = {
        "must contain": {"c2/p2": {}},
        "cover scenarios": {"c2/p2": {}}
    }
    processes_to_scenarios, models = _obtain_models(model, spec)

    # Cover all c2p2 scenarios
    p2scenarios = processes_to_scenarios['c2/p2']
    assert len(p2scenarios) == len(models)
    actions = [m.environment['c2/p2'].actions for m in models if 'c2/p2' in m.environment] +\
              [m.entry.actions for m in models]
    for scenario in p2scenarios:
        assert scenario.actions in actions


def test_inclusion_p1(model):
    spec = {
        "must contain": {"c2/p1": {}},
        "cover scenarios": {"c2/p1": {}}
    }
    processes_to_scenarios, models = _obtain_models(model, spec)

    # Cover all scenarios from c2p1
    p1scenarios = processes_to_scenarios['c2/p1']
    assert len(p1scenarios) == len(models)
    actions = [m.environment['c2/p1'].actions for m in models if 'c2/p1' in m.environment] + \
              [m.entry.actions for m in models]
    for scenario in p1scenarios:
        assert scenario.actions in actions

    # No savepoints from c2p2
    c2p2_withsavepoint = [s for s in processes_to_scenarios['c2/p2'] if s.savepoint].pop()
    assert all([True if c2p2_withsavepoint.actions != m.entry.actions else False for m in models])


def test_deletion(model):
    spec = {
        "must not contain": {"c2/p2": {}},
        "cover scenarios": {"c2/p1": {}}
    }
    processes_to_scenarios, models = _obtain_models(model, spec)

    # Cover all scenarios from c2p1
    p1scenarios = processes_to_scenarios['c2/p1']
    assert len(p1scenarios) == len(models)
    actions = [m.environment['c2/p1'].actions for m in models] + [m.entry.actions for m in models]
    for scenario in p1scenarios:
        assert scenario.actions in actions

    # No savepoints from c2p2
    c2p2_withsavepoint = [s for s in processes_to_scenarios['c2/p2'] if s.savepoint].pop()
    assert all([True if c2p2_withsavepoint.actions != m.entry.actions else False for m in models])

    # No other actions
    for model in models:
        assert 'c2/p2' not in model.environment


def test_complex_restrictions(model):
    spec = {
        "must contain": {"c2/p2": {"actions": [["read"]]}},
        "must not contain": {"c2/p1": {"savepoints": [["c2p1s1"]]}},
        "cover scenarios": {"c2/p2": {}}
    }
    processes_to_scenarios, models = _obtain_models(model, spec)

    # Cover only scenarios with read from p2
    assert len(models) == len([s for s in processes_to_scenarios['c2/p2'] if 'write' not in s.actions])
    actions = [m.environment['c2/p2'].actions for m in models] + [m.entry.actions for m in models]
    for model_actions in actions:
        assert 'write' not in model_actions
        assert 'read' in model_actions

    # No scenarios with a savepoint c2p1s1
    c2p1_withsavepoint = [s for s in processes_to_scenarios['c2/p1'] if s.savepoint].pop()
    assert all([True if c2p1_withsavepoint.actions != m.entry.actions else False for m in models])


def test_contraversal_conditions(model):
    spec = {
        "must contain": {"c2/p2": {}},
        "must not contain": {"c2/p1": {}},
        "cover scenarios": {"c2/p1": {}}
    }
    # TODO: Implement assertions, expect an exception ValueError
    raise NotImplementedError


def test_complex_exclusion(model):
    spec = {
        "must contain": {"c2/p1": {}},
        "must not contain": {"c2/p1": {"actions": [["probe", "success"]]}},
        "cover scenarios": {"c2/p1": {}}
    }
    # TODO: Implement assertions, expect p2p1 with failed probe
    raise NotImplementedError


def _obtain_models(model, specification):
    separation = SelectiveFactory(logging.Logger('default'), specification)
    scenario_generator = LinearStrategy(logging.Logger('default'), dict())
    processes_to_scenarios = {str(process): list(scenario_generator(process)) for process in model.environment.values()}
    return processes_to_scenarios, list(separation(processes_to_scenarios, model))
