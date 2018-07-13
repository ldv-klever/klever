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

import json
import os
import re
from xml.dom import minidom
from xml.etree import ElementTree

import core.vtg.fvtp.common as common
import core.utils as utils


class Basic:

    def __init__(self, logger, conf, abstract_task_desc):
        """
        This is a simple strategy to generate verification tasks and corresponding benchmark descriptions. This
        particular strategy generates single verification task with maximum time limits set. It is assumed that
        the generatl algorythms is left unchanged while methods for creating different sections of the description
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

        :return: List of descriptions with fully prepared tasks.
        """
        self.logger.info("Prepare single verification task for abstract task {!r}".
                         format(self.abstract_task_desc['id']))
        resource_limits = self._prepare_resource_limits()
        files = self._prepare_benchmark_description(resource_limits)
        common.prepare_verification_task_files_archive(files)
        task_description = self._prepare_task_description(resource_limits)
        self.logger.debug('Create verification task description file "task.json"')
        with open('task.json', 'w', encoding='utf8') as fp:
            json.dump(task_description, fp, ensure_ascii=False, sort_keys=True, indent=4)
        self._cleanup()

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
        if "CPU time" in resource_limits and isinstance(resource_limits["CPU time"], int):
            benchmark.set('timelimit', str(int(int(resource_limits["CPU time"]) * 0.9)))

        opts, safe_prps = common.get_verifier_opts_and_safe_prps(self.logger, resource_limits, self.conf)

        # Then add options
        self._prepare_run_definition(benchmark, opts)

        # Files
        files = self._prepare_task_files(benchmark)

        # Safety properties specification
        self._prepare_safe_prps_spec(benchmark, safe_prps)
        files.append("safe-prps.prp")

        # Save the benchmark definition
        with open("benchmark.xml", "w", encoding="utf8") as fp:
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
            # Safely use id of corresponding abstract verification task since all bug kinds will be merged and each
            # abstract verification task will correspond to exactly one verificatoin task.
            'id': self.abstract_task_desc['id'],
            'job id': self.conf['identifier'],
            'format': 1,
        }
        # Copy attributes from parent job.
        for attr_name in ('priority', 'upload input files of static verifiers'):
            task_desc[attr_name] = self.conf[attr_name]

        for attr in self.abstract_task_desc['attrs']:
            attr_name = list(attr.keys())[0]
            attr_val = attr[attr_name]
            if attr_name == 'rule specification':
                self.rule_specification = attr_val

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

        # Save to task its class
        task_desc['solution class'] = self.abstract_task_desc['solution class']

        return task_desc

    def _prepare_run_definition(self, benchmark_definition, options):
        """
        The function should add a new subelement with name 'rundefinition' to the XML description of the given
        benchmark. The new element should contains a list of options for the given verifier.

        :param benchmark_definition: ElementTree.Element.
        :param options: Dictionary with options.
        :return: None.
        """
        rundefinition = ElementTree.SubElement(benchmark_definition, "rundefinition")

        # Add options to the XML description
        for opt in options:
            for name in opt:
                ElementTree.SubElement(rundefinition, "option", {"name": name}).text = opt[name]

    def _prepare_task_files(self, benchmark_definition):
        """
        The function prepares files and adds their names to the given benchmark definition. It should add new
        subelement 'tasks'.

        :param benchmark_definition: ElementTree.Element.
        :return: List of property file names with necessary paths to add to the final archive.
        """
        self._prepare_bug_kind_functions_file()

        tasks = ElementTree.SubElement(benchmark_definition, "tasks")
        if "merge source files" in self.conf and self.conf["merge source files"]:
            file = common.merge_files(self.logger, self.conf, self.abstract_task_desc)
            ElementTree.SubElement(tasks, "include").text = file
            return [file]
        else:
            c_files = common.trimmed_files(self.logger, self.conf, self.abstract_task_desc)
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
        limitations = self.abstract_task_desc.get('resource limits',
                                                  utils.read_max_resource_limitations(self.logger, self.conf))
        return limitations

    def _cleanup(self):
        """
        This function delete all unnecessary files generated by the strategy. All further cleanup will be perfromed
        later.

        :return: None
        """
        if not self.conf['keep intermediate files']:
            for extra_c_file in self.abstract_task_desc['extra C files']:
                if 'C file' in extra_c_file and os.path.isfile(extra_c_file['C file']):
                    os.remove(extra_c_file['C file'])
                if 'new C file' in extra_c_file and os.path.isfile(extra_c_file['new C file']):
                    os.remove(extra_c_file['new C file'])

    def _prepare_bug_kind_functions_file(self):
        self.logger.debug('Prepare bug kind functions file "bug kind funcs.c"')

        bug_kinds = []
        for extra_c_file in self.abstract_task_desc['extra C files']:
            if 'bug kinds' in extra_c_file:
                for bug_kind in extra_c_file['bug kinds']:
                    if bug_kind not in bug_kinds:
                        bug_kinds.append(bug_kind)
        bug_kinds.sort()

        # Create bug kind function definitions that all call __VERIFIER_error() since this strategy doesn't distinguish
        # different bug kinds.
        with open('bug kind funcs.c', 'w', encoding='utf8') as fp:
            fp.write('/* http://sv-comp.sosy-lab.org/2015/rules.php */\nvoid __VERIFIER_error(void);\n')
            for bug_kind in bug_kinds:
                fp.write('void ldv_assert_{0}(int expr) {{\n\tif (!expr)\n\t\t__VERIFIER_error();\n}}\n'.format(
                    re.sub(r'\W', '_', bug_kind)))

        # Add bug kind functions file to other abstract verification task files. Absolute file path is required to get
        # absolute path references in error traces.
        self.abstract_task_desc['extra C files'].append({'C file': os.path.abspath('bug kind funcs.c')})

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

        if not len(safe_prps):
            raise ValueError('Safety properties specification was not prepared since there is no safety properties')

        with open('safe-prps.prp', 'w', encoding='utf8') as fp:
            for safe_prp in safe_prps:
                fp.write(safe_prp.format(entry_point=self.abstract_task_desc['entry points'][0]) + '\n')

        ElementTree.SubElement(benchmark_description, "propertyfile").text = "safe-prps.prp"
