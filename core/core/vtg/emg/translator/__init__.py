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
from core.vtg.emg.common import check_or_set_conf_property, get_necessary_conf_property
from core.vtg.emg.translator.code import CModel
from core.vtg.emg.translator.instances import yield_instances
from core.vtg.emg.translator.fsa_translator.label_fsa_translator import LabelTranslator
from core.vtg.emg.translator.fsa_translator.state_fsa_translator import StateTranslator


def translate_intermediate_model(logger, conf, avt, analysis, model, instance_maps, aspect_lines=None):
    # Prepare main configuration properties
    logger.info("Check necessary configuration properties to be set")
    check_or_set_conf_property(conf, 'entry point', default_value='main', expected_type=str)
    check_or_set_conf_property(conf["translation options"], "nested automata", default_value=True, expected_type=bool)
    check_or_set_conf_property(conf["translation options"], "direct control functions calls", default_value=True,
                               expected_type=bool)
    check_or_set_conf_property(conf["translation options"], "implicit callback calls", default_value=True,
                               expected_type=bool)

    # Generate instances
    logger.info("Generate finite state machines on each process from an intermediate model")
    entry_fsa, model_fsa, main_fsa = yield_instances(logger, conf["translation options"], analysis, model,
                                                     instance_maps)

    # Determine entry point
    logger.info("Determine entry point file and function name")
    entry_point_name, entry_file = __determine_entry(logger, conf, analysis)

    # Collect files
    files = set()
    for grp in avt['grps']:
        files.update([f['in file'] for f in grp['Extra CCs'] if 'in file' in f])
    files = sorted(files)
    logger.info("Files found: {}".format(len(files)))

    # Initalize code representation
    cmodel = CModel(logger, conf["translation options"], conf['main working directory'], files, entry_point_name,
                    entry_file)

    # Prepare code on each automaton
    logger.info("Translate finite state machines into C code")
    if get_necessary_conf_property(conf["translation options"], "nested automata"):
        LabelTranslator(logger, conf["translation options"], analysis, cmodel, entry_fsa, model_fsa,
                                         main_fsa)
    else:
        StateTranslator(logger, conf["translation options"], analysis, cmodel, entry_fsa, model_fsa,
                                         main_fsa)

    logger.info("Print generated source code")
    addictions = cmodel.print_source_code(aspect_lines)

    # Set entry point function in abstract task
    logger.info("Add an entry point function name to the abstract verification task")
    avt["entry points"] = [cmodel.entry_name]

    for grp in avt['grps']:
        logger.info('Add aspects to C files of group {!r}'.format(grp['id']))
        for cc_extra_full_desc_file in sorted([f for f in grp['Extra CCs'] if 'in file' in f],
                                              key=lambda f: f['in file']):
            if cc_extra_full_desc_file["in file"] in addictions:
                if 'plugin aspects' not in cc_extra_full_desc_file:
                    cc_extra_full_desc_file['plugin aspects'] = []
                cc_extra_full_desc_file['plugin aspects'].append(
                    {
                        "plugin": "EMG",
                        "aspects": [addictions[cc_extra_full_desc_file["in file"]]]
                    }
                )

    return instance_maps


def __determine_entry(logger, conf, analysis):
    logger.info("Determine entry point function name and a file to add")
    if len(analysis.inits) >= 1:
        file = analysis.inits[0][0]
        entry_file = file
    elif len(analysis.inits) < 1:
        raise RuntimeError("Cannot generate entry point without module initialization function")

    entry_point_name = get_necessary_conf_property(conf, 'entry point')
    return entry_point_name, entry_file


def __add_entry_points(self):
    self.task["entry points"] = [self.entry_point_name]


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'


