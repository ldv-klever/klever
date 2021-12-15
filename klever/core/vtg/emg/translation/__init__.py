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

import os
import shutil
import json
import sortedcontainers

import klever.core.utils
from klever.core.vtg.utils import find_file_or_dir
from klever.core.vtg.emg.translation.code import CModel
from klever.core.vtg.emg.translation.automaton import Automaton
from klever.core.vtg.emg.common import id_generator, get_or_die
from klever.core.vtg.emg.common.process.serialization import CollectionEncoder
from klever.core.vtg.emg.translation.fsa_translator.label_fsa_translator import LabelTranslator
from klever.core.vtg.emg.translation.fsa_translator.state_fsa_translator import StateTranslator
from klever.core.vtg.emg.translation.fsa_translator.simplest_fsa_translator import SimplestTranslator


DEFAULT_INCLUDE_HEADERS = (
    "ldv/linux/common.h",
    "ldv/linux/err.h",
    "ldv/verifier/common.h",
    "ldv/verifier/gcc.h",
    "ldv/verifier/nondet.h",
    "ldv/verifier/memory.h",
    "ldv/verifier/thread.h"
)


def translate_intermediate_model(logger, conf, avt, source, collection, udemses, program_fragment, images):
    """
    This is the main translator function. It generates automata first for all given processes of the environment model
    and then give them to particular translator chosen by the user defined configuration. At the end it triggers
    code printing and adds necessary information to the (abstract) verification task description.

    :param logger: Logger object.
    :param conf: Configuration dictionary for the whole EMG.
    :param avt: Verification task dictionary.
    :param source: Source object.
    :param collection: ProcessCollection object.
    :param udemses: Dictionary with UDEMSes to put the new one.
    :param program_fragment: Name of program fragment for which EMG generates environment models.
    :param images: List of images to be reported to the server.
    :return: None.
    """
    # Prepare main configuration properties
    logger.info(f"Translate '{collection.attributed_name}' with an identifier {collection.name}")
    conf['translation options'].setdefault('entry point', 'main')
    conf['translation options'].setdefault('environment model file', 'environment_model.c')
    conf['translation options'].setdefault('nested automata', True)
    conf['translation options'].setdefault('direct control functions calls', True)
    conf['translation options'].setdefault('code additional aspects', list())
    conf['translation options'].setdefault('additional headers', DEFAULT_INCLUDE_HEADERS)
    conf['translation options'].setdefault('self parallel processes', False)
    conf['translation options'].setdefault('ignore missing program files', False)

    # Make a separate directory
    model_path = str(collection.name)
    assert model_path, 'Each environment model should have a unique name'
    assert not os.path.isdir(model_path), f"Model name '{model_path}' is used twice"
    if os.path.isdir(model_path):
        logger.info(f"Clean workdir for translation '{model_path}'")
        shutil.rmtree(model_path)
    os.makedirs(model_path)
    if collection.attributed_name != collection.name:
        os.symlink(model_path, collection.attributed_name, target_is_directory=True)

    # Save processes
    model_file = os.path.join(model_path, 'input model.json')
    with open(model_file, mode='w', encoding='utf-8') as fp:
        json.dump(collection, fp, cls=CollectionEncoder, indent=2)

    udems = {
        conf["specifications set"]: [{
            "fragments": [program_fragment],
            "model": collection
        }]
    }
    udemses[collection.name] = json.dumps(udems, cls=CollectionEncoder, indent=2)

    # Save images of processes
    collection.save_digraphs(os.path.join(model_path, 'images'))

    for root, _, filenames in os.walk(os.path.join(model_path, 'images')):
        for fname in filenames:
            if os.path.splitext(fname)[-1] != '.dot':
                continue
            dot_file = os.path.join(root, fname)
            image_file = os.path.join(root, fname + '.png')
            if os.path.isfile(image_file):
                images.append((
                    'Model {0}/process "{1}"'
                    .format(collection.name, os.path.splitext(os.path.basename(dot_file))[0]),
                    dot_file, image_file))
            else:
                logger.warn('Image "{0}" does not exist'.format(image_file))

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
        collection.establish_peers()

    # Determine entry point file and function
    logger.info("Determine entry point file and function name")
    entry_file = os.path.join(model_path,
                              conf['translation options'].get('environment model file', 'environment_model.c'))
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
                additional_code.setdefault(file,
                                           {'declarations': sortedcontainers.SortedDict(),
                                            'definitions': sortedcontainers.SortedDict()})
                additional_code[file][att].update(getattr(process, att)[file])
        if process.file == 'environment model':
            process.file = entry_file

    # Initialize code representation
    cmodel = CModel(logger, conf, conf['main working directory'], files, entry_point_name, entry_file)

    # Then convert into proper format
    for file in additional_code:
        additional_code[file]['declarations'] = [val if val.endswith('\n') else val + '\n'
                                                 for val in additional_code[file]['declarations'].values()]

        val = additional_code[file]['definitions']
        additional_code[file]['definitions'] = list()
        for name, item in val.items():
            if isinstance(item, list):
                additional_code[file]['definitions'].extend(item)
            elif isinstance(item, str):
                # Replace file contents
                pth = find_file_or_dir(logger, conf['main working directory'], item)
                with open(pth, 'r', encoding='utf-8') as fp:
                    additional_code[file]['definitions'].extend(fp.readlines() + ["\n"])
            elif isinstance(item, dict):
                # Generate wrappers or do any other transformations
                func = cmodel.create_wrapper(name, item['wrapper'], item['declaration'])
                additional_code[file]['definitions'].extend(func.define() + ["\n"])
                if isinstance(additional_code['environment model']['declarations'], list):
                    additional_code['environment model']['declarations'].append(func.declare(extern=True)[0] + "\n")
                elif func.name not in additional_code['environment model']['declarations']:
                    additional_code['environment model']['declarations'][func.name] = \
                        func.declare(extern=True)[0] + "\n"
            else:
                raise ValueError("Expect either a list of string as a definition in intermediate model specification of"
                                 " a path name but got {!r}".format(item))

    # Rename main file
    if 'environment model' in additional_code:
        additional_code[entry_file] = additional_code['environment model']
        del additional_code['environment model']

    # Add common headers provided by a user
    for file in files:
        cmodel.add_headers(file, get_or_die(conf['translation options'], "additional headers"))

    logger.info("Generate finite state machine on each process")
    entry_fsa = Automaton(collection.entry, 1)
    identifiers = id_generator(start_from=2, cast=int)
    model_fsa = []
    main_fsa = []
    for process in collection.models.values():
        model_fsa.append(Automaton(process, next(identifiers)))
    for process in collection.environment.values():
        main_fsa.append(Automaton(process, next(identifiers)))

    # Set self parallel flag
    sp_ids = conf["translation options"].get('not self parallel processes')
    if sp_ids and isinstance(sp_ids, list):
        for amtn in (a for a in model_fsa + main_fsa + [entry_fsa] if str(a.process) in sp_ids):
            amtn.self_parallelism = False

    sp_categories = conf["translation options"].get("not self parallel processes from categories")
    sp_scenarios = conf["translation options"].get("not self parallel processes from scenarios")
    if sp_categories and isinstance(sp_categories, list):
        for amtn in (a for a in model_fsa + main_fsa + [entry_fsa] if a.process.category in sp_categories):
            amtn.self_parallelism = False
    if sp_scenarios and isinstance(sp_scenarios, list):
        for amtn in (a for a in model_fsa + main_fsa + [entry_fsa] if a.process.name in sp_scenarios):
            amtn.self_parallelism = False

    # Prepare code on each automaton
    logger.info("Translate finite state machines into C code")
    if conf['translation options'].get("simple control functions calls", True):
        SimplestTranslator(logger, conf['translation options'], source, collection, cmodel, entry_fsa, model_fsa, main_fsa)
    elif get_or_die(conf['translation options'], "nested automata"):
        LabelTranslator(logger, conf['translation options'], source, collection, cmodel, entry_fsa, model_fsa, main_fsa)
    else:
        StateTranslator(logger, conf['translation options'], source, collection, cmodel, entry_fsa, model_fsa, main_fsa)

    logger.info("Print generated source code")
    addictions = cmodel.print_source_code(model_path, additional_code)

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
    return avt
