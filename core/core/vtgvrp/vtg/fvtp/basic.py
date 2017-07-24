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
import json
import os
import re
from xml.dom import minidom
from xml.etree import ElementTree

import core.session
import core.utils
import core.vtgvrp.vtg.plugins


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
        self.conf  = conf
        self.abstract_task_desc = abstract_task_desc
        self.__vt_cache = None

    @property
    def verification_tasks(self):
        """
        Generate and return a number of archives with verification tasks to submit. Avoid changing the method
        implementing other strategies.

        :return: List of paths to archives to solve.
        """
        if not self.__vt_cache:
            self.__vt_cache = self._generate_tasks()
        return self.__vt_cache

    def _generate_tasks(self):
        """
        Main routine of the strategy. It is suspicious if you need to change it, do it if you need to play with resource
        limitations or generate several tasks.

        :return: List of archives with fully prepared tasks.
        """
        raise NotImplementedError

    @property
    def _get_options_set(self):
        """
        Collect verifier oiptions from a user provided description, template and profile and prepare a final list of
        options. Each option is represented as a small dictionary with an option name given as a key and value provided
        as a value. The value can be None. Priority of options is the following: options given by a user
        (the most important), options provided by a profile and options from the template.

        :return: List with options.
        """
        raise NotImplementedError
        return dict()

    def _prepare_run_definition(self, options_list, benchmark_definition):
        """
        The function should add a new subelement with name 'rundefinition' to the XML description of the given
        benchmark. The new element should contains a list of options for the given verifier.

        :param options_list: List of options for the given verifier.
        :param benchmark_definition: ElementTree.Element.
        :return: None.
        """
        # todo: not implemented
        raise NotImplementedError

    def _prepare_property_files(self, benchmark_definition):
        """
        The function prepares property files and adds "propertyfile" tag to the given XML definition of the benchmark.
        It should add at least one new SubElement "propertyfile".

        :param benchmark_definition: ElementTree.Element.
        :return: List of property file names with necessary paths to add to the final archive.
        """
        raise NotImplementedError

    def _prepare_tasks(self, benchmark_definition):
        """
        The function prepares files and adds their names to the given benchmark definition. It should add new
        subelement 'tasks'.

        :param benchmark_definition: ElementTree.Element.
        :return: List of property file names with necessary paths to add to the final archive.
        """
        raise NotImplementedError

    def _prepare_resource_limits(self, ):

    ##########################################################################################################
    # todo: change function
    def prepare_common_verification_task_desc(self):
        self.logger.debug('Prepare common verification task description')

        self.task_desc = {
            # Safely use id of corresponding abstract verification task since all bug kinds will be merged and each
            # abstract verification task will correspond to exactly one verificatoin task.
            'id': self.conf['abstract task desc']['id'],
            'job id': self.conf['identifier'],
            'format': 1,
        }
        # Copy attributes from parent job.
        for attr_name in ('priority', 'upload input files of static verifiers'):
            self.task_desc[attr_name] = self.conf[attr_name]

        for attr in self.conf['abstract task desc']['attrs']:
            attr_name = list(attr.keys())[0]
            attr_val = attr[attr_name]
            if attr_name == 'rule specification':
                self.rule_specification = attr_val

        # Use resource limits and verifier specified in job configuration.
        self.task_desc.update(
            {
                'verifier': {
                    'name': self.conf['VTG strategy']['verifier']['name'],
                    'version': self.conf['VTG strategy']['verifier']['version']
                },
                'resource limits': self.restrictions
            }
        )


    def final_task_preparation(self):
        if 'verifier profile' not in self.conf:
            raise KeyError("User should set 'verifier profile' configuration option to determine which verifier "
                           "options the system should use")

        if 'verifier version' in self.conf:
            self.logger.info('Verifier version is "{0}"'.format(self.conf['verifier version']))
            self.abstract_task_desc['verifier version'] = self.conf['verifier version']

        if 'verifier configuration' in self.conf:
            self.logger.info('Verifier configuration is "{0}"'.format(self.conf['verifier configuration']))
            self.abstract_task_desc['verifier configuration'] = self.conf['verifier configuration']

        if 'verifier options' in self.conf:
            self.logger.info('Verifier options are: {0}'.format(self.conf['verifier options']))
            self.abstract_task_desc['verifier options'] = self.conf['verifier options']

        if 'verifier specifications' in self.conf:
            self.logger.info('Verifier specifications are: {0}'.format(', '.join(self.conf['verifier specifications'])))
            self.abstract_task_desc['verifier specifications'] = self.conf['verifier specifications']

        if 'verifier version' in self.conf['abstract task desc']:
            self.conf['VTG strategy']['verifier']['version'] = self.conf['abstract task desc']['verifier version']
        # Read max restrictions for tasks
        restrictions_file = core.utils.find_file_or_dir(self.logger, self.conf["main working directory"], "tasks.json")
        with open(restrictions_file, 'r', encoding='utf8') as fp:
            self.restrictions = json.loads(fp.read())

        self._get_options
        self.set_common_verifier_options()
        self.prepare_common_verification_task_desc()
        self.prepare_bug_kind_functions_file()
        property_file = self.prepare_property_file()
        files = self.prepare_src_files()
        benchmark = self.prepare_benchmark_description(files, property_file)
        self.files = files + [property_file] + [benchmark]
        self.shadow_src_dir = os.path.abspath(os.path.join(self.conf['main working directory'],
                                                           self.conf['shadow source tree']))

        if self.conf['keep intermediate files']:
            self.logger.debug('Create verification task description file "task.json"')
            with open('task.json', 'w', encoding='utf8') as fp:
                json.dump(self.task_desc, fp, ensure_ascii=False, sort_keys=True, indent=4)

        self.prepare_verification_task_files_archive()
        # todo: implement
        self.decide_verification_task()

        # Remove all extra C files.
        if not self.conf['keep intermediate files']:
            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                if 'C file' in extra_c_file:
                    if os.path.isfile(extra_c_file['C file']):
                        os.remove(extra_c_file['C file'])

    main = final_task_preparation

    def prepare_benchmark_description(self, files, property_file):
        # Property file may not be specified.
        self.logger.debug("Prepare benchmark.xml file")
        benchmark = ElementTree.Element("benchmark", {
            "tool": self.conf['VTG strategy']['verifier']['name'].lower()
        })
        rundefinition = ElementTree.SubElement(benchmark, "rundefinition")
        for opt in self.conf['VTG strategy']['verifier']['options']:
            for name in opt:
                ElementTree.SubElement(rundefinition, "option", {"name": name}).text = opt[name]
        ElementTree.SubElement(benchmark, "propertyfile").text = property_file

        tasks = ElementTree.SubElement(benchmark, "tasks")
        # TODO: in this case verifier is invoked per each such file rather than per all of them.
        for file in files:
            ElementTree.SubElement(tasks, "include").text = file
        with open("benchmark.xml", "w", encoding="utf8") as fp:
            fp.write(minidom.parseString(ElementTree.tostring(benchmark)).toprettyxml(indent="    "))

        return "benchmark.xml"

    def set_common_verifier_options(self):
        if self.conf['VTG strategy']['verifier']['name'] == 'CPAchecker':
            if 'options' not in self.conf['VTG strategy']['verifier']:
                self.conf['VTG strategy']['verifier']['options'] = []

            if 'verifier configuration' in self.conf['abstract task desc']:
                self.conf['VTG strategy']['verifier']['options'].append(
                    {self.conf['abstract task desc']['verifier configuration']: ''}
                )
            elif 'value analysis' in self.conf['VTG strategy']:
                self.conf['VTG strategy']['verifier']['options'] = [{'-valueAnalysis': ''}]
            elif 'recursion support' in self.conf['VTG strategy']:
                self.conf['VTG strategy']['verifier']['options'] = [{'-valuePredicateAnalysis-bam-rec': ''}]
            # Specify default CPAchecker configuration.
            else:
                self.conf['VTG strategy']['verifier']['options'].append({'-ldv-bam-optimized': ''})

            # Remove internal CPAchecker timeout.
            self.conf['VTG strategy']['verifier']['options'].append({'-setprop': 'limits.time.cpu={0}s'.format(
                round(self.restrictions['CPU time'] / 1000))})

            # To refer to original source files rather than to CIL ones.
            self.conf['VTG strategy']['verifier']['options'].append({'-setprop': 'parser.readLineDirectives=true'})

            # To allow to output multiple error traces if other options (configuration) will need this.
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-setprop': 'counterexample.export.graphml=witness.%d.graphml'})

            # Do not compress witnesses as, say, CPAchecker r20376 we still used did.
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-setprop': 'counterexample.export.compressWitness=false'})

            # Adjust JAVA heap size for static memory (Java VM, stack, and native libraries e.g. MathSAT) to be 1/4 of
            # general memory size limit if users don't specify their own sizes.
            if '-heap' not in [list(opt.keys())[0] for opt in self.conf['VTG strategy']['verifier']['options']]:
                self.conf['VTG strategy']['verifier']['options'].append({'-heap': '{0}m'.format(
                    round(3 * self.restrictions['memory size'] / (4 * 1000 ** 2)))})

            if 'bit precision analysis' in self.conf['VTG strategy']:
                self.conf['VTG strategy']['verifier']['options'].extend([
                    {'-setprop': 'cpa.predicate.encodeBitvectorAs=BITVECTOR'},
                    {'-setprop': 'solver.solver=MATHSAT5'}
                ])

            if 'graph traversal algorithm' in self.conf['VTG strategy'] \
                    and self.conf['VTG strategy']['graph traversal algorithm'] != 'Default':
                algo_map = {'Depth-first search': 'DFS', 'Breadth-first search': 'BFS', 'Random': 'RAND'}
                self.conf['VTG strategy']['verifier']['options'].append(
                    {'-setprop': 'analysis.traversal.order={0}'.format(
                        algo_map[self.conf['VTG strategy']['graph traversal algorithm']])}
                )

            if 'verifier options' in self.conf['abstract task desc']:
                self.conf['VTG strategy']['verifier']['options'].extend(
                    self.conf['abstract task desc']['verifier options']
                )
        else:
            raise NotImplementedError(
                'Verifier {0} is not supported'.format(self.conf['VTG strategy']['verifier']['name']))


    def prepare_bug_kind_functions_file(self):
        self.logger.debug('Prepare bug kind functions file "bug kind funcs.c"')

        bug_kinds = []
        for extra_c_file in self.conf['abstract task desc']['extra C files']:
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
        self.conf['abstract task desc']['extra C files'].append({'C file': os.path.abspath('bug kind funcs.c')})

    def prepare_property_file(self):
        self.logger.info('Prepare verifier property file')

        if 'entry points' in self.conf['abstract task desc']:
            if len(self.conf['abstract task desc']['entry points']) > 1:
                raise NotImplementedError('Several entry points are not supported')

            if 'verifier specifications' in self.conf['abstract task desc']:
                with open('spec.prp', 'w', encoding='utf8') as fp:
                    for spec in self.conf['abstract task desc']['verifier specifications']:
                        fp.write('CHECK( init({0}()), {1} )\n'.format(
                            self.conf['abstract task desc']['entry points'][0], spec))
                property_file = 'spec.prp'

                self.logger.debug('Verifier property file was outputted to "spec.prp"')
            else:
                with open('unreach-call.prp', 'w', encoding='utf8') as fp:
                    fp.write('CHECK( init({0}()), LTL(G ! call(__VERIFIER_error())) )'.format(
                        self.conf['abstract task desc']['entry points'][0]))

                property_file = 'unreach-call.prp'

                self.logger.debug('Verifier property file was outputted to "unreach-call.prp"')
        else:
            raise ValueError('Verifier property file was not prepared since entry points were not specified')

        return property_file

