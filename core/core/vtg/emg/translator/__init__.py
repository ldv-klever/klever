#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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
from core.utils import find_file_or_dir
from core.vtg.emg.common import get_conf_property, check_or_set_conf_property, get_necessary_conf_property
from core.vtg.emg.translator.code import CModel
from core.vtg.emg.translator.fsa import Automaton
from core.vtg.emg.translator.fsa_translator.label_fsa_translator import LabelTranslator
from core.vtg.emg.translator.fsa_translator.state_fsa_translator import StateTranslator


def translate_intermediate_model(logger, conf, avt, analysis, model, additional_code):
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

    # Collect files
    files = set()
    for grp in avt['grps']:
        files.update([f['in file'] for f in grp['cc extra full desc files'] if 'in file' in f])
    files = sorted(files)
    logger.info("Files found: {}".format(len(files)))

    # Determine entry point file and function
    logger.info("Determine entry point file and function name")
    entry_file = get_necessary_conf_property(conf['translation options'], "environment model file")
    entry_point_name = get_necessary_conf_property(conf['translation options'], 'entry point')
    if entry_file not in files:
        files.append(entry_file)
        try:
            entry_file_realpath = find_file_or_dir(logger, conf['main working directory'], entry_file)
        except FileNotFoundError:
            entry_file_realpath = os.path.relpath(entry_file, conf['main working directory'])

        # Generate new group
        avt['environment model'] = entry_file_realpath

    # Initalize code representation
    cmodel = CModel(logger, conf, conf['main working directory'], files, entry_point_name,
                    entry_file)

    # Add common headers provided by a user
    cmodel.add_headers(entry_file, get_necessary_conf_property(conf['translation options'], "additional headers"))

    logger.info("Generate finite state machine on each process")
    entry_fsa = Automaton(model.entry_process, 0)
    identifier_cnt = 1
    model_fsa = []
    main_fsa = []
    for process in model.model_processes:
        model_fsa.append(Automaton(process, identifier_cnt))
        identifier_cnt += 1
    for process in model.event_processes:
        main_fsa.append(Automaton(process, identifier_cnt))
        identifier_cnt += 1

    # Prepare code on each automaton
    logger.info("Translate finite state machines into C code")
    if get_necessary_conf_property(conf['translation options'], "nested automata"):
        LabelTranslator(logger, conf['translation options'], analysis, cmodel, entry_fsa, model_fsa, main_fsa)
    else:
        StateTranslator(logger, conf['translation options'], analysis, cmodel, entry_fsa, model_fsa, main_fsa)

    logger.info("Print generated source code")
    # Rename main file
    if 'environment model' in additional_code:
        additional_code[cmodel.entry_file] = additional_code['environment model']
        del additional_code['environment model']
    addictions = cmodel.print_source_code(additional_code)

    # Set entry point function in abstract task
    logger.info("Add an entry point function name to the abstract verification task")
    avt["entry points"] = [cmodel.entry_name]
    for grp in avt['grps']:
        logger.info('Add aspects to C files of group {!r}'.format(grp['id']))
        for cc_extra_full_desc_file in sorted([f for f in grp['cc extra full desc files'] if 'in file' in f],
                                              key=lambda f: f['in file']):
            if cc_extra_full_desc_file["in file"] in addictions:
                if 'plugin aspects' not in cc_extra_full_desc_file:
                    cc_extra_full_desc_file['plugin aspects'] = []
                cc_extra_full_desc_file['plugin aspects'].append(
                    {
                        "plugin": "EMG",
                        "aspects": [addictions[cc_extra_full_desc_file["in file"]]] +
                                   get_conf_property(conf['translation options'], "code additional aspects")
                    }
                )


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'

