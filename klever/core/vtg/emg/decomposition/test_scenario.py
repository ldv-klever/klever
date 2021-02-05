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

from klever.core.vtg.emg.decomposition.scenario import Scenario, ScenarioExtractor
from klever.core.vtg.emg.common.process import Action, Actions, Block, Concatenation, Choice, Parentheses


def test_set_initial_action():
    test1 = Action('test1')
    test2 = Action('test2')
    test3 = Action('test3')

    scenario = Scenario()

    scenario.set_initial_action(test1)
    assert scenario.actions.initial_action == test1, 'Initial action was not set'
    assert not (scenario.actions.initial_action is test2), 'Initial action does not differ from another object'

    try:
        scenario.set_initial_action(test3)
    except ValueError:
        pass
    else:
        assert False, "Expect ValueError"


def test_add_action_copy():
    test1, test2 = Block('block1'), Block('block2')

    operator1 = Parentheses('1')
    inst1 = Scenario()
    inst1.set_initial_action(operator1)
    ret = inst1.add_action_copy(test1, operator1)
    assert ret == test1 and ret is not test1, 'Copy is not successful'
    try:
        inst1.add_action_copy(test2, operator1)
    except AssertionError:
        pass
    else:
        assert False, 'It is imposible to add two actions to Parentheses'

    for operator2 in (Choice('2'), Concatenation('3')):
        inst1 = Scenario()
        inst1.set_initial_action(operator2)
        ret1 = inst1.add_action_copy(test1, operator2)
        assert ret1 == test1 and ret1 is not test1, 'Copy is not successful'

        ret2 = inst1.add_action_copy(test2, operator2)
        assert ret2 == test2 and ret2 is not test2 and ret2 is not test1, 'Copy is not successful'



def test_hashing():
    pass


def test_scenario_extraction():
    pass
