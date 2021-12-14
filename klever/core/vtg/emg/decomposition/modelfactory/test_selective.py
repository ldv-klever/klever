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
import logging
from klever.core.vtg.emg.decomposition.separation.reqs import ReqsStrategy
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy
from klever.core.vtg.emg.decomposition.separation.linear import LinearStrategy
from klever.core.vtg.emg.decomposition.modelfactory.selective import SelectiveFactory
import klever.core.vtg.emg.decomposition.modelfactory.decomposition_models as models


@pytest.fixture()
def model():
    return models.driver_model()


@pytest.fixture()
def advanced_model():
    return models.fs_model()


@pytest.fixture()
def advanced_model_with_unique():
    return models.fs_with_unique_process()


@pytest.fixture()
def model_with_independent_process():
    return models.fs_simplified()


@pytest.fixture()
def double_init_model():
    return models.driver_double_init()


@pytest.fixture()
def fs_deps_model():
    return models.fs_savepoint_deps()


@pytest.fixture()
def fs_init_deps_model():
    return models.fs_savepoint_init_deps()


@pytest.fixture()
def logger():
    logger = logging.getLogger(__name__)
    # todo: Uncomment when you will need a log or implement ini file
    # logger.setLevel(logging.DEBUG)
    # handler = logging.StreamHandler(sys.stdout)
    # handler.setLevel(logging.DEBUG)
    # logger.addHandler(handler)
    return logger


def _obtain_model(logger, model, specification):
    separation = SelectiveFactory(logger, specification)
    scenario_generator = SeparationStrategy(logger, dict())
    processes_to_scenarios = {str(process): list(scenario_generator(process, model))
                              for process in model.non_models.values()}
    return processes_to_scenarios, list(separation(processes_to_scenarios, model))


def _obtain_linear_model(logger, model, specification, separate_dispatches=False):
    separation = SelectiveFactory(logger, specification)
    scenario_generator = LinearStrategy(logger, dict() if not separate_dispatches else
                                                {'add scenarios without dispatches': True})
    processes_to_scenarios = {str(process): list(scenario_generator(process, model))
                              for process in model.non_models.values()}
    return processes_to_scenarios, list(separation(processes_to_scenarios, model))


def _obtain_reqs_model(logger, model, specification, separate_dispatches=False):
    separation = SelectiveFactory(logger, specification)
    scenario_generator = ReqsStrategy(logger, dict() if not separate_dispatches else
                                                {'add scenarios without dispatches': True})
    processes_to_scenarios = {str(process): list(scenario_generator(process, model))
                              for process in model.non_models.values()}
    return processes_to_scenarios, list(separation(processes_to_scenarios, model))


def _to_sorted_attr_str(attrs):
    return ", ".join(f"{k}: {attrs[k]}" for k in sorted(attrs.keys()))


def _expect_models_with_attrs(models, attributes):
    model_attrs = {_to_sorted_attr_str(m.attributes) for m in models}
    attrs = {_to_sorted_attr_str(attrs) for attrs in attributes}

    unexpected = model_attrs.difference(attrs)
    assert len(unexpected) == 0, f"There are unexpected models: {unexpected}"

    missing = attrs.difference(model_attrs)
    assert len(missing) == 0, f"There are missing models: {missing}"


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
    for model in models:
        if model.entry.actions == c2p2_withsavepoint.actions:
            assert False, f"Model {model.attributed_name} has a savepoint from p2"


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


def test_controversial_conditions1(logger, model):
    spec = {
        "must contain": {"c/p2": {}},
        "must not contain": {"c/p1": {}},
        "cover scenarios": {"c/p1": {}}
    }
    with pytest.raises(ValueError):
        processes_to_scenarios, models = _obtain_linear_model(logger, model, spec)


def test_controversial_conditions2(logger, model):
    spec = {
        "must contain": {"c/p2": {}},
        "must not contain": {"c/p1": {}, "c/p2": {"savepoints": ["s2"]}},
        "cover scenarios": {"c/p2": {}}
    }
    with pytest.raises(ValueError):
        processes_to_scenarios, models = _obtain_linear_model(logger, model, spec)
        pass


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

    # Test that there is a p1 model in models
    actions = [m.environment['c/p1'].actions for m in models if 'c/p1' in m.environment] + \
              [m.entry.actions for m in models if 'c/p1' not in m.environment]

    # Test all scenarios of p1 are covered
    assert len(actions) == len(relevant_scenarios)
    for scenario_actions in relevant_scenarios:
        assert scenario_actions in actions


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


def test_combinations_with_transitive_dependencies(logger, advanced_model):
    spec = {
        "must contain": {"c/p3": {}},
        "cover scenarios": {"c/p3": {"actions": ["create2", "success"]}}
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, advanced_model, spec)

    p3scenarios = {s for s in processes_to_scenarios['c/p3'] if {"create2", "success"}.issubset(set(s.actions.keys()))}
    assert len(p3scenarios) == len(models)
    actions = [m.environment['c/p3'].actions for m in models if 'c/p3' in m.environment] + \
              [m.entry.actions for m in models]
    for scenario in p3scenarios:
        assert scenario.actions in actions


def test_savepoints_with_deps(logger, advanced_model):
    spec = {
        "cover scenarios": {
            "c/p1": {"savepoints only": True}
        }
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, advanced_model, spec)

    p1scenarios = {s for s in processes_to_scenarios['c/p1'] if s.savepoint}
    assert len(models) == len(p1scenarios)
    names = [m.attributes['c/p1'] for m in models]
    for scenario in p1scenarios:
        assert scenario.name in names


def test_savepoints_with_mc_deps(logger, advanced_model):
    spec = {
        "must contain": {"c/p3": {}},
        "cover scenarios": {
            "c/p1": {"savepoints only": True},
            "c/p3": {"actions": ["create2", "success"], "savepoints": []}
        }
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, advanced_model, spec)

    p1scenarios = {s for s in processes_to_scenarios['c/p1'] if s.savepoint and 'exit' in s.actions}
    assert len(models) == len(p1scenarios)
    names = [m.attributes['c/p1'] for m in models]
    for scenario in p1scenarios:
        assert scenario.name in names


def test_combinations_with_savepoints_only(logger, advanced_model):
    spec = {
        "cover scenarios": {
            "c/p1": {"savepoints only": True},
            "c/p3": {"actions": ["create2", "success"], "savepoints only": True}}
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, advanced_model, spec)

    p1scenarios = {s for s in processes_to_scenarios['c/p1'] if s.savepoint}
    p3scenarios = {s for s in processes_to_scenarios['c/p3']
                   if s.savepoint and {"create2", "success"}.issubset(set(s.actions.keys()))}
    assert len(models) == (len(p1scenarios) + len(p3scenarios))
    names = [m.attributes['c/p1'] for m in models if m.attributes.get('c/p1')]
    for scenario in p1scenarios:
        assert scenario.name in names
    names = [m.attributes['c/p3'] for m in models if m.attributes.get('c/p3')]
    for scenario in p3scenarios:
        assert scenario.name in names


def test_combinations_with_extra_dependencies(logger, advanced_model):
    spec = {
        "cover scenarios": {"c/p2": {}, "c/p3": {"actions": ["create2", "success"], "savepoints only": True}}
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, advanced_model, spec)

    # Cover all scenarios from p1
    p3scenarios = {s for s in processes_to_scenarios['c/p3']
                   if s.savepoint and {"create2", "success"}.issubset(set(s.actions.keys()))}
    p2scenarios = {s for s in processes_to_scenarios['c/p2']}
    assert len(models) <= (len(p3scenarios) + len(p2scenarios))
    names = [m.attributes['c/p3'] for m in models if m.attributes.get('c/p3')]
    for scenario in p3scenarios:
        assert scenario.name in names
    names = [m.attributes['c/p2'] for m in models if m.attributes.get('c/p2')]
    for scenario in p2scenarios:
        assert scenario.name in names


def test_savepoints_only_with_deps(logger, advanced_model):
    spec = {
        "cover scenarios": {
            "c/p1": {"savepoints only": True},
            "c/p3": {"actions": ["create2", "success"]}
        }
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, advanced_model, spec)

    p1scenarios = {s for s in processes_to_scenarios['c/p1'] if s.savepoint}
    p3scenarios = {s for s in processes_to_scenarios['c/p3']
                   if s.savepoint and {"create2", "success"}.issubset(set(s.actions.keys()))}
    p1scenarios_for_p3 = {s for s in processes_to_scenarios['c/p1'] if s.savepoint and "exit" in s.actions}
    assert len(models) <= (len(p1scenarios) + len(p1scenarios_for_p3) + len(p3scenarios))
    names = [m.attributes['c/p3'] for m in models if m.attributes.get('c/p3')]
    for scenario in p3scenarios:
        assert scenario.name in names
    names = [m.attributes['c/p1'] for m in models if m.attributes.get('c/p2')]
    for scenario in p1scenarios:
        assert scenario.name in names


def test_savepoints_without_base_actions(logger, advanced_model):
    spec = {
        "cover scenarios": {
            "c/p1": {"actions": ["exit"], "savepoints only": True},
            "c/p3": {"actions": ["create2", "success"], "savepoints only": True}
        }
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, advanced_model, spec)

    p1scenarios = {s for s in processes_to_scenarios['c/p1'] if s.savepoint and
                   {"exit"}.issubset(set(s.actions.keys()))}
    p3scenarios = {s for s in processes_to_scenarios['c/p3']
                   if s.savepoint and {"create2", "success"}.issubset(set(s.actions.keys()))}
    assert len(models) <= (len(p1scenarios) + len(p3scenarios))
    names = [m.attributes['c/p3'] for m in models if m.attributes.get('c/p3')]
    for scenario in p3scenarios:
        assert scenario.name in names
    names = [m.attributes['c/p1'] for m in models if m.attributes.get('c/p2')]
    for scenario in p1scenarios:
        assert scenario.name in names


def test_all_process_savepoints_and_actions_without_base(logger, advanced_model):
    spec = {
        "cover scenarios": {
            "c/p1": {"savepoints only": True},
            "c/p2": {},
            "c/p3": {"savepoints only": True},
            "c/p4": {}
        }
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, advanced_model, spec, separate_dispatches=True)
    # Check attributes
    for model in models:
        assert len(model.attributes) == 4

    s1 = {s for s in processes_to_scenarios['c/p1'] if s.savepoint}
    s3 = {s for s in processes_to_scenarios['c/p3'] if s.savepoint}
    s2 = set(processes_to_scenarios['c/p2'])
    s4 = set(processes_to_scenarios['c/p4'])
    names = ['c/p1', 'c/p2', 'c/p3', 'c/p4']

    for name, scenarios in zip(names, [s1, s2, s3, s4]):
        model_scenarios = {m.attributes[name] for m in models}
        assert {s.name for s in scenarios}.issubset(model_scenarios)


def test_advanced_model_with_unique_processes(logger, advanced_model_with_unique):
    spec = {
        "cover scenarios": {
            "c/p6": {"savepoints only": True}
        }
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, advanced_model_with_unique, spec,
                                                          separate_dispatches=True)
    model_attrs = {_to_sorted_attr_str(m.attributes) for m in models}
    expected = [
        {"c/p1": "Removed", "c/p2": "Removed", "c/p3": "Removed", "c/p4": "Removed", "c/p6": "sp_unique_2 with w2"},
        {"c/p1": "Removed", "c/p2": "Removed", "c/p3": "Removed", "c/p4": "Removed", "c/p6": "sp_unique_2 with w1"},
        {"c/p1": "Removed", "c/p2": "Removed", "c/p3": "Removed", "c/p4": "Removed", "c/p6": "sp_unique_1 with w2"},
        {"c/p1": "Removed", "c/p2": "Removed", "c/p3": "Removed", "c/p4": "Removed", "c/p6": "sp_unique_1 with w1"}
    ]
    _expect_models_with_attrs(models, expected)


def test_process_without_deps(logger, model_with_independent_process):
    spec = {
        "must not contain": {"c/p1": {"savepoints": ["sp_init_first", "sp_init_second", "sp_init_third"]}},
        "cover scenarios": {
            "c/p5": {}
        }
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, model_with_independent_process, spec,
                                                          separate_dispatches=True)
    p5scenarios = set(processes_to_scenarios['c/p5'])
    assert len(models) == len(p5scenarios)
    names = [m.attributes['c/p5'] for m in models if m.attributes.get('c/p5')]
    for scenario in p5scenarios:
        assert scenario.name in names


def test_process_ignoring_free_process(logger, model_with_independent_process):
    spec = {
        "cover scenarios": {
            "c/p1": {"savepoints only": True},
            "c/p2": {"actions": ["fail"]}
        }
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, model_with_independent_process, spec,
                                                          separate_dispatches=True)
    s1 = {s for s in processes_to_scenarios['c/p1'] if s.savepoint}
    s3 = {s for s in processes_to_scenarios['c/p2'] if 'fail' in s.actions}
    assert len(models) == len(s1)
    names = [m.attributes['c/p1'] for m in models if m.attributes.get('c/p1')]
    for scenario in s1:
        assert scenario.name in names
    names = [m.attributes['c/p2'] for m in models if m.attributes.get('c/p2')]
    for scenario in s3:
        assert scenario.name in names


def test_combine_free_and_dependent_processes(logger, model_with_independent_process):
    spec = {
        "cover scenarios": {
            "c/p5": {},
            "c/p2": {"actions": ["fail"]}
        }
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, model_with_independent_process, spec,
                                                          separate_dispatches=True)
    s5 = {s for s in processes_to_scenarios['c/p5']}
    s2 = {s for s in processes_to_scenarios['c/p2'] if 'fail' in s.actions}
    assert len(models) == len(s5)
    names = [m.attributes['c/p5'] for m in models if m.attributes.get('c/p5')]
    for scenario in s5:
        assert scenario.name in names
    names = [m.attributes['c/p2'] for m in models if m.attributes.get('c/p2')]
    for scenario in s2:
        assert scenario.name in names


def test_double_sender_model_single_init(logger, double_init_model):
    spec = {
        "cover scenarios": {
            "c1/p1": {"savepoints only": True},
            "c2/p2": {}
        }
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, double_init_model, spec)
    expected = [
        {'c2/p2': 'Removed', 'c2/p1': 'Removed', 'c1/p1': 's1 with fail', 'c1/p2': 'Removed'},
        {'c2/p2': 'v1', 'c1/p1': 's1 with ok', 'c2/p1': 'base', 'c1/p2': 'Removed'},
        {'c2/p2': 'v2', 'c1/p1': 's1 with ok', 'c2/p1': 'base', 'c1/p2': 'Removed'}
    ]
    _expect_models_with_attrs(models, expected)


def test_double_sender_model(logger, double_init_model):
    spec = {
        "cover scenarios": {
            "c1/p1": {"savepoints only": True},
            "c1/p2": {"savepoints only": True},
            "c2/p2": {}
        }
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, double_init_model, spec)
    expected = [
        {'c2/p2': 'Removed', 'c1/p1': 'Removed', 'c2/p1': 'Removed', 'c1/p2': 'basic with fail'},
        {'c2/p2': 'Removed', 'c2/p1': 'base', 'c1/p1': 'Removed', 'c1/p2': 'basic with ok'},
        {'c2/p2': 'Removed', 'c2/p1': 'Removed', 'c1/p1': 's1 with fail', 'c1/p2': 'Removed'},
        {'c2/p2': 'v1', 'c1/p1': 's1 with ok', 'c1/p2': 'Removed', 'c2/p1': 'base'},
        {'c2/p2': 'v2', 'c1/p1': 's1 with ok', 'c1/p2': 'Removed', 'c2/p1': 'base'}
    ]
    _expect_models_with_attrs(models, expected)


def test_double_sender_model_full_list(logger, double_init_model):
    spec = {
        "cover scenarios": {
            "c1/p1": {"savepoints only": True},
            "c1/p2": {"savepoints only": True},
            "c2/p1": {},
            "c2/p2": {}
        }
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, double_init_model, spec)
    expected = [
        {'c2/p2': 'Removed', 'c2/p1': 'Removed', 'c1/p1': 'Removed', 'c1/p2': 'basic with fail'},
        {'c2/p2': 'Removed', 'c2/p1': 'base', 'c1/p1': 'Removed', 'c1/p2': 'basic with ok'},
        {'c2/p2': 'Removed', 'c2/p1': 'Removed', 'c1/p1': 's1 with fail', 'c1/p2': 'Removed'},
        {'c2/p2': 'v1', 'c2/p1': 'base', 'c1/p1': 's1 with ok', 'c1/p2': 'Removed'},
        {'c2/p2': 'v2', 'c2/p1': 'base', 'c1/p1': 's1 with ok', 'c1/p2': 'Removed'}
    ]
    _expect_models_with_attrs(models, expected)


def test_fs_reqs_linear(logger, fs_deps_model):
    spec = {
        "cover scenarios": {
            "c/p1": {"savepoints only": True}
        }
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, fs_deps_model, spec)
    expected = [
        {"c/p1": "sp1 with exit", "c/p2": "deregister_p2", "c/p3": "Removed", "c/p4": "Removed"},
        {"c/p1": "sp2 with exit", "c/p2": "success_probe_deregister_p2", "c/p3": "create_scenario_p4_scenario_success", "c/p4": "base"},
        {"c/p1": "sp1 with init_failed", "c/p2": "Removed", "c/p3": "Removed", "c/p4": "Removed"},
        {'c/p1': 'sp5 with exit', 'c/p4': 'base', 'c/p3': 'create_scenario_p4_scenario_success',
         'c/p2': 'success_probe_deregister_p2'}
    ]
    _expect_models_with_attrs(models, expected)


def test_fs_reqs_linear_p3(logger, fs_deps_model):
    spec = {
        "cover scenarios": {
            "c/p3": {"savepoints only": True}
        }
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, fs_deps_model, spec)
    expected = [
        {'c/p3': 'sp3 with create_scenario_p4_scenario_success', 'c/p4': 'base', 'c/p2': 'Removed', 'c/p1': 'Removed'},
        {'c/p3': 'sp4 with create_scenario_p4_scenario_success', 'c/p4': 'Removed', 'c/p2': 'Removed',
         'c/p1': 'Removed'}
    ]
    _expect_models_with_attrs(models, expected)


def test_fs_reqs_p1(logger, fs_deps_model):
    spec = {
        "cover scenarios": {
            "c/p1": {"savepoints only": True}
        }
    }
    processes_to_scenarios, models = _obtain_reqs_model(logger, fs_deps_model, spec)
    # todo: hmm, maybe it is required to have scenario with s5 there
    expected = [
        {'c/p1': 'sp1 with base', 'c/p4': 'Removed', 'c/p3': 'Removed', 'c/p2': 'Removed'},
        {'c/p1': 'sp2 with base', 'c/p4': 'base for sp2', 'c/p3': 'register_p4_success_create for sp2',
         'c/p2': 'success for sp2'}
    ]
    _expect_models_with_attrs(models, expected)


def test_fs_reqs_p3(logger, fs_deps_model):
    spec = {
        "cover scenarios": {
            "c/p3": {"savepoints only": True}
        }
    }
    processes_to_scenarios, models = _obtain_reqs_model(logger, fs_deps_model, spec)
    expected = [
        {'c/p3': 'sp3 with base', 'c/p4': 'base for sp3', 'c/p2': 'Removed', 'c/p1': 'Removed'},
        {'c/p3': 'sp4 with register_p4', 'c/p4': 'Removed', 'c/p2': 'Removed', 'c/p1': 'Removed'}
    ]
    _expect_models_with_attrs(models, expected)


def test_fs_reqs_init_linear(logger, fs_init_deps_model):
    spec = {
        "cover scenarios": {
            "entry_point/main": {"savepoints only": True}
        }
    }
    processes_to_scenarios, models = _obtain_linear_model(logger, fs_init_deps_model, spec)
    expected = [
        {'c/p2': 'success_probe_deregister_p2', 'c/p3': 'create_scenario_p4_scenario_success', 'c/p4': 'base',
         'entry_point/main': 'sp5 with exit'},
        {'c/p2': 'success_probe_deregister_p2', 'c/p3': 'create_scenario_p4_scenario_success', 'c/p4': 'base',
         'entry_point/main': 'sp2 with exit'},
        {'c/p2': 'deregister_p2', 'c/p3': 'Removed', 'c/p4': 'Removed', 'entry_point/main': 'sp1 with exit'},
        {'c/p2': 'Removed', 'c/p3': 'Removed', 'c/p4': 'Removed', 'entry_point/main': 'sp1 with init_failed'}
    ]
    _expect_models_with_attrs(models, expected)


def test_fs_reqs_init_cover_init(logger, fs_init_deps_model):
    spec = {
        "cover scenarios": {
            "c/p3": {"savepoints only": True}
        }
    }
    processes_to_scenarios, models = _obtain_reqs_model(logger, fs_init_deps_model, spec)
    expected = [
        {'c/p3': 'sp3 with base', 'c/p4': 'base for sp3', 'c/p2': 'Removed', 'entry_point/main': 'Removed'},
        {'c/p3': 'sp4 with register_p4', 'c/p4': 'Removed', 'c/p2': 'Removed', 'entry_point/main': 'Removed'}
    ]
    _expect_models_with_attrs(models, expected)
