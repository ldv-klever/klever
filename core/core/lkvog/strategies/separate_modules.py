#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

from core.lkvog.strategies.strategy_utils import Module, Graph
from core.lkvog.strategies.abstract_strategy import AbstractStrategy


class SeparateModules(AbstractStrategy):
    def __init__(self, logger, strategy_params, params):
        super().__init__(logger)

    def divide(self, module_name):
        if module_name.endswith('.o'):
            return [Graph([Module(module_name)])]
        else:
            return []
