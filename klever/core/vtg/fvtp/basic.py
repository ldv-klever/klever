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
from xml.dom import minidom
from xml.etree import ElementTree

from klever.core.vtg.fvtp import common
from klever.core import utils


class BasicGenerationStrategy:

    def __init__(self, logger, conf, abstract_task_desc):
        """
        This is a simple strategy to generate verification tasks and corresponding benchmark descriptions. This
        particular strategy generates single verification task with maximum time limits set. It is assumed that
        the generated algorithm is left unchanged while methods for creating different sections of the description
        can be changed.

        :param logger: Logger.
        :param conf: Dictionary
        :param abstract_task_desc: Dictionary.
        """
        self.logger = logger
        self.conf = conf
        self.abstract_task_desc = abstract_task_desc

    def generate_verification_task(self):
        """
        Main routine of the strategy. It is suspicious if you need to change it, do it if you need to play with resource
        limitations or generate several tasks. This should be a generator to update archives each time before submitting
        new tasks.
        """
        self.logger.info("Prepare single verification task for abstract task {!r}".
                         format(self.abstract_task_desc['id']))
        resource_limits = self._prepare_resource_limits()
        files = self._prepare_benchmark_description(resource_limits)
        common.prepare_verification_task_files_archive(files)
        task_description = self._prepare_task_description(resource_limits)
        self.logger.debug('Create verification task description file "task.json"')
        with open('task.json', 'w', encoding='utf-8') as fp:
            utils.json_dump(task_description, fp, self.conf['keep intermediate files'])

    def _prepare_benchmark_description(self, resource_limits):
        """
        Generate root ElementTree.Element for the benchmark description.

        :param resource_limits: Dictionary with resource limitations of the task.
        :return: ElementTree.Element.
        """
        self.logger.debug("Prepare benchmark.xml file")
        benchmark = ElementTree.Element("benchmark", {
            "tool": self.conf['verifier']['name'].lower()
        })
        if resource_limits.get("CPU time"):
            benchmark.set('hardtimelimit', str(int(resource_limits["CPU time"])))
            if resource_limits.get("soft CPU time"):
                benchmark.set('timelimit',
                              str(int(int(resource_limits["CPU time"]) * float(resource_limits["soft CPU time"]))))

        opts, safe_prps = common.get_verifier_opts_and_safe_prps(self.logger, resource_limits, self.conf)

        # Then add options
        rundefinition = ElementTree.SubElement(benchmark, "rundefinition")

        # Add options to the XML description
        for opt in opts:
            for name in opt:
                ElementTree.SubElement(rundefinition, "option", {"name": name}).text = opt[name]

        # Files
        files = self._prepare_task_files(benchmark)
        self.abstract_task_desc['verification task files'] = {file: (file if os.path.isabs(file)
                                                                     else os.path.realpath(file))
                                                              for file in files}

        # Safety properties specification
        self._prepare_safe_prps_spec(benchmark, safe_prps)
        files.append("safe-prps.prp")

        # Save the benchmark definition
        with open("benchmark.xml", "w", encoding="utf-8") as fp:
            fp.write(minidom.parseString(ElementTree.tostring(benchmark)).toprettyxml(indent="    "))
        files.append("benchmark.xml")

        return files

    def _prepare_task_description(self, resource_limits):
        """
        Generate dictionary with verification task description.

        :param resource_limits: Dictionary.
        :return: Dictionary.
        """
        self.logger.debug('Prepare common verification task description')

        task_desc = {
            # Safely use id of corresponding abstract verification task since each abstract verification task will
            # correspond to exactly one verification task.
            'id': self.abstract_task_desc['id'],
            'job id': self.conf['identifier'],
            'format': 1,
        }
        # Copy attributes from parent job.
        for attr_name in ('priority', 'upload verifier input files'):
            task_desc[attr_name] = self.conf[attr_name]

        for attr in self.abstract_task_desc['attrs']:
            attr_name = list(attr.keys())[0]
            attr_val = attr[attr_name]
            if attr_name == 'requirement':
                self.requirement = attr_val

        # Use resource limits and verifier specified in job configuration.
        task_desc.update(
            {
                'verifier': {
                    'name': self.conf['verifier']['name'],
                    'version': self.conf['verifier']['version']
                },
                'resource limits': resource_limits
            }
        )

        # Save to task its class.
        task_desc['solution class'] = self.conf['solution class']

        # Keep reference to additional sources. It will be used for verification reports.
        task_desc['additional sources'] = self.abstract_task_desc['additional sources']

        return task_desc

    def _prepare_task_files(self, benchmark_definition):
        """
        The function prepares files and adds their names to the given benchmark definition. It should add new
        subelement 'tasks'.

        :param benchmark_definition: ElementTree.Element.
        :return: List of property file names with necessary paths to add to the final archive.
        """
        tasks = ElementTree.SubElement(benchmark_definition, "tasks")
        if "merge source files" in self.conf and self.conf["merge source files"]:
            file = common.merge_files(self.logger, self.conf, self.abstract_task_desc)
            with open('cil.yml', 'w') as fp:
                fp.write("format_version: '1.0'\n\n")
                fp.write("input_files: 'cil.i'\n\n")
                fp.write("properties:\n  - property_file: safe-prps.prp\n")
            ElementTree.SubElement(tasks, "include").text = 'cil.yml'
            return ['cil.yml', file]
        # TODO: this is for experimental purposes only!
        c_files = [os.path.join(self.conf['main working directory'], extra_c_file['C file']) for
                   extra_c_file in self.abstract_task_desc['extra C files'] if 'C file' in extra_c_file]
        ElementTree.SubElement(tasks, "include").text = c_files[0]
        for file in c_files[1:]:
            ElementTree.SubElement(tasks, "append").text = file
        return c_files

    def _prepare_resource_limits(self):
        """
        Calculate resource limitations for the given task. In terms of this particular strategy it return just maximum
        limitations already set by a user.

        :return: Dictionary with resource limitations.
        """
        if self.conf.get('override resource limits'):
            self.logger.info("Choose resource limitations provided by VTG instead of QoS")
        limitations = self.conf.get('override resource limits',
                                    utils.read_max_resource_limitations(self.logger, self.conf))

        if 'memory size' not in limitations:
            raise KeyError("User should provide memory limitation for verification tasks")

        return limitations

    def _prepare_safe_prps_spec(self, benchmark_description, safe_prps):
        """
        Prepare a safety properties specification and add the corresponding element to the benchmark definition.

        :param benchmark_description: ElementTree.Element.
        :return: None.
        """
        self.logger.info('Prepare safety properties specification "safe-prps.prp"')

        if 'entry points' not in self.abstract_task_desc:
            raise ValueError('Safety properties specification was not prepared since entry points were not specified')

        if len(self.abstract_task_desc['entry points']) > 1:
            raise NotImplementedError('Several entry points are not supported')

        if not safe_prps:
            raise ValueError('Safety properties specification was not prepared since there is no safety properties')

        with open('safe-prps.prp', 'w', encoding='utf-8') as fp:
            for safe_prp in safe_prps:
                fp.write(safe_prp.format(entry_point=self.abstract_task_desc['entry points'][0]) + '\n')

        ElementTree.SubElement(benchmark_description, "propertyfile").text = "safe-prps.prp"
