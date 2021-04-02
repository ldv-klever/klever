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

from logging import Logger
from klever.core.vtg.emg.common.process import ProcessCollection
from klever.core.vtg.emg.decomposition.modelfactory import ModelFactory
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy
from klever.core.vtg.emg.decomposition.separation.linear import LinearStrategy


#TODO: Add Python Doc
#TODO: Add Annotations
def decompose_intermediate_model(logger: Logger, conf: dict, model: ProcessCollection):
    if conf.get('decomposition'):
        algorythm = Decomposition(logger, conf,
                                  model=model,
                                  separator=_choose_separator(logger, conf),
                                  modelfactory=_choose_factory(logger, conf))
        for new_model in algorythm():
            logger.info(f'Generated a new model {new_model.name}')
            yield new_model
    else:
        return [model]


def _choose_separator(logger, conf):
    if conf.get('scenario separation') == 'linear':
        logger.info('Split processes into lienar sequences of actions')
        return LinearStrategy(logger, conf)
    else:
        logger.info('Do not split processes at separation stage of model decomposition')
        return SeparationStrategy(logger, conf)


def _choose_factory(logger, conf):
    # TODO: Implement an option that cover different scenarios not only SP
    return ModelFactory(logger, conf)


class Decomposition:

    def __init__(self, logger, conf, model, separator, modelfactory):
        self.logger = logger
        self.conf = conf
        self.model = model
        self.separator = separator
        self.modelfactory = modelfactory

    def __call__(self, *args, **kwargs):
        processes_to_scenarios = dict()
        for process in self.model.environment.values():
            scenarios = list(self.separator(process))
            self.logger.debug(f'Generated {len(scenarios)} scenarios for the process {str(process)}')
            processes_to_scenarios[str(process)] = scenarios

        yield from self.modelfactory(processes_to_scenarios, self.model)
