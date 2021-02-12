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

import json
import pytest
import logging

from klever.core.vtg.emg.common.c import Function
from klever.core.vtg.emg.common.c.source import Source
from klever.core.vtg.emg.common.process.serialization import CollectionDecoder, CollectionEncoder


@pytest.fixture
def source():
    cfiles = [
        'main.c',
        'lib.c'
    ]

    source = Source(cfiles, [], dict())
    main_functions = {
        'f1': "static int f1(struct test *)",
        'f2': "static void f2(struct test *)",
        'f3': "static void f3(struct test *)",
        'f4': "static int f4(struct validation *)",
        'f5': "static void f4(void)"
    }
    external_functions = {
        "register_c1": "int register_c1(struct test *)",
        "deregister_c1": "void deregister_c1(struct test *)",
        "register_c2": "int register_c2(struct validation *)",
        "deregister_c2": "void deregister_c2(struct validation *)"
    }

    for name, declaration_str in main_functions.items():
        new = Function(name, declaration_str)
        new.definition_file = cfiles[0]
        source.set_source_function(new, cfiles[0])

    for name, declaration_str in external_functions.items():
        new = Function(name, declaration_str)
        new.definition_file = cfiles[1]
        source.set_source_function(new, cfiles[1])

    return source


@pytest.fixture
def raw_model():
    c1p1 = {
        "comment": "Category 1, process 1.",
        "headers": ["linux/test.h"],
        "labels": {
            "container": {
                "declaration": "struct test *var",
                "value": "0"
            }
        },
        "process": "(!register_c1p1).{activate}",
        "actions": {
            "activate": {
                "comment": "Activate the second process.",
                "process": "([register_c1p2].[deregister_c1p2]).({activate} | (deregister_c1p1))"
            },
            "register_c1p1": {
                "parameters": ['%container%']
            },
            "deregister_c1p1": {
                "parameters": ['%container%']
            },
            "register_c1p2": {
                "parameters": ['%container%']
            },
            "deregister_c1p2": {
                "parameters": ['%container%']
            }
        }
    }
    c1p2 = {
        "comment": "Category 1, process 2.",
        "headers": ["linux/test.h"],
        "labels": {
            "container": {
                "declaration": "struct test *var",
                "value": "0"
            },
            "ret": {
                "declaration": "int x",
                "value": "0"
            }
        },
        "process": "(!register_c1p2).<alloc>.{main}",
        "declarations": {
            "environment model": {
                "global_var": "struct test *global_var;\n"
            }
        },
        "actions": {
            "main": {
                "comment": "Test initialization.",
                "process": "<probe>.(<success>.{calls} | <fail>.{main}) | (deregister_c1p2)"
            },
            "calls": {
                "comment": "Test actions.",
                "process": "(<read> | <write>).(<remove>.{main} | {calls})"
            },
            "register_c1p2": {
                "condition": ["$ARG1 == global_var"],
                "parameters": ['%container%']
            },
            "alloc": {
                "comment": "Alloc memory for the container.",
                "statements": ["$CALLOC(%container%);"]
            },
            "probe": {
                "comment": "Do probing.",
                "statements": ["%ret% = f1(%container%);"]
            },
            "success": {
                "comment": "Successful probing.",
                "condition": ["%ret% == 0"]
            },
            "fail": {
                "comment": "Failed probing.",
                "condition": ["%ret% != 0"]
            },
            "deregister_c1p2": {
                "parameters": ['%container%']
            },
            "read": {
                "comment": "Reading.",
                "statements": ["f2(%container%);"]
            },
            "write": {
                "comment": "Writing.",
                "statements": ["f3(%container%);"]
            },
            "remove": {
                "comment": "Removing.",
                "statements": ["$FREE(%container%);"]
            }
        }
    }
    c2p1 = {
        "comment": "Category 2, process 1.",
        "labels": {
            "container": {
                "declaration": "struct validation *var",
                "value": "0"
            },
            "ret": {
                "declaration": "int x",
                "value": "0"
            }
        },
        "process": "(!register_c2p1).{main}",
        "actions": {
            "main": {
                "comment": "Test initialization.",
                "process": "<probe>.(<success> | <fail>.<remove>).{main} | (deregister_c2p1)"
            },
            "register_c2p1": {
                "condition": ["$ARG1 != 0"],
                "parameters": ['%container%']
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
            "deregister_c2p1": {
                "parameters": ['%container%']
            },
            "remove": {
                "comment": "Removing.",
                "statements": ["$FREE(%container%);"]
            }
        }
    }
    register_c1 = {
        "comment": "Register С1.",
        "labels": {
            "container": {
                "declaration": "struct test *var"
            },
        },
        "process": "<assign>.[register_c1p1].<success> | <fail>",
        "actions": {
            "register_c1p1": {
                "parameters": [
                    "%container%"
                ]
            },
            "assign": {
                "comment": "Get container.",
                "statements": [
                    "%container% = $ARG1;"
                ]
            },
            "fail": {
                "comment": "Failed registration.",
                "statements": ["return ldv_undef_int_negative();"]
            },
            "success": {
                "comment": "Successful registration.",
                "statements": [
                    "return 0;"
                ]
            }
        }
    }
    deregister_c1 = {
        "comment": "Deregister C1.",
        "labels": {
            "container": {
                "declaration": "struct test *var"
            },
        },
        "process": "<assign>.[deregister_c1p1]",
        "actions": {
            "deregister_c1p1": {
                "parameters": [
                    "%container%"
                ]
            },
            "assign": {
                "comment": "Get container.",
                "statements": [
                    "%container% = $ARG1;"
                ]
            }
        }
    }
    register_c2 = {
        "comment": "Register С2.",
        "labels": {
            "container": {
                "declaration": "struct validation *var"
            },
        },
        "process": "<assign>.[register_c2p1].<success> | <fail>",
        "actions": {
            "register_c2p1": {
                "parameters": [
                    "%container%"
                ]
            },
            "assign": {
                "comment": "Get container.",
                "statements": [
                    "%container% = $ARG1;"
                ]
            },
            "fail": {
                "comment": "Failed registration.",
                "statements": ["return ldv_undef_int_negative();"]
            },
            "success": {
                "comment": "Successful registration.",
                "statements": [
                    "return 0;"
                ]
            }
        }
    }
    deregister_c2 = {
        "comment": "Deregister C2.",
        "labels": {
            "container": {
                "declaration": "struct validation *var"
            },
        },
        "process": "<assign>.[deregister_c2p1]",
        "actions": {
            "deregister_c2p1": {
                "parameters": [
                    "%container%"
                ]
            },
            "assign": {
                "comment": "Get container.",
                "statements": [
                    "%container% = $ARG1;"
                ]
            }
        }
    }
    main = {
        "comment": "Main process.",
        "labels": {},
        "process": "<root>",
        "actions": {
            "root": {
                "statements": "f5();"
            }
        }
    }

    spec = {
        "functions models": {
            "register_c1": register_c1,
            "deregister_c1": deregister_c1,
            "register_c2": register_c2,
            "deregister_c2": deregister_c2
        },
        "environment processes": {
            "c1/p1": c1p1,
            "c1/p2": c1p2,
            "c2/p1": c2p1
        },
        "main process": main
    }

    return spec


@pytest.fixture()
def model(source, raw_model):
    parser = CollectionDecoder(logging, dict())
    return parser.parse_event_specification(source, raw_model)


def test_import_model(raw_model, model):
    raw2 = json.loads(json.dumps(model, cls=CollectionEncoder))
    _compare_models(raw_model, raw2)


def test_imported_names(raw_model, model):
    assert 'entry' == model.entry.name

    for name in raw_model['functions models']:
        assert name in model.models, 'There are models: {}'.format(', '.join(sorted(model.models.keys())))

    for name in raw_model['environment processes']:
        assert name in model.environment, 'There are models: {}'.format(', '.join(sorted(model.environment.keys())))


def test_export_model(source, model):
    raw1 = json.dumps(model, cls=CollectionEncoder)
    new_model = CollectionDecoder(logging, dict()).parse_event_specification(source, json.loads(raw1))
    raw2 = json.dumps(new_model, cls=CollectionEncoder)

    raw1 = json.loads(raw1)
    raw2 = json.loads(raw2)
    _compare_models(raw1, raw2)


def _compare_models(raw1, raw2):
    _compare_process(raw1["main process"], raw2["main process"])
    for attr in ("functions models", "environment processes"):
        collection1 = raw1.get(attr, dict())
        collection2 = raw2.get(attr, dict())
        assert len(collection1) == len(collection2), attr
        for key in collection1:
            assert key in collection2, key
            _compare_process(collection1[key], collection2[key])


def _compare_process(one, two):
    for item in ('comment', 'headers', 'declarations', 'definitions', 'source files'):
        assert str(one.get(item)) == str(two.get(item))

    assert len(one['labels']) == len(two['labels'])
    for label in one['labels']:
        for attr in ('value', 'declaration'):
            assert one['labels'][label].get(attr) == one['labels'][label].get(attr), f"{label}, {attr}"

    _compare_actions_collections(one['actions'], two['actions'])


def _compare_actions_collections(one, two):
    assert len(one) == len(two)
    for action in one:
        _compare_actions(one[action], two[action])


def _compare_actions(one, two):
    # todo: we do not test attribute 'trace relevant' as it is unnecessary
    for attr in ('comment', 'statements', 'condition', 'parameters', 'savepoints',
                 'peers', 'pre-call', 'post-call'):
        assert str(one.get(attr)) == str(two.get(attr)), f"{attr}"

    if 'process' in one:
        assert 'process' in two


def test_compare_peers(model):
    def _check_peers(p1, p2, actions):
        assert str(p1) in p2.peers, 'Peers are {}'.format(', ', p2.peers.keys())
        assert str(p2) in p1.peers, 'Peers are {}'.format(', ', p1.peers.keys())
        for action in actions:
            assert action in p1.peers[str(p2)], 'Peer actions are: {}'.format(', '.join(sorted(p1.peers[str(p2)])))
            assert action in p2.peers[str(p1)], 'Peer actions are: {}'.format(', '.join(sorted(p2.peers[str(p1)])))
        assert len(actions) == len(p1.peers[str(p2)]), 'Peers are {}'.format(', '.join(sorted(p2.peers[str(p1)])))
        assert len(actions) == len(p2.peers[str(p1)]), 'Peers are {}'.format(', '.join(sorted(p1.peers[str(p2)])))
            
    def expect_peers(p1, length):
        assert len(p1.peers) == length, 'Peers are {}'.format(', ', p1.peers.keys())
    
    model.establish_peers()
    
    # register_c1, deregister_c1
    _check_peers(model.models['register_c1'], model.environment['c1/p1'], {'register_c1p1'})
    _check_peers(model.models['deregister_c1'], model.environment['c1/p1'], {'deregister_c1p1'})
    expect_peers(model.models['register_c1'], 1)
    expect_peers(model.models['deregister_c1'], 1)
    
    # register_c2, deregister_c2
    _check_peers(model.models['register_c2'], model.environment['c2/p1'], {'register_c2p1'})
    _check_peers(model.models['deregister_c2'], model.environment['c2/p1'], {'deregister_c2p1'})
    expect_peers(model.models['register_c2'], 1)
    expect_peers(model.models['deregister_c2'], 1)
    
    # c1/p1
    _check_peers(model.environment['c1/p1'], model.environment['c1/p2'], {'register_c1p2', 'deregister_c1p2'})
    expect_peers(model.environment['c1/p1'], 3)
    
    # c1/p2
    expect_peers(model.environment['c1/p2'], 1)
    
    # c2/p2
    expect_peers(model.environment['c1/p1'], 3)
    
    # main
    expect_peers(model.entry, 0)

    # todo: Check that peers are correctly exported and imported back

