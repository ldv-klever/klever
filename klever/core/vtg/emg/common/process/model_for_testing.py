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

import logging

from klever.core.vtg.emg.common.c import Function
from klever.core.vtg.emg.common.c.source import Source
from klever.core.vtg.emg.common.process import ProcessCollection
from klever.core.vtg.emg.common.process.serialization import CollectionDecoder


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
            "process": "([register_c1p2].[deregister_c1p2]).({activate} | (deregister_c1p1))",
            "savepoints": {
                'p1s3': {"statements": ["$ALLOC(%container%);"], "comment": "Expect to detect."},
                'p1s4': {"statements": ["$ALLOC(%container%);"]}
            }
        },
        "register_c1p1": {
            "parameters": ['%container%'],
            "savepoints": {
                'p1s1': {
                    "statements": ["$ALLOC(%container%);"],
                    "require": {
                        "actions": {"c1/p1": ["register_c1p2", "deregister_c1p1"]},
                        "processes": {"c1/p1": True, "c1/p2": True}
                    }
                },
                'p1s2': {"statements": ["$ALLOC(%container%);"]}
            }
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
            "parameters": ['%container%'],
            "savepoints": {
                'p2s1': {"statements": ["$ALLOC(%container%);"]},
                'p2s2': {"statements": ["$ALLOC(%container%);"]}
            },
            "require": {"processes": {"c1/p1": True}}
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
           "process": "<probe>.(<success>.[register_c2p2] | <fail>.<remove>).{main} | (deregister_c2p1)"
       },
       "register_c2p1": {
           "condition": ["$ARG1 != 0"],
           "parameters": ['%container%'],
           "savepoints": {
               'c2p1s1': {"statements": []}
           }
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
       },
       "register_c2p2": {
           "parameters": ['%container%']
       }
   }
}
register_c1 = {
    "comment": "Register С1.",
    "labels": {
        "container": {
            "declaration": "struct test *var"
        }
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
        }
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
        }
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
        }
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
            "comment": "Some action",
            "statements": "f5();",
            "savepoints": {
                "entry_sp": {"statements": []}
            }
        }
    }
}
spec = {
    "name": 'test_model',
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


def source_preset():
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


def raw_model_preset():
    return spec


def model_preset():
    source = source_preset()
    raw_model = raw_model_preset()
    parser = CollectionDecoder(logging, dict())
    model = parser.parse_event_specification(source, raw_model, ProcessCollection())
    model.establish_peers()
    return model
