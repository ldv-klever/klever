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
from klever.core.vtg.emg.decomposition.separation.linear import LinearStrategy
from klever.core.vtg.emg.common.process.model_for_testing import model_preset_c2
from klever.core.vtg.emg.decomposition.modelfactory.selective import SelectiveFactory


@pytest.fixture()
def model():
    return model_preset_c2


def test_first(model):
    spec = {
        "must contain": {"c2/p2": {}},
        "cover scenarios": {"c2/p2": {}}
    }
    processes_to_scenarios, models = _obtain_models(model, spec)
    
    # todo: Cover all c2p2 scenarios
    assert False


def test_second(model):
    spec = {
        "must contain": {"c2/p1": {}},
        "cover scenarios": {"c2/p1": {}}
    }
    processes_to_scenarios, models = _obtain_models(model, spec)

    # todo: Cover all scenarios from c2p1
    # todo: No savepoints from c2p2
    assert False


def test_third(model):
    spec = {
        "must contain": {"c2/p2": {"actions": [["read"]]}},
        "must not contain": {"c2/p1": {"savepoints": [["c2p1s1"]]}},
        "cover scenarios": {"c2/p2": {}}
    }
    processes_to_scenarios, models = _obtain_models(model, spec)

    # todo: Cover only scenarios with read from p2
    # todo: Not scenarios with a savepoint c2p1s1
    assert False


def _obtain_models(model, specification):
    separation = SelectiveFactory(logging.Logger('default'), specification)
    scenario_generator = LinearStrategy(logging.Logger('default'), dict())
    processes_to_scenarios = {str(process): list(scenario_generator(process)) for process in model.environment.values()}
    return processes_to_scenarios, list(separation(processes_to_scenarios, model))
