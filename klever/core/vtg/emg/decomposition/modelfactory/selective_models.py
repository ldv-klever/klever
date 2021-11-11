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
import logging
from klever.core.vtg.emg.common.c import Function
from klever.core.vtg.emg.common.c.source import Source
from klever.core.vtg.emg.common.process import ProcessCollection
from klever.core.vtg.emg.common.process.serialization import CollectionDecoder


class DeviceDriverModel:

    entry = {
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
    f1_model = {
        "comment": "",
        "labels": {"container": {"declaration": "struct validation *var"}},
        "process": "[register_p1]",
        "actions": {
            "register_p1": {"parameters": ["%container%"]}
        }
    }
    f2_model = {
        "comment": "",
        "labels": {"container": {"declaration": "struct validation *var"}},
        "process": "[deregister_p1]",
        "actions": {
            "deregister_p1": {"parameters": ["%container%"]}
        }
    }
    environment_models = {
        "c/p1": {
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
        },
        "c/p2": {
            "comment": "",
            "labels": {
                "container": {"declaration": "struct validation *var"}
            },
            "process": "(!register_p2).([read] | [write])",
            "actions": {
                "register_p2": {
                    "parameters": ['%container%'],
                    "savepoints": {'s2': {"statements": []}},
                    "require": {"processes": {"c/p1": True}, "actions": {"c/p1": ["probe", "success"]}}
                },
                "read": {"comment": "", "statements": []},
                "write": {"comment": "Do write.", "statements": []}
            }
        }
    }


class FileSystemModel:
    entry = None
    f1_model = {
        "comment": "",
        "labels": {},
        "process": "[register_p2]",
        "actions": {"register_p2": {}}
    }
    f2_model = {
        "comment": "",
        "labels": {},
        "process": "[deregister_p2]",
        "actions": {"deregister_p2": {}}
    }
    environment_models = {
        "c/p1": {
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
        },
        "c/p2": {
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
                        "processes": {"c/p1": True},
                        "actions": {
                            "c/p1": ["init", "exit"]
                        }
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
        },
        "c/p3": {
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
                        "processes": {"c/p2": True},
                        "actions": {"c/p2": ["register_p3", "deregister_p3"]}
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
        },
        "c/p4": {
            "comment": "",
            "labels": {},
            "process": "(!register_p4).<write>.(deregister_p4)",
            "actions": {
                "register_p4": {
                    "parameters": [],
                    "require": {
                        "actions": {"c/p3": ["register_p4"]},
                        "processes": {"c/p3": True}
                    }
                },
                "deregister_p4": {"parameters": []},
                "write": {"comment": ""}
            }
        }
    }


class ExtendedFileSystemModel(FileSystemModel):

    environment_models = {
        **dict(FileSystemModel.environment_models),
        "c/p6": {
            "comment": "The process that does not rely on any other.",
            "labels": {},
            "process": "(!register_unique).(<w1> | <w2>)",
            "actions": {
                "register_unique": {
                    "parameters": [],
                    "savepoints": {
                        'sp_unique_1': {"statements": []},
                        'sp_unique_2': {"statements": []}
                    }
                },
                "w1": {"comment": ""},
                "w2": {"comment": ""}
            }
        }
    }


class SimplifiedFileSystemModel(FileSystemModel):

    entry = dict(DeviceDriverModel.entry)
    environment_models = {
        "c/p1": FileSystemModel.environment_models["c/p1"],
        "c/p2": FileSystemModel.environment_models["c/p2"],
        "c/p5": {
            "comment": "",
            "labels": {},
            "process": "(!register_p2).(<w1> | <w2>).(deregister_p2)",
            "actions": {
                "register_p2": {
                    "parameters": [],
                    "savepoints": {
                        'sp_p5': {"statements": []}
                    }
                },
                "deregister_p2": {"parameters": []},
                "w1": {"comment": ""},
                "w2": {"comment": ""}
            }
        }
    }


class FileSystemModelWithRequirements(FileSystemModel):
    environment_models = {
        "c/p1": {
            "comment": "",
            "labels": {},
            "process": "(!register_p1).<init>.(<exit> | <init_failed>)",
            "actions": {
                "register_p1": {
                    "parameters": [],
                    "savepoints": {
                        'sp1': {
                            "statements": [],
                            "require": {
                                "processes": {"c/p3": False, "c/p4": False}
                            }
                        },
                        'sp2': {
                            "statements": [],
                            "require": {
                                "processes": {"c/p2": True, "c/p3": True, "c/p4": True},
                                "actions": {
                                    "c/p2": ["success"],
                                    "c/p3": ["register_p4", "success", "create"]
                                }
                            }
                        }
                    }
                },
                "init": {"comment": ""},
                "exit": {"comment": ""},
                "init_failed": {"comment": ""}
            }
        },
        "c/p2": FileSystemModel.environment_models["c/p2"],
        "c/p3": FileSystemModel.environment_models["c/p3"],
        "c/p4": FileSystemModel.environment_models["c/p4"]
    }


class DoubleInitModel(DeviceDriverModel):
    entry = None,
    environment_models = {
        "c1/p1": {
            "comment": "Category 1, process 1.",
            "process": "(!register_c1p1).<init>.(<ok>.[register_c2p2].[deregister_c2p2] | <fail>)",
            "actions": {
                "register_c1p1": {
                    "parameters": [],
                    "savepoints": {
                        "s1": {"statements": []}
                    }
                },
                "register_c2p2": {"parameters": []},
                "deregister_c2p2": {"parameters": []},
                "init": {"coment": ""},
                "ok": {"coment": ""},
                "fail": {"coment": ""}
            }
        },
        "c1/p2": {
            "comment": "Category 1, process 1.",
            "process": "(!register_c1p2).<init>.(<ok> | <fail>)",
            "actions": {
                "register_c1p2": {
                    "parameters": [],
                    "savepoints": {
                        "basic": {"statements": []}
                    }
                },
                "init": {"coment": ""},
                "ok": {"coment": ""},
                "fail": {"coment": ""}
            }
        },
        "c2/p1": {
            "comment": "Category 2, process 1.",
            "process": "(!register_p1).<probe>.(deregister_p1)",
            "labels": {"container": {"declaration": "struct validation *var"}},
            "actions": {
                "register_p1": {
                    "parameters": ["%container%"],
                    "weak require": {
                        "processes": {"c1/p1": True, "c1/p2": True},
                        "actions": {
                            "c1/p1": ["ok"],
                            "c1/p2": ["ok"]
                        }
                    }
                },
                "deregister_p1": {"parameters": ["%container%"]},
                "probe": {"comment": ""},
            }
        },
        "c2/p2": {
            "comment": "Category 2, process 2.",
            "process": "(!register_c2p2).(<v1> | <v2>).(deregister_c2p2)",
            "actions": {
                "register_c2p2": {
                    "parameters": [],
                    "require": {
                        "processes": {"c2/p1": True},
                        "actions": {"c2/p1": ["probe"]}
                    }
                },
                "deregister_c2p2": {"parameters": []},
                "v1": {"comment": ""},
                "v2": {"comment": ""}
            }
        }
    }


class DoubleInitModelWithSavepoints(DoubleInitModel):
    environment_models = {
        "c1/p1": {
            "comment": "Category 1, process 1.",
            "process": "(!register_c1p1).<init>.(<ok>.[register_c2p2].[deregister_c2p2] | <fail>)",
            "actions": {
                "register_c1p1": {
                    "parameters": [],
                    "savepoints": {
                        "s1": {"statements": []},
                        "s2": {
                            "statements": [],
                            "require": {
                                "processes": {"c2/p1": True, "c2p2": False}
                            }
                        },
                        "s3": {
                            "statements": [],
                            "require": {
                                "processes": {"c2/p1": True, "c2p2": True}
                            }
                        },
                        "s4": {
                            "statements": [],
                            "require": {
                                "processes": {"c2/p1": True, "c2p2": True},
                                "actions": {
                                    "c2/p2": ["v1"]
                                }
                            }
                        }
                    }
                },
                "register_c2p2": {"parameters": []},
                "deregister_c2p2": {"parameters": []},
                "init": {"coment": ""},
                "ok": {"coment": ""},
                "fail": {"coment": ""}
            }
        },
        "c1/p2": DoubleInitModel.environment_models["c1/p2"],
        "c2/p1": {
            "comment": "Category 2, process 1.",
            "process": "(!register_p1).<probe>.(deregister_p1)",
            "labels": {"container": {"declaration": "struct validation *var"}},
            "actions": {
                "register_p1": {
                    "parameters": ["%container%"],
                    "require": {
                        "c1/p1": {"include": ["ok"]},
                        "c1/p2": {"include": ["ok"]}
                    },
                    "savepoints": {
                        "s5": {
                            "statements": []
                        }
                    }
                },
                "deregister_p1": {"parameters": ["%container%"]},
                "probe": {"comment": ""},
            }
        },
        "c2/p2": {
            "comment": "Category 2, process 2.",
            "process": "(!register_c2p2).(<v1>.(<v3> | <v4>) | <v2>).(deregister_c2p2)",
            "actions": {
                "register_c2p2": {
                    "parameters": [],
                    "require": {
                        "processes": {"c2/p1": True},
                        "actions": {"c2/p1": ["probe"]}
                    }
                },
                "deregister_c2p2": {"parameters": []},
                "v1": {"comment": ""},
                "v2": {"comment": ""},
                "v3": {"comment": ""},
                "v4": {"comment": ""}
            }
        }
    }


def driver_model():
    return _model_factory(DeviceDriverModel)


def driver_double_init():
    return _model_factory(DoubleInitModel)


def driver_double_init_with_deps():
    return _model_factory(DoubleInitModelWithSavepoints)


def fs_model():
    return _model_factory(FileSystemModel)


def fs_with_unique_process():
    return _model_factory(ExtendedFileSystemModel)


def fs_savepoint_deps():
    return _model_factory(FileSystemModelWithRequirements)


def fs_simplified():
    return _model_factory(SimplifiedFileSystemModel)


def _model_factory(model_class):
    """The function allows to build a model with provided processes."""
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
            "f1": model_class.f1_model,
            "f2": model_class.f2_model,
        },
        "environment processes": model_class.environment_models,
        "main process": model_class.entry
    }
    collection = CollectionDecoder(logging, dict()).parse_event_specification(source,
                                                                              json.loads(json.dumps(spec)),
                                                                              ProcessCollection())
    return collection
