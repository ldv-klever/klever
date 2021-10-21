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

from logging import Logger
from klever.core.vtg.emg.common.process import ProcessCollection
from klever.core.vtg.emg.decomposition.modelfactory import ModelFactory
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy
from klever.core.vtg.emg.decomposition.separation.linear import LinearStrategy
from klever.core.vtg.emg.decomposition.modelfactory.selective import SelectiveFactory
from klever.core.vtg.emg.decomposition.modelfactory.combinatorial import CombinatorialFactory


def decompose_intermediate_model(logger: Logger, conf: dict, model: ProcessCollection):
    """
    Decompose the given environment model.

    :param logger: Logger obj.
    :param conf: Dictionary with EMG configuration.
    :param model: ProcessCollection obj.
    :return: An iterator over models.
    """
    if not conf.get('single environment model per fragment', True):
        logger.info(f"Decompose environment model '{model.name}'")
        algorithm = Decomposition(logger, conf,
                                  model=model,
                                  separator=_choose_separator(logger, conf),
                                  factory=_choose_factory(logger, conf))
        for new_model in algorithm():
            logger.info(f"Generated a new model '{new_model.attributed_name}'")
            yield new_model
    else:
        logger.info(f"Do not decompose the provided model '{model.name}'")
        yield model


def _choose_separator(logger, conf):
    if conf.get('scenario separation') == 'linear':
        logger.info("Split processes into linear sequences of actions")
        return LinearStrategy(logger, conf)
    else:
        logger.info("Do not split processes at separation stage of model decomposition")
        return SeparationStrategy(logger, conf)


def _choose_factory(logger, conf):
    if isinstance(conf.get('select scenarios'), str) and conf['select scenarios'] == 'use all scenarios combinations' :
        logger.info("Choose the combinatorial factory")
        return CombinatorialFactory(logger, conf)
    elif isinstance(conf.get('select scenarios'), dict):
        if 'cover scenarios' not in conf['select scenarios']:
            raise ValueError("Provide configuration parameter 'cover scenarios' inside 'select scenarios'")
        conf.update(conf.get('select scenarios', dict()))
        logger.info("Activate the selection of scenarios according to the provided configuration")
        return SelectiveFactory(logger, conf)
    else:
        logger.info("Choose the default model factory")
        return ModelFactory(logger, conf)


class Decomposition:

    def __init__(self, logger, conf, model, separator, factory):
        self.logger = logger
        self.conf = conf
        self.model = model
        self.separator = separator
        self.modelfactory = factory

    def __call__(self, *args, **kwargs):
        processes_to_scenarios = dict()
        self.logger.info("Generating models ...")
        for process in self.model.environment.values():
            scenarios = list(self.separator(process))
            self.logger.debug(f"Generated {len(scenarios)} scenarios for the process '{str(process)}'")
            processes_to_scenarios[str(process)] = scenarios

        yield from self.modelfactory(processes_to_scenarios, self.model)
