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

import json
import pytest
import logging

from klever.core.vtg.emg.common.process import ProcessCollection
from klever.core.vtg.emg.decomposition.separation.reqs import ReqsStrategy
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy
from klever.core.vtg.emg.decomposition.separation.linear import LinearStrategy
from klever.core.vtg.emg.common.process.serialization import CollectionDecoder
from klever.core.vtg.emg.common.process.actions import Subprocess, Choice, Receive, Block
from klever.core.vtg.emg.common.process.model_for_testing import model_preset, source_preset


@pytest.fixture
def model():
    return model_preset()


@pytest.fixture
def default_separator():
    return SeparationStrategy(logging.Logger('default'), dict())


@pytest.fixture
def linear_separator():
    return LinearStrategy(logging.Logger('default'), dict())


@pytest.fixture
def requirements_driven_separator():
    return ReqsStrategy(logging.Logger('default'), dict())


@pytest.fixture()
def specific_model():
    c1p1 = {
        "comment": "Category 1, process 1.",
        "process": "(!register_c1p1).(deregister_c1p1)",
        "actions": {
            "register_c1p1": {"parameters": []},
            "deregister_c1p1": {"parameters": []}
        }
    }
    c1p2 = {
        "comment": "Category 1, process 2.",
        "process": "(!register_c1p1).{level_one}",
        "actions": {
            "level_one": {"process": "<a>.({level_two} | {level_three}) | {finish}", "comment": ""},
            "level_two": {"process": "(<b> | <c>).{finish}", "comment": ""},
            "level_three": {"process": "<d>.{finish}", "comment": ""},
            "finish": {"process": "(deregister_c1p1)"},
            "register_c1p1": {"parameters": []},
            "deregister_c1p1": {"parameters": []},
            "a": {"comment": "", "statements": [], "condition": []},
            "b": {"comment": "", "statements": [], "condition": []},
            "c": {"comment": "", "statements": [], "condition": []},
            "d": {"comment": "", "statements": [], "condition": []}
        }
    }
    c2p1 = {
        "comment": "Category 2, process 1.",
        "process": "(!register_c2p1).{level_one}",
        "actions": {
            "level_one": {"process": "<a>.<b>"},
            "register_c2p1": {"parameters": []},
            "a": {"comment": "", "statements": [], "condition": []},
            "b": {"comment": "", "statements": [], "condition": []}
        }
    }
    spec = {
        "name": 'test_model',
        "functions models": {},
        "environment processes": {
            "c1/p1": c1p1,
            "c1/p2": c1p2,
            "c2/p1": c2p1
        }
    }
    collection = CollectionDecoder(logging, dict()).parse_event_specification(source_preset(),
                                                                              json.loads(json.dumps(spec)),
                                                                              ProcessCollection())
    return collection


@pytest.fixture()
def model_with_savepoint_requirements():
    c1p1 = {
        "comment": "",
        "process": "(!register).({x} | <a>).{y}",
        "actions": {
            "x": {
                "comment": "",
                "process": "<b>.(<c> | <d>).{y}"
            },
            "y": {
                "comment": "",
                "process": "<e>.<f> | <g>"
            },
            "a": {"comment": "", "statements": []},
            "b": {"comment": "", "statements": []},
            "c": {"comment": "", "statements": []},
            "d": {"comment": "", "statements": []},
            "e": {"comment": "", "statements": []},
            "f": {"comment": "", "statements": []},
            "g": {"comment": "", "statements": []},
            "register": {
                "parameters": [],
                "savepoints": {
                    "s1": {
                        "statements": [],
                        "require": {
                            "processes": {"c1/p1": True},
                            "actions": {"c1/p1": ["b", "c", "g"]}
                        }
                    },
                    "s2": {
                        "statements": [],
                        "require": {
                            "processes": {"c1/p1": True},
                            "actions": {"c1/p1": ["e"]}
                        }
                    },
                    "s3": {
                        "statements": [],
                        "require": {
                            "processes": {"c1/p1": True},
                            "actions": {"c1/p1": ["a"]}
                        }
                    }
                }
            }
        }
    }
    c1p2 = {
        "comment": "",
        "process": "(!register).(<b>.(<c> | <d>) | <a>).(<e>.<f> | <g>)",
        "actions": {
            "a": {"comment": "", "statements": []},
            "b": {"comment": "", "statements": []},
            "c": {"comment": "", "statements": []},
            "d": {"comment": "", "statements": []},
            "e": {"comment": "", "statements": []},
            "f": {"comment": "", "statements": []},
            "g": {"comment": "", "statements": []},
            "register": {
                "parameters": [],
                "savepoints": {
                    "s4": {
                        "statements": [],
                        "require": {
                            "processes": {"c1/p2": True},
                            "actions": {"c1/p2": ["b", "c", "g"]}
                        }
                    },
                    "s5": {
                        "statements": [],
                        "require": {
                            "processes": {"c1/p2": True},
                            "actions": {"c1/p2": ["e"]}
                        }
                    },
                    "s6": {
                        "statements": [],
                        "require": {
                            "processes": {"c1/p2": True},
                            "actions": {"c1/p2": ["a"]}
                        }
                    }
                }
            }
        }
    }
    c1p3 = {
        "comment": "",
        "process": "(!register).({level_one} | (unregister))",
        "actions": {
            "level_one": {"comment": "", "process": "<probe>.(<success>.{level_two} | <fail>).<remove>.(unregister)"},
            "level_two": {"comment": "", "process": "(<read> | <write>).{level_two} | <remove>.{level_one}"},
            "register": {
                "parameters": [],
                "savepoints": {
                    "s7": {
                        "statements": [],
                        "require": {
                            "processes": {"c1/p3": True},
                            "actions": {"c1/p3": ["probe"]}
                        }
                    },
                    "s8": {
                        "statements": [],
                        "require": {
                            "processes": {"c1/p3": True},
                            "actions": {"c1/p3": ["probe", "remove", "read"]}
                        }
                    },
                    "s9": {
                        "statements": [],
                        "require": {
                            "processes": {"c1/p3": True, "c1/p1": True},
                            "actions": {
                                "c1/p3": ["probe", "fail"],
                                "c1/p1": ["b", "c", "g"]
                            }
                        }
                    }
                }
            },
            "unregister": {"parameters": []},
            "probe": {"comment": "", "statements": []},
            "remove": {"comment": "", "statements": []},
            "success": {"comment": "", "statements": []},
            "fail": {"comment": "", "statements": []},
            "read": {"comment": "", "statements": []},
            "write": {"comment": "", "statements": []}
        }
    }
    spec = {
        "functions models": {},
        "environment processes": {
            "c1/p1": c1p1,
            "c1/p2": c1p2,
            "c1/p3": c1p3
        }
    }
    collection = CollectionDecoder(logging, dict()).parse_event_specification(source_preset(),
                                                                              json.loads(json.dumps(spec)),
                                                                              ProcessCollection())
    return collection


def test_default_scenario_extraction(model, default_separator):
    c1p1 = model.environment['c1/p1']
    c1p2 = model.environment['c1/p2']
    c2p1 = model.environment['c2/p1']

    s1 = default_separator(c1p1, model)
    assert len(s1) == 2
    _compare_scenario_with_actions(s1, c1p1.actions)
    assert len([s for s in s1 if s.savepoint]) == 2

    s2 = default_separator(c1p2, model)
    assert len(s2) == 2
    _compare_scenario_with_actions(s2, c1p2.actions)
    assert len([s for s in s2 if s.savepoint]) == 2

    s3 = default_separator(c2p1, model)
    assert len(s3) == 1


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
    scenarios = linear_separator(c1p1, model)
    _check_linear_actions(scenarios, c1p1.actions)

    # Test the number of scenarios
    # 4 - savepoints  + 1 option without savepoints
    assert len(scenarios) == 5, f'The number of scenarios is {len(scenarios)}: ' + \
                                ', '.join([s.name for s in scenarios])

    scenarios = {s.name: s for s in scenarios}
    assert 'deregister_c1p1' in scenarios
    assert scenarios['deregister_c1p1'].actions.sequence == \
           '(!register_c1p1).[register_c1p2].[deregister_c1p2].(deregister_c1p1)'
    assert 'p1s1 with deregister_c1p1' in scenarios
    assert scenarios['p1s1 with deregister_c1p1'].actions.sequence == \
           '(!register_c1p1).[register_c1p2].[deregister_c1p2].(deregister_c1p1)'
    assert 'p1s2 with deregister_c1p1' in scenarios
    assert scenarios['p1s1 with deregister_c1p1'].actions.sequence == \
           '(!register_c1p1).[register_c1p2].[deregister_c1p2].(deregister_c1p1)'
    assert 'p1s3 with deregister_c1p1' in scenarios
    assert scenarios['p1s3 with deregister_c1p1'].actions.sequence == \
           '[register_c1p2].[deregister_c1p2].(deregister_c1p1)'
    assert 'p1s4 with deregister_c1p1' in scenarios
    assert scenarios['p1s4 with deregister_c1p1'].actions.sequence == \
           '[register_c1p2].[deregister_c1p2].(deregister_c1p1)'


def test_linear_strategy_c1p2(model, linear_separator):
    c1p2 = model.environment['c1/p2']
    scenarios = linear_separator(c1p2, model)
    _check_linear_actions(scenarios, c1p2.actions)

    # Test the number of scenarios
    # 10 * 3 scenarios (2 savepoints)
    assert len(scenarios) >= 30, f'The number of scenarios is {len(scenarios)}: ' + \
                                 ', '.join([s.name for s in scenarios])

    scenarios = {s.name: s for s in scenarios}
    assert 'success_probe_read_remove_deregister_c1p2' in scenarios
    assert scenarios['success_probe_read_remove_deregister_c1p2'].actions.sequence == \
           '(!register_c1p2).<alloc>.<probe>.<success>.<read>.<remove>.(deregister_c1p2)'
    assert 'success_probe_write_remove_deregister_c1p2' in scenarios
    assert scenarios['success_probe_write_remove_deregister_c1p2'].actions.sequence == \
           '(!register_c1p2).<alloc>.<probe>.<success>.<write>.<remove>.(deregister_c1p2)'
    assert 'fail_probe_deregister_c1p2' in scenarios
    assert scenarios['fail_probe_deregister_c1p2'].actions.sequence == \
           '(!register_c1p2).<alloc>.<probe>.<fail>.(deregister_c1p2)'

    assert 'p2s1 with success_probe_read_remove_deregister_c1p2' in scenarios
    assert scenarios['p2s1 with success_probe_read_remove_deregister_c1p2'].actions.sequence == \
           '(!register_c1p2).<alloc>.<probe>.<success>.<read>.<remove>.(deregister_c1p2)'
    assert 'p2s1 with success_probe_write_remove_deregister_c1p2' in scenarios
    assert scenarios['p2s1 with success_probe_write_remove_deregister_c1p2'].actions.sequence == \
           '(!register_c1p2).<alloc>.<probe>.<success>.<write>.<remove>.(deregister_c1p2)'
    assert 'p2s1 with fail_probe_deregister_c1p2' in scenarios
    assert scenarios['p2s1 with fail_probe_deregister_c1p2'].actions.sequence == \
           '(!register_c1p2).<alloc>.<probe>.<fail>.(deregister_c1p2)'

    assert 'p2s2 with success_probe_read_remove_deregister_c1p2' in scenarios
    assert scenarios['p2s2 with success_probe_read_remove_deregister_c1p2'].actions.sequence == \
           '(!register_c1p2).<alloc>.<probe>.<success>.<read>.<remove>.(deregister_c1p2)'
    assert 'p2s2 with success_probe_write_remove_deregister_c1p2' in scenarios
    assert scenarios['p2s2 with success_probe_write_remove_deregister_c1p2'].actions.sequence == \
           '(!register_c1p2).<alloc>.<probe>.<success>.<write>.<remove>.(deregister_c1p2)'
    assert 'p2s2 with fail_probe_deregister_c1p2' in scenarios
    assert scenarios['p2s2 with fail_probe_deregister_c1p2'].actions.sequence == \
           '(!register_c1p2).<alloc>.<probe>.<fail>.(deregister_c1p2)'


def test_linear_strategy_c2p1(model, linear_separator):
    c2p1 = model.environment['c2/p1']
    scenarios = linear_separator(c2p1, model)
    _check_linear_actions(scenarios, c2p1.actions)

    # Test the number of scenarios
    # 3 options with a single sp
    # Todo: reimplement this. It is better to cover sequences somehow.
    assert len(scenarios) == 6, f'The number of scenarios is {len(scenarios)}: ' + \
                                ', '.join([s.name for s in scenarios])


def test_linear_plain_process(specific_model, linear_separator):
    c1p1 = specific_model.environment['c1/p1']
    scenarios = linear_separator(c1p1, specific_model)
    _check_linear_actions(scenarios, c1p1.actions)

    assert len(scenarios) == 1
    assert list(scenarios)[0].name == 'base'


def test_linear_deep_subprocesses(specific_model, linear_separator):
    c1p2 = specific_model.environment['c1/p2']
    scenarios = linear_separator(c1p2, specific_model)
    _check_linear_actions(scenarios, c1p2.actions)

    assert len(scenarios) == 4, f'The number of scenarios is {len(scenarios)}: ' + \
                                ', '.join([s.name for s in scenarios])

    scenarios = {s.name: s for s in scenarios}
    assert 'level_three_a' in scenarios
    assert scenarios['level_three_a'].actions.sequence == '(!register_c1p1).<a>.<d>.(deregister_c1p1)'
    assert 'level_two_a_c' in scenarios
    assert scenarios['level_two_a_c'].actions.sequence == '(!register_c1p1).<a>.<c>.(deregister_c1p1)'
    assert 'finish' in scenarios
    assert scenarios['finish'].actions.sequence == '(!register_c1p1).(deregister_c1p1)'
    assert 'level_two_a_b' in scenarios
    assert scenarios['level_two_a_b'].actions.sequence == '(!register_c1p1).<a>.<b>.(deregister_c1p1)'


def test_linear_c2_p1(specific_model, linear_separator):
    c2p1 = specific_model.environment['c2/p1']
    scenarios = linear_separator(c2p1, specific_model)
    _check_linear_actions(scenarios, c2p1.actions)

    assert len(scenarios) == 1, f'The number of scenarios is {len(scenarios)}: ' + \
                                ', '.join([s.name for s in scenarios])

    scenarios = {s.name: s for s in scenarios}
    assert 'level_one' in scenarios
    assert scenarios['level_one'].actions.sequence == '(!register_c2p1).<a>.<b>'


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

    # No blocks with conditions
    for scenario in scenarios:
        for action in scenario.actions.filter(include={Block}):
            assert not action.condition, "Blocks must be moved to statements as assumptions"


def test_reqs_p1(model_with_savepoint_requirements, requirements_driven_separator):
    c1p1 = model_with_savepoint_requirements.environment['c1/p1']
    scenarios = requirements_driven_separator(c1p1, model_with_savepoint_requirements)

    # There should be an extra scenario which is created for savepoint 9
    assert len(scenarios) == len(c1p1.actions['register'].savepoints) + 1

    scenario_dict = {s.name: s for s in scenarios}
    s1 = scenario_dict['s1 with b_c_g']
    s2 = scenario_dict['s2 with e']
    s3 = scenario_dict['s3 with a']
    s4 = list(set(scenarios).difference({s1, s2, s3})).pop()

    s1_removed = {'a', 'd', 'e', 'f'}
    _check_removed_actions(set(c1p1.actions.keys()).difference(s1_removed), s1_removed, s1)
    s2_removed = {'g'}
    _check_removed_actions(set(c1p1.actions.keys()).difference(s2_removed), s2_removed, s2)
    s3_removed = {'b', 'c', 'd', 'x'}
    _check_removed_actions(set(c1p1.actions.keys()).difference(s3_removed), s3_removed, s3)

    assert not s4.savepoint
    _check_removed_actions(set(c1p1.actions.keys()).difference(s1_removed), s1_removed, s4)


def test_reqs_p2(model_with_savepoint_requirements, requirements_driven_separator):
    c1p2 = model_with_savepoint_requirements.environment['c1/p2']
    scenarios = requirements_driven_separator(c1p2, model_with_savepoint_requirements)

    assert len(scenarios) == len(c1p2.actions['register'].savepoints)

    scenario_dict = {s.name: s for s in scenarios}
    s1 = scenario_dict['s4 with b_c_g']
    s2 = scenario_dict['s5 with e']
    s3 = scenario_dict['s6 with a']

    s1_removed = {'a', 'd', 'e', 'f'}
    _check_removed_actions(set(c1p2.actions.keys()).difference(s1_removed), s1_removed, s1)
    s2_removed = {'g'}
    _check_removed_actions(set(c1p2.actions.keys()).difference(s2_removed), s2_removed, s2)
    s3_removed = {'b', 'c', 'd'}
    _check_removed_actions(set(c1p2.actions.keys()).difference(s3_removed), s3_removed, s3)


def test_reqs_p3(model_with_savepoint_requirements, requirements_driven_separator):
    c1p3 = model_with_savepoint_requirements.environment['c1/p3']
    scenarios = requirements_driven_separator(c1p3, model_with_savepoint_requirements)

    assert len(scenarios) == len(c1p3.actions['register'].savepoints)

    scenario_dict = {s.name: s for s in scenarios}
    s1 = scenario_dict['s7 with probe']
    s2 = scenario_dict['s8 with probe_remove_read']
    s3 = scenario_dict['s9 with probe_fail']

    s1_removed = {}
    _check_removed_actions(set(c1p3.actions.keys()).difference(s1_removed), s1_removed, s1)
    assert len(s1.actions.behaviour('unregister')) == 1
    s2_removed = {'write'}
    _check_removed_actions(set(c1p3.actions.keys()).difference(s2_removed), s2_removed, s2)
    s3_removed = {'success', 'read', 'write', 'level_two'}
    _check_removed_actions(set(c1p3.actions.keys()).difference(s3_removed), s3_removed, s3)


def _check_removed_actions(required, removed, scenario):
    for action in required:
        assert action in scenario.actions
    for action in removed:
        assert action not in scenario.actions
