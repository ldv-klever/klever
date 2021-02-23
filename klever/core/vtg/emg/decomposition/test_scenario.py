#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

from klever.core.vtg.emg.common.process.model_for_testing import model_preset
from klever.core.vtg.emg.decomposition.scenario import Scenario, ScenarioExtractor
from klever.core.vtg.emg.common.process.actions import Concatenation, Subprocess


@pytest.fixture
def model():
    return model_preset()


def test_set_initial_action(model):
    c1p1 = model.environment['c1/p1']
    b1 = c1p1.actions.initial_action

    scenario = Scenario()
    assert scenario.initial_action is None
    scenario.initial_action = b1
    assert scenario.initial_action is not None, repr(scenario.initial_action)
    assert scenario.initial_action is not b1
    assert scenario.actions.initial_action is not None
    assert scenario.actions.initial_action is scenario.initial_action


def test_add_action_copy(model):
    c1p2 = model.environment['c1/p2']
    b1 = c1p2.actions.behaviour('read').pop()
    b2 = c1p2.actions.behaviour('write').pop()
    op = Concatenation()

    inst1 = Scenario()
    inst1.initial_action = op
    op = inst1.initial_action
    c1 = inst1.add_action_copy(b1, op)
    c2 = inst1.add_action_copy(b2, op)

    assert c1 is not b1
    assert c2 is not b2
    assert c1.my_operator is op
    assert c2.my_operator is op
    assert op[0] is c1
    assert op[1] is c2


def test_scenario_extraction(model):
    c1p1 = model.environment['c1/p1']
    c1p2 = model.environment['c1/p2']
    c2p1 = model.environment['c2/p1']

    e1 = ScenarioExtractor(c1p1.actions)
    s1 = e1()
    assert len(s1) == 2
    _compare_scenario_with_actions(s1, c1p1.actions)

    e2 = ScenarioExtractor(c1p2.actions)
    s2 = e2()
    assert len(s2) == 2
    _compare_scenario_with_actions(s2, c1p2.actions)

    e3 = ScenarioExtractor(c2p1.actions)
    s3 = e3()
    assert len(s3) == 1
    _compare_scenario_with_actions(s3, c2p1.actions)


def _compare_scenario_with_actions(scenarios, actions):
    for s in scenarios:
        assert s.savepoint
        assert s.initial_action

        assert repr(s.initial_action) == repr(actions.initial_action)
        for subp in actions.filter(include={Subprocess}):
            assert repr(s.actions[subp.name].action) == repr(actions[subp.name].action)
        for name in actions:
            assert s.actions[name]
            assert len(actions.behaviour(name)) == len(s.actions.behaviour(name)), \
                "{} and {}".format('\n'.join(map(repr, actions.behaviour(name))),
                                   '\n'.join(map(repr, s.actions.behaviour(name))))
