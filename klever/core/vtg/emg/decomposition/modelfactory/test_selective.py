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

import sys
import json
import pytest
import logging
from klever.core.vtg.emg.common.c import Function
from klever.core.vtg.emg.common.c.source import Source
from klever.core.vtg.emg.common.process import ProcessCollection
from klever.core.vtg.emg.common.process.serialization import CollectionDecoder
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy
from klever.core.vtg.emg.decomposition.separation.linear import LinearStrategy
from klever.core.vtg.emg.decomposition.modelfactory.selective import SelectiveFactory


MAIN = {
    "comment": "Main process.",
    "labels": {},
    "process": "<root>",
    "actions": {
        "root": {
            "comment": "Some action",
            "statements": []
        }
    }
}
REGISTER = {
    "comment": "",
    "labels": {"container": {"declaration": "struct validation *var"}},
    "process": "[register_p1]",
    "actions": {
        "register_p1": {"parameters": ["%container%"]}
    }
}
DEREGISTER = {
    "comment": "",
    "labels": {"container": {"declaration": "struct validation *var"}},
    "process": "[deregister_p1]",
    "actions": {
        "deregister_p1": {"parameters": ["%container%"]}
    }
}
B1 = {
    "comment": "",
    "labels": {
        "container": {"declaration": "struct validation *var"},
        "ret": {"declaration": "int x", "value": "0"}
    },
    "process": "(!register_p1).{main}",
    "actions": {
        "main": {
            "comment": "",
            "process": "<probe>.(<success>.[register_p2] | <fail>.<remove>).{main} | (deregister_p1)"
        },
        "register_p1": {
            "condition": ["$ARG1 != 0"],
            "parameters": ['%container%'],
            "savepoints": {'s1': {"statements": []}}
        },
        "probe": {
            "comment": "Do probing.",
            "statements": ["%ret% = f4(%container%);"]
        },
        "success": {
            "comment": "Successful probing.",
            "condition": ["%ret% == 0"]
        },
        "fail": {
            "comment": "Failed probing.",
            "condition": ["%ret% != 0"]
        },
        "deregister_p1": {
            "parameters": ['%container%']
        },
        "remove": {
            "comment": "Removing.",
            "statements": ["$FREE(%container%);"]
        },
        "register_p2": {
            "parameters": ['%container%']
        }
    }
}
B2 = {
    "comment": "",
    "labels": {
        "container": {"declaration": "struct validation *var"}
    },
    "process": "(!register_p2).([read] | [write])",
    "actions": {
        "register_p2": {
            "parameters": ['%container%'],
            "savepoints": {'s2': {"statements": []}},
            "require": {"c/p1": {"include": ["probe", "success"]}}
        },
        "read": {"comment": "", "statements": []},
        "write": {"comment": "Do write.", "statements": []}
    }
}


@pytest.fixture()
def model():
    files = ['test.c']
    functions = {
        'f1': "static int f1(struct test *)",
        'f2': "static void f2(struct test *)"
    }
    source = Source(files, [], dict())
    for name, declaration_str in functions.items():
        new = Function(name, declaration_str)
        new.definition_file = files[0]
        source.set_source_function(new, files[0])
    spec = {
        "name": 'base',
        "functions models": {
            "f1": REGISTER,
            "f2": DEREGISTER,
        },
        "environment processes": {
            "c/p1": B1,
            "c/p2": B2
        },
        "main process": MAIN
    }
    collection = CollectionDecoder(logging, dict()).parse_event_specification(source,
                                                                              json.loads(json.dumps(spec)),
                                                                              ProcessCollection())
    return collection


P1 = {
    "comment": "",
    "labels": {},
    "process": "(!register_p1).<init>.(<exit> | <init_failed>)",
    "actions": {
        "register_p1": {
            "parameters": [],
            "savepoints": {
                'sp_init_first': {"statements": []},
                'sp_init_second': {"statements": []},
                'sp_init_third': {"statements": []}
            }
        },
        "init": {"comment": ""},
        "exit": {"comment": ""},
        "init_failed": {"comment": ""}
    }
}
REGISTER_P2 = {
    "comment": "",
    "labels": {},
    "process": "[register_p2]",
    "actions": {"register_p2": {}}
}
DEREGISTER_P2 = {
    "comment": "",
    "labels": {},
    "process": "[deregister_p2]",
    "actions": {"deregister_p2": {}}
}
P2 = {
    "comment": "",
    "labels": {"ret": {"declaration": "int x"}},
    "process": "(!register_p2).{main}",
    "actions": {
        "main": {
            "comment": "Test initialization.",
            "process": "<probe>.(<success>.[register_p3].[deregister_p3] | <fail>.<remove>).{main} | (deregister_p2)"
        },
        "register_p2": {
            "parameters": [],
            "require": {
                "c/p1": {"include": ["init", "exit"]}
            }
        },
        "deregister_p2": {"parameters": []},
        "probe": {"comment": ""},
        "success": {"comment": "", "condition": ["%ret% == 0"]},
        "fail": {"comment": "Failed probing.", "condition": ["%ret% != 0"]},
        "remove": {"comment": ""},
        "register_p3": {"parameters": []},
        "deregister_p3": {"parameters": []}
    }
}
P3 = {
    "comment": "",
    "labels": {},
    "process": "(!register_p3).<init>.{scenario1}",
    "actions": {
        "register_p3": {
            "parameters": [],
            "savepoints": {
                'sp_init_p3': {"statements": [], "comment": "test comment"}
            },
            "require": {
                "c/p2": {"include": ["register_p3", "deregister_p3"]}
            }
        },
        "deregister_p3": {"parameters": []},
        "free": {"comment": ""},
        "terminate": {"comment": "", "process": "<free>.(deregister_p3)"},
        "init": {"comment": ""},
        "create": {"comment": ""},
        "create_fail": {"comment": ""},
        "create2": {"comment": ""},
        "create2_fail": {"comment": ""},
        "success": {"comment": ""},
        "work1": {"comment": ""},
        "work2": {"comment": ""},
        "register_p4": {"parameters": []},
        "deregister_p4": {"parameters": []},
        "create_scenario": {
            "comment": "",
            "process": "<create>.(<success>.({work_scenario} | {p4_scenario}) | <create_fail>.{terminate})"
        },
        "create2_scenario": {"comment": "", "process": "<create2>.(<create2_fail> | <success>).{terminate}"},
        "work_scenario": {"comment": "", "process": "(<work1> | <work2>).{terminate}"},
        "p4_scenario": {"comment": "", "process": "[register_p4].[deregister_p4].{terminate}"},
        "scenario1": {"comment": "", "process": "{create_scenario} | {create2_scenario}"}
    }
}
P4 = {
    "comment": "",
    "labels": {},
    "process": "(!register_p4).<write>.(deregister_p4)",
    "actions": {
        "register_p4": {
            "parameters": [],
            "require": {
                "c/p3": {"include": ["register_p4"]}
            }
        },
        "deregister_p4": {"parameters": []},
        "write": {"comment": ""}
    }
}


@pytest.fixture()
def advanced_model():
    files = ['test.c']
    functions = {
        'f1': "static int f1(struct test *)",
        'f2': "static void f2(struct test *)"
    }
    source = Source(files, [], dict())
    for name, declaration_str in functions.items():
        new = Function(name, declaration_str)
        new.definition_file = files[0]
        source.set_source_function(new, files[0])
    spec = {
        "functions models": {
            "f1": REGISTER_P2,
            "f2": DEREGISTER_P2,
        },
        "environment processes": {
            "c/p1": P1,
            "c/p2": P2,
            "c/p3": P3,
            "c/p4": P4
        }
    }
    collection = CollectionDecoder(logging, dict()).parse_event_specification(source,
                                                                              json.loads(json.dumps(spec)),
                                                                              ProcessCollection())
    return collection


@pytest.fixture()
def logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return logger


def _obtain_model(logger, model, specification):
    separation = SelectiveFactory(logger, specification)
    scenario_generator = SeparationStrategy(logger, dict())
    processes_to_scenarios = {str(process): list(scenario_generator(process)) for process in model.environment.values()}
    return processes_to_scenarios, list(separation(processes_to_scenarios, model))


def _obtain_linear_model(logger, model, specification):
    separation = SelectiveFactory(logger, specification)
    scenario_generator = LinearStrategy(logger, dict())
    processes_to_scenarios = {str(process): list(scenario_generator(process)) for process in model.environment.values()}
    return processes_to_scenarios, list(separation(processes_to_scenarios, model))


def test_default_coverage(logger, advanced_model):
    spec = {
        "must not contain": {"c/p3": {}},
        "must contain": {
            "c/p2": {"scenarios only": False}
        },
        "cover scenarios": {"c/p1": {"savepoints except": []}}
    }
    processes_to_scenarios, models = _obtain_model(logger, advanced_model, spec)

    # Cover all p1 savepoints + base p2 process, expect no p3, p4
    p1scenarios = processes_to_scenarios['c/p1']
    assert len(p1scenarios) == len(models)
    for model in models:
        assert 'c/p2' in model.environment
        assert 'c/p3' not in model.environment
        assert 'c/p4' not in model.environment


def test_inclusion_p2(logger, model):
    spec = {
        "must contain": {"c/p2": {}},
        "cover scenarios": {"c/p2": {}}
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, model, spec)

    # Cover all c2p2 scenarios
    p2scenarios = processes_to_scenarios['c/p2']
    assert len(p2scenarios) == len(models)
    actions = [m.environment['c/p2'].actions for m in models if 'c/p2' in m.environment] + \
              [m.entry.actions for m in models]
    for scenario in p2scenarios:
        assert scenario.actions in actions


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
    assert all([True if c2p2_withsavepoint.actions != m.entry.actions else False for m in models])


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


def test_complex_restrictions(logger, model):
    spec = {
        "must contain": {"c/p2": {"actions": [["read"]]}},
        "must not contain": {"c/p1": {"savepoints": ["s1"]},
                             "c/p2": {"actions": [["write"]]}},
        "cover scenarios": {"c/p2": {}}
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, model, spec)

    # Cover only scenarios with read from p2
    scenarios_with_read = [s for s in processes_to_scenarios['c/p2'] if 'write' not in s.actions]
    assert len(models) == len(scenarios_with_read)
    actions = [m.environment['c/p2'].actions for m in models if 'c/p2' in m.environment] + \
              [m.entry.actions for m in models if 'c/p2' not in m.environment]
    for model_actions in actions:
        assert 'write' not in model_actions
        assert 'read' in model_actions

    # No scenarios with a savepoint p1s1
    p1_withsavepoint = [s for s in processes_to_scenarios['c/p1'] if s.savepoint].pop()
    assert all([True if p1_withsavepoint.actions != m.entry.actions else False for m in models])


def test_contraversal_conditions(logger, model):
    spec = {
        "must contain": {"c/p2": {}},
        "must not contain": {"c/p1": {}},
        "cover scenarios": {"c/p1": {}}
    }
    with pytest.raises(ValueError):
        _obtain_linear_model(logger, model, spec)

    spec = {
        "must contain": {"c/p2": {}},
        "must not contain": {"c/p1": {}, "c/p2": {"savepoints": []}},
        "cover scenarios": {"c/p2": {}}
    }
    with pytest.raises(ValueError):
        _obtain_linear_model(logger, model, spec)


def test_complex_exclusion(logger, model):
    spec = {
        "must contain": {"c/p1": {}},
        "must not contain": {"c/p1": {"actions": [["probe", "success"]]}},
        "cover scenarios": {"c/p1": {}}
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, model, spec)
    relevant_scenarios = [s.actions for s in processes_to_scenarios['c/p1']
                          if not {"probe", "success"}.issubset(set(s.actions.keys()))]

    # Test the number of models
    assert len(models) == len(relevant_scenarios)

    # Test that threre is a p1 model in models
    actions = [m.environment['c/p1'].actions for m in models if 'c/p1' in m.environment] + \
              [m.entry.actions for m in models if 'c/p1' not in m.environment]

    # Test allscenarios of p1 are covered
    assert len(actions) == len(relevant_scenarios)
    for scneario_actions in relevant_scenarios:
        assert scneario_actions in actions


def test_cover_actions(logger, model):
    spec = {
        "cover scenarios": {"c/p1": {"actions": ["probe"], "savepoints": []}}
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, model, spec)
    assert len(models) == 1
    model = models.pop()
    if 'c/p1' in model.environment:
        actions = model.environment['c/p1'].actions
    else:
        actions = model.entry.actions

    assert "probe" in actions


def test_cover_savepoint(logger, model):
    spec = {
        "must contain": {"c/p1": {"savepoints": ["s1"]}},
        "cover scenarios": {"c/p1": {"savepoints": ["s1"]}}
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, model, spec)

    # Test the number of models
    relevant_scenarios = [s.actions for s in processes_to_scenarios['c/p1'] if s.savepoint]
    assert len(relevant_scenarios) == len(models)

    for model in models:
        assert "c/p1" not in model.environment
        assert "s1" in model.entry.actions


def test_cover_except_savepoint(logger, model):
    spec = {
        "must contain": {"c/p1": {}},
        "cover scenarios": {"c/p1": {"savepoints except": ["s1"]}}
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, model, spec)

    # Test the number of models
    relevant_scenarios = [s.actions for s in processes_to_scenarios['c/p1'] if not s.savepoint]
    assert len(relevant_scenarios) == len(models)

    model_actions = [m.environment['c/p1'].actions for m in models]
    for relevant in relevant_scenarios:
        assert relevant in model_actions


def test_cover_except_actions(logger, model):
    spec = {
        "must contain": {"c/p2": {}},
        "cover scenarios": {"c/p2": {"actions except": ["read"], "savepoints": []}}
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, model, spec)

    # Test the number of models
    relevant_scenarios = [s.actions for s in processes_to_scenarios['c/p2']
                          if not s.savepoint and "read" not in s.actions]
    assert len(relevant_scenarios) == len(models)

    model_actions = [m.environment['c/p2'].actions for m in models if 'c/p2' in m.environment] +\
                    [m.entry.actions for m in models if 'c/p2' not in m.environment]
    for relevant in relevant_scenarios:
        assert relevant in model_actions


def test_missing_keys(logger, model):
    error_specs = [
        {
            "must contain": {"c/p3": {}},
            "cover scenarios": {"c/p1": {}}
        },
        {
            "cover scenarios": {"c/p3": {}}
        },
        {
            "must not contain": {"c/p3": {}},
            "cover scenarios": {"c/p1": {}}
        },
        {
            "cover scenarios": {"c/p1": {"savepoints": ["x"]}}
        },
        {
            "cover scenarios": {"c/p1": {"actions": ["x"]}}
        },
        {
            "cover scenarios": {"c/p1": {"savepoints except": ["x"]}}
        },
        {
            "cover scenarios": {"c/p1": {"actions except": ["x"]}}
        },
        {
            "must contain": {"c/p1": {"actions": [['']]}},
            "cover scenarios": {"c/p1": {}}
        },
        {
            "must contain": {"c/p1": {"actions": ['']}},
            "cover scenarios": {"c/p1": {}}
        },
        {
            "must contain": {"c/p1": {"savepoints": [['']]}},
            "cover scenarios": {"c/p1": {}}
        },
        {
            "must contain": {"c/p1": {"savepoints": ['x']}},
            "cover scenarios": {"c/p1": {}}
        },
        {
            "must not contain": {"c/p1": {"actions": ['']}},
            "cover scenarios": {"c/p1": {}}
        },
        {
            "must not contain": {"c/p1": {"savepoints": [['']]}},
            "cover scenarios": {"c/p1": {}}
        },
        {
            "must not contain": {"c/p1": {"savepoints": ['x']}},
            "cover scenarios": {"c/p1": {}}
        }
    ]
    for spec in error_specs:
        with pytest.raises(AssertionError):
            _obtain_linear_model(logger, model, spec)

# def test_combinations_with_deleted_dependencies():
#     raise NotImplementedError
#
#
# def test_all_process_savepoints():
#     raise RuntimeError
#
#
# def test_all_processes_explicitly():
#     raise NotImplementedError
#
#
# def test_all_processes_autoconfig():
#     raise NotImplementedError
