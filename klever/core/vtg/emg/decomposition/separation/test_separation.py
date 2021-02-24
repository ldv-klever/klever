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
import logging

from klever.core.vtg.emg.common.process.actions import Subprocess
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy
from klever.core.vtg.emg.common.process.model_for_testing import model_preset
from klever.core.vtg.emg.decomposition.separation.linear import LinearStrategy


@pytest.fixture
def model():
    return model_preset()


@pytest.fixture
def default_separator():
    return SeparationStrategy(logging, dict())


def test_default_scenario_extraction(model, default_separator):
    c1p1 = model.environment['c1/p1']
    c1p2 = model.environment['c1/p2']
    c2p1 = model.environment['c2/p1']

    e1 = default_separator(c1p1)
    s1 = e1()
    assert len(s1) == 2
    _compare_scenario_with_actions(s1, c1p1.actions)

    e2 = default_separator(c1p2)
    s2 = e2()
    assert len(s2) == 2
    _compare_scenario_with_actions(s2, c1p2.actions)

    e3 = default_separator(c2p1)
    s3 = e3()
    assert len(s3) == 1
    _compare_scenario_with_actions(s3, c2p1.actions)


def _compare_scenario_with_actions(scenarios, actions):
    first_actions = actions.first_actions()
    savepoints = [s for a in first_actions for s in actions[a].savepoints]

    for s in scenarios:
        assert not savepoints or s.savepoint in savepoints
        assert s.initial_action

        assert repr(s.initial_action) == repr(actions.initial_action)
        for subp in actions.filter(include={Subprocess}):
            assert repr(s.actions[subp.name].action) == repr(actions[subp.name].action)
        for name in actions:
            assert s.actions[name]
            assert len(actions.behaviour(name)) == len(s.actions.behaviour(name)), \
                "{} and {}".format('\n'.join(map(repr, actions.behaviour(name))),
                                   '\n'.join(map(repr, s.actions.behaviour(name))))
