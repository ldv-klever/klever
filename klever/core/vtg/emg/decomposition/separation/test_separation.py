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

from klever.core.vtg.emg.decomposition.separation import SeparationStrategy
from klever.core.vtg.emg.common.process.model_for_testing import model_preset
from klever.core.vtg.emg.decomposition.separation.linear import LinearStrategy
from klever.core.vtg.emg.common.process.actions import Subprocess, Choice, Receive


@pytest.fixture
def model():
    return model_preset()


@pytest.fixture
def default_separator():
    return SeparationStrategy(logging.Logger('default'), dict())


@pytest.fixture
def linear_separator():
    return LinearStrategy(logging.Logger('default'), dict())


def test_default_scenario_extraction(model, default_separator):
    c1p1 = model.environment['c1/p1']
    c1p2 = model.environment['c1/p2']
    c2p1 = model.environment['c2/p1']

    s1 = default_separator(c1p1)
    assert len(s1) == 2
    _compare_scenario_with_actions(s1, c1p1.actions)
    assert len([s for s in s1 if s.savepoint]) == 2

    s2 = default_separator(c1p2)
    assert len(s2) == 2
    _compare_scenario_with_actions(s2, c1p2.actions)
    assert len([s for s in s2 if s.savepoint]) == 2

    s3 = default_separator(c2p1)
    assert len(s3) == 0


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


def test_linear_strategy_c1p1(model, linear_separator):
    c1p1 = model.environment['c1/p1']
    scenarios = linear_separator(c1p1)
    _check_linear_actions(scenarios, c1p1.actions)

    # Test the number of scenarios
    # 4 - savepoints  + 1 option without savepoints
    assert len(scenarios) == 5, f'The number of scenarios is {len(scenarios)}: ' + \
                                ', '.join([s.name for s in scenarios])

    scenarios = {s.name: s for s in scenarios}
    assert 'deregister_c1p1' in scenarios
    assert scenarios['deregister_c1p1'].actions.sequence == \
           '(!register_c1p1).[register_c1p2].[deregister_c1p2].(deregister_c1p1)'
    assert 'p1s1_deregister_c1p1' in scenarios
    assert scenarios['p1s1_deregister_c1p1'].actions.sequence == \
           '<p1s1>.[register_c1p2].[deregister_c1p2].(deregister_c1p1)'
    assert 'p1s2_deregister_c1p1' in scenarios
    assert scenarios['p1s1_deregister_c1p1'].actions.sequence == \
           '<p1s2>.[register_c1p2].[deregister_c1p2].(deregister_c1p1)'
    assert 'p1s3_deregister_c1p1' in scenarios
    assert scenarios['p1s1_deregister_c1p1'].actions.sequence == \
           '<p1s3>.[register_c1p2].[deregister_c1p2].(deregister_c1p1)'
    assert 'p1s4_deregister_c1p1' in scenarios
    assert scenarios['p1s1_deregister_c1p1'].actions.sequence == \
           '<p1s4>.[register_c1p2].[deregister_c1p2].(deregister_c1p1)'


def test_linear_strategy_c1p2(model, linear_separator):
    c1p2 = model.environment['c1/p2']
    scenarios = linear_separator(c1p2)
    _check_linear_actions(scenarios, c1p2.actions)

    # Test the number of scenarios
    # 3 scenarios + 2 sp * 3 scenarios
    assert len(scenarios) == 9, f'The number of scenarios is {len(scenarios)}: ' + \
                                ', '.join([s.name for s in scenarios])

    scenarios = {s.name: s for s in scenarios}
    assert 'success_read_deregister_c1p2' in scenarios
    assert scenarios['success_read_deregister_c1p2'].actions.sequence == \
           '(!register_c1p2).<alloc>.<probe>.<success>.<read>.<remove>.(deregister_c1p2)'
    assert 'success_write_deregister_c1p2' in scenarios
    assert scenarios['success_write_deregister_c1p2'].actions.sequence == \
           '(!register_c1p2).<alloc>.<probe>.<success>.<read>.<remove>.(deregister_c1p2)'
    assert 'fail_deregister_c1p2' in scenarios
    assert scenarios['fail_deregister_c1p2'].actions.sequence == \
           '(!register_c1p2).<alloc>.<probe>.<fail>.(deregister_c1p2)'

    assert 'p2s1_success_read_deregister_c1p2' in scenarios
    assert scenarios['p2s1_success_read_deregister_c1p2'].actions.sequence == \
           '<p2s1>.<alloc>.<probe>.<success>.<read>.<remove>.(deregister_c1p2)'
    assert 'p2s1_success_write_deregister_c1p2' in scenarios
    assert scenarios['p2s1_success_write_deregister_c1p2'].actions.sequence == \
           '<p2s1>.<alloc>.<probe>.<success>.<read>.<remove>.(deregister_c1p2)'
    assert 'p2s1_fail_deregister_c1p2' in scenarios
    assert scenarios['p2s1_fail_deregister_c1p2'].actions.sequence == \
           '<p2s1>.<alloc>.<probe>.<fail>.(deregister_c1p2)'

    assert 'p2s2_success_read_deregister_c1p2' in scenarios
    assert scenarios['p2s2_success_read_deregister_c1p2'].actions.sequence == \
           '<p2s2>.<alloc>.<probe>.<success>.<read>.<remove>.(deregister_c1p2)'
    assert 'p2s2_success_write_deregister_c1p2' in scenarios
    assert scenarios['p2s2_success_write_deregister_c1p2'].actions.sequence == \
           '<p2s2>.<alloc>.<probe>.<success>.<read>.<remove>.(deregister_c1p2)'
    assert 'p2s2_fail_deregister_c1p2' in scenarios
    assert scenarios['p2s2_fail_deregister_c1p2'].actions.sequence == \
           '<p2s2>.<alloc>.<probe>.<fail>.(deregister_c1p2)'


def test_linear_strategy_c2p1(model, linear_separator):
    c2p1 = model.environment['c2/p1']
    scenarios = linear_separator(c2p1)
    _check_linear_actions(scenarios, c2p1.actions)

    # Test the number of scenarios
    # 3 options without sp
    # Todo: reimplement this. It is better to cover sequences somehow.
    assert len(scenarios) == 3, f'The number of scenarios is {len(scenarios)}: ' + \
                                ', '.join([s.name for s in scenarios])


def _check_linear_actions(scenarios, actions):
    # Savepoints are covered
    first_actions = actions.first_actions()
    savepoints = {str(s) for a in actions for s in actions[a].savepoints}
    covered = {str(s.savepoint) for s in scenarios if s.savepoint}
    assert savepoints == covered, "Covered: {}; All: {}".format(', '.join(savepoints), ', '.join(covered))

    # All actions are covered
    covered_actions = dict()
    for scenario in scenarios:
        for name in scenario.actions:
            covered_actions.setdefault(name, 0)
            behs = len(scenario.actions.behaviour(name))
            covered_actions[name] += behs

    for name in (name for name in actions if not isinstance(actions[name], Subprocess)):
        real_behs = len(actions.behaviour(name))
        assert name in covered_actions, f'Action {name} is not covered at all'
        assert real_behs <= covered_actions[name], f'Some entries of {name} are not covered ({real_behs}):' \
                                                   f' {covered_actions[name]}'

    # No Choices in paths
    for scenario in scenarios:
        for beh in scenario.actions.behaviour():
            if isinstance(beh, Choice):
                assert False, f'Do not expect choice in the scenario: {repr(beh)}'

    # Have registration or savepoint
    registrations = {a.name for a in actions.filter(include={Receive})}.intersection(first_actions)
    assert len(registrations) == 1, f'The process should have a single registration instead of:' \
                                    f' {", ".join(registrations)}'
    registration = registrations.pop()
    for scenario in scenarios:
        assert scenario.savepoint or registration in scenario.actions.first_actions()
