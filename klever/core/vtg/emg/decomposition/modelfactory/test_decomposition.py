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

from klever.core.vtg.emg.decomposition.modelfactory import ModelFactory
from klever.core.vtg.emg.decomposition.separation.reqs import ReqsStrategy
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy
from klever.core.vtg.emg.common.process.model_for_testing import model_preset
from klever.core.vtg.emg.decomposition.modelfactory.savepoints import SavepointsFactory
import klever.core.vtg.emg.decomposition.modelfactory.decomposition_models as test_models


@pytest.fixture
def base_model():
    return model_preset()


@pytest.fixture()
def driver_model():
    return test_models.driver_model()


@pytest.fixture()
def fs_deps_model():
    return test_models.fs_savepoint_deps()


@pytest.fixture()
def fs_init_deps_model():
    return test_models.fs_savepoint_init_deps()


@pytest.fixture()
def double_init_with_deps_model():
    return test_models.driver_double_init_with_deps()


@pytest.fixture()
def logger():
    logger = logging.getLogger(__name__)
    return logger


# def _obtain_model(logger, model, specification):
#     separation = CombinatorialFactory(logger, specification)
#     scenario_generator = SeparationStrategy(logger, dict())
#     processes_to_scenarios = {str(process): list(scenario_generator(process, model))
#                               for process in model.environment.values()}
#     return processes_to_scenarios, list(separation(processes_to_scenarios, model))
#
#
# def _obtain_linear_model(logger, model, specification, separate_dispatches=False):
#     separation = CombinatorialFactory(logger, specification)
#     scenario_generator = LinearStrategy(logger, dict() if not separate_dispatches else
#     {'add scenarios without dispatches': True})
#     processes_to_scenarios = {str(process): list(scenario_generator(process, model))
#                               for process in model.environment.values()}
#     return processes_to_scenarios, list(separation(processes_to_scenarios, model))


def _obtain_reqs_model(logger, model, specification, separate_dispatches=False):
    separation = SavepointsFactory(logger, specification)
    scenario_generator = ReqsStrategy(logger, dict() if not separate_dispatches else
    {'add scenarios without dispatches': True})
    processes_to_scenarios = {str(process): list(scenario_generator(process, model))
                              for process in model.non_models.values()}
    return processes_to_scenarios, list(separation(processes_to_scenarios, model))


def test_default_models(base_model):
    separation = ModelFactory(logging.Logger('default'), {})
    scenario_generator = SeparationStrategy(logging.Logger('default'), dict())
    processes_to_scenarios = {str(process): list(scenario_generator(process, base_model))
                              for process in base_model.non_models.values()}
    models = list(separation(processes_to_scenarios, base_model))

    cnt = 1  # Original model
    for process in base_model.non_models.values():
        for action_name in process.actions.first_actions():
            action = process.actions[action_name]
            cnt += len(action.savepoints) if hasattr(action, 'savepoints') and action.savepoints else 0
    assert len(models) == cnt

    # Compare processes itself
    for new_model in models:
        assert len(list(new_model.models.keys())) > 0
        assert len(list(new_model.environment.keys())) > 0 or new_model.entry

        for name, process in base_model.environment.items():
            if name in new_model.environment:
                for label in process.labels:
                    # Check labels
                    assert label in new_model.environment[name].labels, f'Missing label {label}'

                assert new_model.environment[name].actions
            elif new_model.name in process.actions.savepoints:
                for label in process.labels:
                    # Check labels
                    assert label in new_model.entry.labels, f'Missing label {label}'

                assert new_model.entry.actions

# todo: These features are unsupported yet
# def test_inclusion_p1(logger, driver_model):
#     spec = {
#         "must contain": {"c/p1": {}}
#     }
#     processes_to_scenarios, models = _obtain_linear_model(logger, driver_model, spec)
#
#     # Cover all scenarios from c2p1
#     p1scenarios = processes_to_scenarios['c/p1']
#     p2scenarios = {s for s in processes_to_scenarios['c/p2'] if not s.savepoint}
#     assert (len(p1scenarios) + len(p2scenarios)) == len(models)
#     actions = [m.environment['c/p1'].actions for m in models if 'c/p1' in m.environment] + \
#               [m.entry.actions for m in models]
#     for scenario in p1scenarios:
#         assert scenario.actions in actions
#
#     # No savepoints from c2p2
#     c2p2_withsavepoint = [s for s in processes_to_scenarios['c/p2'] if s.savepoint].pop()
#     for driver_model in models:
#         if driver_model.entry.actions == c2p2_withsavepoint.actions:
#             assert False, f"Model {driver_model.attributed_name} has a savepoint from p2"
#
#
# def test_deletion(logger, model):
#     spec = {
#         "must not contain": {"c/p2": {}}
#     }
#     processes_to_scenarios, models = _obtain_linear_model(logger, model, spec)
#
#     # Cover all scenarios from p1
#     p1scenarios = {s for s in processes_to_scenarios['c/p1']}
#     assert len(p1scenarios) == len(models)
#     actions = [m.environment['c/p1'].actions for m in models if 'c/p1' in m.environment] + \
#               [m.entry.actions for m in models]
#     for scenario in p1scenarios:
#         assert scenario.actions in actions
#
#     # No savepoints from p2
#     p2_withsavepoint = [s for s in processes_to_scenarios['c/p2'] if s.savepoint].pop()
#     assert all([True if p2_withsavepoint.actions != m.entry.actions else False for m in models])
#
#     # No other actions
#     for model in models:
#         assert 'c/p2' not in model.environment


def test_fs_reqs(logger, fs_deps_model):
    spec = {}
    processes_to_scenarios, models = _obtain_reqs_model(logger, fs_deps_model, spec)
    expected = [
        {'c/p1': 'sp1 with base', 'c/p4': 'Removed', 'c/p3': 'Removed', 'c/p2': 'base'},
        {'c/p1': 'sp2 with base', 'c/p4': 'base for sp2', 'c/p3': 'register_p4_success_create for sp2',
         'c/p2': 'success for sp2'},
        {'c/p3': 'sp3 with base', 'c/p4': 'base for sp3', 'c/p2': 'Removed', 'c/p1': 'Removed'},
        {'c/p3': 'sp4 with register_p4', 'c/p4': 'Removed', 'c/p2': 'Removed', 'c/p1': 'Removed'},
        {'c/p1': 'sp5 with base', 'c/p4': 'base for sp5', 'c/p2': 'base', 'c/p3': 'base'}
    ]
    _expect_models_with_attrs(models, expected)


def test_fs_init_reqs(logger, fs_init_deps_model):
    spec = {}
    processes_to_scenarios, models = _obtain_reqs_model(logger, fs_init_deps_model, spec)
    expected = [
        {'entry_point/main': 'sp1 with base', 'c/p4': 'Removed', 'c/p3': 'Removed', 'c/p2': 'base'},
        {'entry_point/main': 'sp2 with exit', 'c/p4': 'base for sp2', 'c/p3': 'register_p4_success_create for sp2',
         'c/p2': 'success for sp2'},
        {'c/p3': 'sp3 with base', 'c/p4': 'base for sp3', 'c/p2': 'Removed', 'entry_point/main': 'Removed'},
        {'c/p3': 'sp4 with register_p4', 'c/p4': 'Removed', 'c/p2': 'Removed', 'entry_point/main': 'Removed'},
        {'entry_point/main': 'sp5 with base', 'c/p4': 'base for sp5', 'c/p2': 'base', 'c/p3': 'base'}
    ]
    _expect_models_with_attrs(models, expected)


def test_double_init_reqs(logger, double_init_with_deps_model):
    spec = {}
    processes_to_scenarios, models = _obtain_reqs_model(logger, double_init_with_deps_model, spec)
    expected = [
        {'c1/p1': 's1 with base', 'c1/p2': 'Removed', 'c2/p1': 'base', 'c2/p2': 'base'},
        {'c1/p1': 's2 with base', 'c2/p1': 'base for s2', 'c2/p2': 'Removed', 'c1/p2': 'Removed'},
        {'c1/p1': 's3 with base', 'c2/p1': 'base for s3', 'c2/p2': 'base for s3', 'c1/p2': 'Removed'},
        {'c1/p1': 's4 with base', 'c2/p1': 'base for s4', 'c2/p2': 'v1 for s4', 'c1/p2': 'Removed'},
        {'c1/p2': 'basic with base', 'c1/p1': 'Removed', 'c2/p2': 'Removed', 'c2/p1': 'base'},
        {'c2/p1': 's5 with base', 'c1/p1': 'Removed', 'c2/p2': 'Removed', 'c1/p2': 'Removed'}
    ]
    _expect_models_with_attrs(models, expected)


def test_double_init_selected(logger, double_init_with_deps_model):
    spec = {
        "savepoints": {
            "c1/p1": ["s1"],
            "c2/p1": True
        }
    }
    processes_to_scenarios, models = _obtain_reqs_model(logger, double_init_with_deps_model, spec)
    expected = [
        {'c1/p1': 's1 with base', 'c1/p2': 'Removed', 'c2/p1': 'base', 'c2/p2': 'base'},
        {'c2/p1': 's5 with base', 'c1/p1': 'Removed', 'c2/p2': 'Removed', 'c1/p2': 'Removed'}
    ]
    _expect_models_with_attrs(models, expected)


def _to_sorted_attr_str(attrs):
    return ", ".join(f"{k}: {attrs[k]}" for k in sorted(attrs.keys()))


def _expect_models_with_attrs(models, attributes):
    model_attrs = {_to_sorted_attr_str(m.attributes) for m in models}
    attrs = {_to_sorted_attr_str(attrs) for attrs in attributes}

    unexpected = model_attrs.difference(attrs)
    assert len(unexpected) == 0, f"There are unexpected models: {unexpected}"

    missing = attrs.difference(model_attrs)
    assert len(missing) == 0, f"There are missing models: {missing}"

