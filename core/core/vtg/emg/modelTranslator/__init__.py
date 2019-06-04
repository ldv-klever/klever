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

import os

from core.vtg.emg.common import get_conf_property, check_or_set_conf_property, get_necessary_conf_property
from core.vtg.emg.modelTranslator.code import CModel
from core.vtg.emg.modelTranslator.fsa import Automaton
from core.vtg.emg.modelTranslator.fsa_translator.label_fsa_translator import LabelTranslator
from core.vtg.emg.modelTranslator.fsa_translator.state_fsa_translator import StateTranslator
from core.vtg.utils import find_file_or_dir


def translate_intermediate_model(logger, conf, avt, source, processes):
    """
    This is the main translator function. It generates automata first for all given processes of the environment model
    and then give them to particular translator chosen by the user defined configuration. At the end it triggers
    code printing and adds necessary information to the (abstract) verification task description.

    :param logger: Logger object.
    :param conf: Configuration dictionary for the whole EMG.
    :param avt: Verification task dictionary.
    :param source: Source object.
    :param processes: ProcessCollection object.
    :return: None.
    """
    # Prepare main configuration properties
    logger.info("Check necessary configuration properties to be set")
    check_or_set_conf_property(conf['translation options'], 'entry point', default_value='main', expected_type=str)
    check_or_set_conf_property(conf['translation options'], 'enironment model file',
                               default_value='environment_model.c', expected_type=str)
    check_or_set_conf_property(conf['translation options'], "nested automata", default_value=True, expected_type=bool)
    check_or_set_conf_property(conf['translation options'], "direct control functions calls", default_value=True,
                               expected_type=bool)
    check_or_set_conf_property(conf['translation options'], "code additional aspects", default_value=list(),
                               expected_type=list)
    check_or_set_conf_property(conf['translation options'], "additional headers", default_value=list(),
                               expected_type=list)

    if get_conf_property(conf['translation options'], "debug output"):
        processes.save_collection('environment processes.json')

    # Collect files
    files = set()
    for grp in avt['grps']:
        files.update([f['in file'] for f in grp['Extra CCs'] if 'in file' in f])
    files = sorted(files)
    logger.info("Files found: {}".format(len(files)))

    # Determine entry point file and function
    logger.info("Determine entry point file and function name")
    entry_file = get_necessary_conf_property(conf['translation options'], "environment model file")
    entry_point_name = get_necessary_conf_property(conf['translation options'], 'entry point')
    if processes.entry:
        # First just merge all as is
        if entry_file not in files:
            files.append(entry_file)
            try:
                entry_file_realpath = find_file_or_dir(logger, conf['main working directory'], entry_file)
            except FileNotFoundError:
                entry_file_realpath = os.path.relpath(entry_file, conf['main working directory'])

            # Generate new group
            avt['environment model'] = entry_file_realpath

        additional_code = dict()
        for process in list(processes.models.values()) + list(processes.environment.values()) + [processes.entry]:
            for file in process.declarations:
                if file not in additional_code:
                    additional_code[file] = {'declarations': process.declarations[file], 'definitions': dict()}
                else:
                    additional_code[file]['declarations'].update(process.declarations[file])
            for file in process.definitions:
                if file not in additional_code:
                    additional_code[file] = {'definitions': process.definitions[file], 'declarations': dict()}
                else:
                    additional_code[file]['definitions'].update(process.definitions[file])

        # Then convert into proper format
        for file in additional_code:
            additional_code[file]['declarations'] = list(additional_code[file]['declarations'].values())

            defin = additional_code[file]['definitions']
            additional_code[file]['definitions'] = list()
            for block in defin.values():
                additional_code[file]['definitions'].extend(block)

        # Rename main file
        if 'environment model' in additional_code:
            additional_code[entry_file] = additional_code['environment model']
            del additional_code['environment model']

        # Initalize code representation
        cmodel = CModel(logger, conf, conf['main working directory'], files, entry_point_name,
                        entry_file)

        # Add common headers provided by a user
        cmodel.add_headers(entry_file, get_necessary_conf_property(conf['translation options'], "additional headers"))

        logger.info("Generate finite state machine on each process")
        entry_fsa = Automaton(processes.entry, 1)
        identifier_cnt = 2
        model_fsa = []
        main_fsa = []
        for process in processes.models.values():
            model_fsa.append(Automaton(process, identifier_cnt))
            identifier_cnt += 1
        for process in processes.environment.values():
            main_fsa.append(Automaton(process, identifier_cnt))
            identifier_cnt += 1

        # Set self parallel flag
        sp_ids = get_conf_property(conf["translation options"], "not self parallel processes")
        if sp_ids and isinstance(sp_ids, list):
            for automaton in (a for a in model_fsa + main_fsa + [entry_fsa] if a.process.pretty_id in sp_ids):
                automaton.self_parallelism = False

        sp_categories = get_conf_property(conf["translation options"], "not self parallel processes from categories")
        sp_scenarios = get_conf_property(conf["translation options"], "not self parallel processes from scenarios")
        if sp_categories and isinstance(sp_categories, list):
            for automaton in (a for a in model_fsa + main_fsa + [entry_fsa] if a.process.category in sp_categories):
                automaton.self_parallelism = False
        if sp_scenarios and isinstance(sp_scenarios, list):
            for automaton in (a for a in model_fsa + main_fsa + [entry_fsa] if a.process.name in sp_scenarios):
                automaton.self_parallelism = False

        # Prepare code on each automaton
        logger.info("Translate finite state machines into C code")
        if get_necessary_conf_property(conf['translation options'], "nested automata"):
            LabelTranslator(logger, conf['translation options'], source, cmodel, entry_fsa, model_fsa, main_fsa)
        else:
            StateTranslator(logger, conf['translation options'], source, cmodel, entry_fsa, model_fsa, main_fsa)

        logger.info("Print generated source code")
        addictions = cmodel.print_source_code(additional_code)

        # Set entry point function in abstract task
        logger.info("Add an entry point function name to the abstract verification task")
        avt["entry points"] = [cmodel.entry_name]
        if get_conf_property(conf['translation options'], "code additional aspects"):
            additional_aspects = [os.path.abspath(find_file_or_dir(logger, conf["main working directory"], f)) for f in
                                  get_conf_property(conf['translation options'], "code additional aspects")]
        else:
            additional_aspects = []
        for grp in avt['grps']:
            logger.info('Add aspects to C files of group {!r}'.format(grp['id']))
            for cc_extra_full_desc_file in [f for f in grp['Extra CCs'] if 'in file' in f]:
                if cc_extra_full_desc_file["in file"] in addictions:
                    if 'plugin aspects' not in cc_extra_full_desc_file:
                        cc_extra_full_desc_file['plugin aspects'] = []
                    cc_extra_full_desc_file['plugin aspects'].append(
                        {
                            "plugin": "EMG",
                            "aspects": [addictions[cc_extra_full_desc_file["in file"]]] + additional_aspects
                        }
                    )

        extra_c_files = {f for p in list(processes.models.values()) + list(processes.environment.values()) +
                         [processes.entry] for f in p.cfiles}
        avt.setdefault('extra C files', list())
        avt['extra C files'].extend([
            {"C file": os.path.realpath(find_file_or_dir(logger,
                                                         get_necessary_conf_property(conf, "main working directory"), f))}
            for f in extra_c_files])
    else:
        logger.warning("It is impossible to generate an environment model without main process")
        avt["entry points"] = [entry_point_name]
        avt.setdefault('extra C files', list())


