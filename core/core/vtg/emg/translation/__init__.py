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

from core.vtg.emg.common import get_or_die
from core.vtg.utils import find_file_or_dir
from core.vtg.emg.translation.code import CModel
from core.vtg.emg.translation.automaton import Automaton
from core.vtg.emg.translation.fsa_translator.label_fsa_translator import LabelTranslator
from core.vtg.emg.translation.fsa_translator.state_fsa_translator import StateTranslator


def translate_intermediate_model(logger, conf, avt, source, collection):
    """
    This is the main translator function. It generates automata first for all given processes of the environment model
    and then give them to particular translator chosen by the user defined configuration. At the end it triggers
    code printing and adds necessary information to the (abstract) verification task description.

    :param logger: Logger object.
    :param conf: Configuration dictionary for the whole EMG.
    :param avt: Verification task dictionary.
    :param source: Source object.
    :param collection: ProcessCollection object.
    :return: None.
    """
    # Prepare main configuration properties
    logger.info("Check necessary configuration properties to be set")
    conf['translation options'].setdefault('entry point', 'main')
    conf['translation options'].setdefault('enironment model file', 'environment_model.c')
    conf['translation options'].setdefault('nested automata', True)
    conf['translation options'].setdefault('direct control functions calls', True)
    conf['translation options'].setdefault('code additional aspects', list())
    conf['translation options'].setdefault('additional headers', list())
    conf['translation options'].setdefault('self parallel processes', False)

    if not collection.entry:
        raise RuntimeError("It is impossible to generate an environment model without main process")

    if conf['translation options'].get('ignore missing function models'):
        for name in list(collection.models.keys()):
            fs = source.get_source_functions(name)
            if not fs:
                logger.info("Ignore function model {!r} since there is no such function in the code".format(name))
                del collection.models[name]

    # If necessary match peers
    if conf['translation options'].get('implicit signal peers'):
        process_list = list(collection.processes)
        for i, first in enumerate(process_list):
            if i + 1 < len(process_list):
                for second in process_list[i+1:]:
                    first.establish_peers(second)

    # Determine entry point file and function
    logger.info("Determine entry point file and function name")
    entry_file = get_or_die(conf['translation options'], "environment model file")
    entry_point_name = get_or_die(conf['translation options'], 'entry point')
    files = source.c_full_paths
    if entry_file not in files:
        files.add(entry_file)
        try:
            entry_file_realpath = find_file_or_dir(logger, conf['main working directory'], entry_file)
        except FileNotFoundError:
            entry_file_realpath = os.path.relpath(entry_file, conf['main working directory'])

        # Generate new group
        avt['environment model'] = entry_file_realpath

    # First just merge all as is
    additional_code = dict()
    for process in list(collection.models.values()) + list(collection.environment.values()) + [collection.entry]:
        for att in ('declarations', 'definitions'):
            for file in getattr(process, att):
                additional_code.setdefault(file, {'declarations': dict(), 'definitions': dict()})
                additional_code[file][att].update(getattr(process, att)[file])
        if process.file == 'environment model':
            process.file = entry_file

    # Then convert into proper format
    for file in additional_code:
        additional_code[file]['declarations'] = [val if val.endswith('\n') else val + '\n'
                                                 for val in additional_code[file]['declarations'].values()]

        val = additional_code[file]['definitions']
        additional_code[file]['definitions'] = list()
        for item in val.values():
            if isinstance(item, list):
                additional_code[file]['definitions'].extend(item)
            elif isinstance(item, str):
                # Replace file contents
                pth = find_file_or_dir(logger, conf['main working directory'], item)
                with open(pth, 'r', encoding='utf8') as fp:
                    additional_code[file]['definitions'].extend(fp.readlines() + ["\n"])
            else:
                raise ValueError("Expect either a list of string as a definition in intermediate model specification of"
                                 " a path name but got {!r}".format(item))

    # Rename main file
    if 'environment model' in additional_code:
        additional_code[entry_file] = additional_code['environment model']
        del additional_code['environment model']

    # Initalize code representation
    cmodel = CModel(logger, conf, conf['main working directory'], files, entry_point_name, entry_file)

    # Add common headers provided by a user
    for file in files:
        cmodel.add_headers(file, get_or_die(conf['translation options'], "additional headers"))

    logger.info("Generate finite state machine on each process")
    entry_fsa = Automaton(collection.entry, 1)
    identifier_cnt = 2
    model_fsa = []
    main_fsa = []
    for process in collection.models.values():
        model_fsa.append(Automaton(process, identifier_cnt))
        identifier_cnt += 1
    for process in collection.environment.values():
        main_fsa.append(Automaton(process, identifier_cnt))
        identifier_cnt += 1

    # Set self parallel flag
    sp_ids = conf["translation options"].get('not self parallel processes')
    if sp_ids and isinstance(sp_ids, list):
        for automaton in (a for a in model_fsa + main_fsa + [entry_fsa] if a.process.pretty_id in sp_ids):
            automaton.self_parallelism = False

    sp_categories = conf["translation options"].get("not self parallel processes from categories")
    sp_scenarios = conf["translation options"].get("not self parallel processes from scenarios")
    if sp_categories and isinstance(sp_categories, list):
        for automaton in (a for a in model_fsa + main_fsa + [entry_fsa] if a.process.category in sp_categories):
            automaton.self_parallelism = False
    if sp_scenarios and isinstance(sp_scenarios, list):
        for automaton in (a for a in model_fsa + main_fsa + [entry_fsa] if a.process.name in sp_scenarios):
            automaton.self_parallelism = False

    # Prepare code on each automaton
    logger.info("Translate finite state machines into C code")
    if get_or_die(conf['translation options'], "nested automata"):
        LabelTranslator(logger, conf['translation options'], source, cmodel, entry_fsa, model_fsa, main_fsa)
    else:
        StateTranslator(logger, conf['translation options'], source, cmodel, entry_fsa, model_fsa, main_fsa)

    logger.info("Print generated source code")
    addictions = cmodel.print_source_code(additional_code)

    # Set entry point function in abstract task
    logger.info("Add an entry point function name to the abstract verification task")
    avt["entry points"] = [cmodel.entry_name]
    if conf['translation options'].get("code additional aspects"):
        additional_aspects = [os.path.abspath(find_file_or_dir(logger, conf["main working directory"], f)) for f in
                              conf['translation options'].get("code additional aspects")]
    else:
        additional_aspects = []
    for grp in avt['grps']:
        # Todo maybe this will not work with ccs with multiple ins
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

    extra_c_files = {f for p in list(collection.models.values()) + list(collection.environment.values()) +
                     [collection.entry] for f in p.cfiles}
    avt.setdefault('extra C files', list())
    avt['extra C files'].extend([
        {"C file": os.path.realpath(find_file_or_dir(logger,
                                                     get_or_die(conf, "main working directory"), f))}
        for f in extra_c_files])

