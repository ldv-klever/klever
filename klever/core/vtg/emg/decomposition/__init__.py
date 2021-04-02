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
from klever.core.vtg.emg.common.c.source import Source
from klever.core.vtg.emg.common.process import ProcessCollection
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy
from klever.core.vtg.emg.decomposition.separation.linear import LinearStrategy
from klever.core.vtg.emg.decomposition.modelfactory.isolated import IsolatedFactory


#TODO: Add Python Doc
#TODO: Add Annotations
#TODO: Remove SA if it is not required
def decompose_intermediate_model(logger: Logger, conf: dict, sa: Source, model: ProcessCollection):
    if conf.get('decomposition'):
        algorythm = Decomposition(logger, conf,
                                  separator=_choose_separator(logger, conf),
                                  modelfactory=_choose_factory(logger, conf))
        # todo: At this moment do not forward the result
        for new_model in algorythm.decompose(model):
            logger.info('Generated a new model')
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
    # todo: At the moment this is the only option
    return IsolatedFactory(logger, conf)


class Decomposition:

    def __init__(self, logger, conf, separator, modelfactory):
        self.logger = logger
        self.conf = conf
        self.separator = separator
        self.modelfactory = modelfactory

    def decompose(self, model: ProcessCollection):
        processes = set()
        # We do not add kernel models to reduce the number of resulted models and scenarios but in general it should
        # be possible
        processes.add(model.entry)
        processes.update(model.environment)

        processes_to_scenarios = dict()
        for process in processes:
            scenarios = self.separator(process)
            self.logger.debug(f'Generated {len(scenarios)} scenarios for the process {str(process)}')
            processes_to_scenarios[process] = scenarios

        for model in self.modelfactory.generate_models(processes_to_scenarios):
            yield model
