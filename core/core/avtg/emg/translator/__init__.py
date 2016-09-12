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
from pympler import asizeof

from core.avtg.emg.translator.instances import yield_instances
from core.avtg.emg.translator.fsa import Automaton


def translate_intermediate_model(logger, conf, avt, analysis, model, instance_maps, aspect_lines=None):
    # Determine entry point
    entry_point_name, entry_file = __determine_entry(logger, conf["translation options"], analysis)

    # Determine additional headers to include
    extra_aspects = include_extra_headers(logger, analysis, model)

    # Generate instances
    entry_fsa, model_fsa, main_fsa = yield_instances(logger, conf["translation options"], analysis, model,
                                                     instance_maps)

    # todo: choose code generator
    return
    #file_addictions = CodeGenerator.translate()

    # Print model


def include_extra_headers(logger, analysis, model):
    """
    Try to extract headers which are need to include in addition to existing in the source code. Get them from the
    list of interfaces without an implementations and from the model processes descriptions.

    :param analysis: ModuleCategoriesSpecification object.
    :param model: ProcessModel object.
    :return: None
    """
    extra_aspects = list()

    # Get from unused interfaces
    header_list = list()
    for interface in (analysis.get_intf(i) for i in analysis.interfaces):
        if len(interface.declaration.implementations) == 0 and interface.header:
            for header in interface.header:
                if header not in header_list:
                    header_list.append(header)

    # Get from specifications
    for process in (p for p in model.model_processes + model.event_processes if len(p.headers) > 0):
        for header in process.headers:
            if header not in header_list:
                header_list.append(header)

    # Generate aspect
    if len(header_list) > 0:
        aspect = ['before: file ("$this")\n',
                  '{\n']
        aspect.extend(['#include <{}>\n'.format(h) for h in header_list])
        aspect.append('}\n')

        extra_aspects.extend(aspect)

    logger.info("Going to add {} additional headers".format(len(header_list)))
    return extra_aspects


def __determine_entry(logger, conf, analysis):
    logger.info("Determine entry point function name and a file to add")
    if len(analysis.inits) >= 1:
        file = analysis.inits[0][0]
        entry_file = file
    elif len(analysis.inits) < 1:
        raise RuntimeError("Cannot generate entry point without module initialization function")

    if "entry point" in conf:
        entry_point_name = conf["entry point"]
    else:
        entry_point_name = "main"

    logger.debug("Going to generate entry point function {} in file {}".format(entry_point_name, entry_file))
    return entry_point_name, entry_file


def __generate_aspects(self):
    aspect_dir = "aspects"
    self.logger.info("Create directory for aspect files {}".format("aspects"))
    os.makedirs(aspect_dir.encode('utf8'), exist_ok=True)

    for grp in self.task['grps']:
        # Generate function declarations
        self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
        for cc_extra_full_desc_file in sorted([df for df in grp['cc extra full desc files'] if 'in file' in df],
                                              key=lambda f: f['in file']):
            # Aspect text
            lines = list()

            if len(self.additional_aspects) > 0:
                lines.append("\n")
                lines.append("/* EMG additional aspects */\n")
                lines.extend(self.additional_aspects)
                lines.append("\n")

            # After file
            lines.append('after: file ("$this")\n')
            lines.append('{\n')

            lines.append("/* EMG type declarations */\n")
            for file in sorted(self.addictions.keys()):
                if "types" in self.addictions[file]:
                    for tp in self.addictions[file]["types"]:
                        lines.append(tp.to_string('') + " {\n")
                        for field in sorted(list(tp.fields.keys())):
                            lines.append("\t{};\n".format(tp.fields[field].to_string(field)))
                        lines.append("};\n")
                        lines.append("\n")

            lines.append("/* EMG Function declarations */\n")
            for file in sorted(self.addictions.keys()):
                if "functions" in self.addictions[file]:
                    for function in sorted(self.addictions[file]["declarations"].keys()):
                        if cc_extra_full_desc_file["in file"] == file:
                            lines.extend(self.addictions[file]["declarations"][function])

            lines.append("\n")
            lines.append("/* EMG variable declarations */\n")
            for file in sorted(self.addictions):
                if "variables" in self.addictions[file]:
                    for variable in sorted(self.addictions[file]["variables"].keys()):
                        if cc_extra_full_desc_file["in file"] == file:
                            lines.append(self.addictions[file]["variables"][variable])

            lines.append("\n")
            lines.append("/* EMG variable initialization */\n")
            for file in sorted(self.addictions):
                if "initializations" in self.addictions[file]:
                    for variable in sorted(self.addictions[file]["initializations"].keys()):
                        if cc_extra_full_desc_file["in file"] == file:
                            lines.append(self.addictions[file]["initializations"][variable])

            lines.append("\n")
            lines.append("/* EMG function definitions */\n")
            for file in sorted(self.addictions):
                if "functions" in self.addictions[file]:
                    for function in sorted(self.addictions[file]["functions"].keys()):
                        if cc_extra_full_desc_file["in file"] == file:
                            lines.extend(self.addictions[file]["functions"][function])
                            lines.append("\n")

            lines.append("}\n")
            lines.append("/* EMG kernel function models */\n")
            for aspect in self.model_aspects:
                lines.extend(aspect.get_aspect())
                lines.append("\n")

            name = "aspects/ldv_{}.aspect".format(os.path.splitext(
                os.path.basename(cc_extra_full_desc_file["in file"]))[0])
            with open(name, "w", encoding="utf8") as fh:
                fh.writelines(lines)

            path = os.path.relpath(name, self.conf['main working directory'])
            self.logger.info("Add aspect file {}".format(path))
            self.aspects[cc_extra_full_desc_file["in file"]] = path


def __add_aspects(self):
    for grp in self.task['grps']:
        self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
        for cc_extra_full_desc_file in sorted([f for f in grp['cc extra full desc files'] if 'in file' in f],
                                              key=lambda f: f['in file']):
            if cc_extra_full_desc_file["in file"] in self.aspects:
                if 'plugin aspects' not in cc_extra_full_desc_file:
                    cc_extra_full_desc_file['plugin aspects'] = []
                cc_extra_full_desc_file['plugin aspects'].append(
                    {
                        "plugin": "EMG",
                        "aspects": [self.aspects[cc_extra_full_desc_file["in file"]]]
                    }
                )


def __add_entry_points(self):
    self.task["entry points"] = [self.entry_point_name]

def __get_translator(self, avt):
    # todo: find a better place
    self.logger.info("Choose translator module to translate an intermediate model to C code")
    if "translator" in self.conf:
        translator_name = self.conf["translator"]
    else:
        translator_name = "default"
    self.logger.info("Translation module {} has been chosen".format(translator_name))

    translator = getattr(__import__("core.avtg.emg.translator.{}".format(translator_name),
                                    fromlist=['Translator']),
                         'Translator')

    # Import additional aspect files
    self.logger.info("Check whether additional aspect files are provided to be included in an environment model")
    aspect_lines = self.__read_additional_content("aspects")


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'


