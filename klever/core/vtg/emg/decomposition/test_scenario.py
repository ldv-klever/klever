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

from klever.core.vtg.emg.decomposition.scenario import Scenario
from klever.core.vtg.emg.common.process.actions import Concatenation
from klever.core.vtg.emg.common.process.model_for_testing import model_preset


@pytest.fixture
def model():
    return model_preset()


def test_set_initial_action(model):
    c1p1 = model.environment['c1/p1']
    b1 = c1p1.actions.initial_action

    scenario = Scenario(c1p1)
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

    inst1 = Scenario(c1p2)
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
