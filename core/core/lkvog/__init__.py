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
import multiprocessing
import os
import re
import shutil
import tarfile

from core.lkvog.module_extractors import get_module_extractor
from core.lkvog.strategies import get_division_strategy
from core.lkvog.projects import get_source_adapter

import core.components
import core.utils


@core.components.before_callback
def __launch_sub_job_components(context):
    context.mqs['Linux kernel module dependencies'] = multiprocessing.Queue()
    context.mqs['Linux kernel module sizes'] = multiprocessing.Queue()
    context.mqs['Linux kernel modules'] = multiprocessing.Queue()
    context.mqs['Linux kernel additional modules'] = multiprocessing.Queue()
    context.mqs['model headers'] = multiprocessing.Queue()


@core.components.after_callback
def __set_model_headers(context):
    context.mqs['model headers'].put(context.model_headers)


class LKVOG(core.components.Component):
    def __init__(self, conf, logger, parent_id, callbacks, mqs, locks, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False):
        super(LKVOG, self).__init__(conf, logger, parent_id, callbacks, mqs, locks, vals, id, work_dir, attrs,
                                    separate_from_parent, include_child_resources)

        # todo: Why all attributes are public?
        self.clade = None
        self.linux_kernel_build_cmd_out_file_desc = multiprocessing.Manager().dict()
        self.linux_kernel_build_cmd_out_file_desc_lock = multiprocessing.Manager().Lock()
        self.linux_kernel_module_info_mq = multiprocessing.Queue()
        self.linux_kernel_clusters_mq = multiprocessing.Queue()
        self.module = {}
        self.all_modules = set()
        self.verification_obj_desc = {}
        self.all_clusters = set()
        self.checked_modules = set()
        self.loc = {}
        self.cc_full_descs_files = {}
        self.verification_obj_desc_file = None
        self.verification_obj_desc_num = 0
        self.dependencies = None
        self.sizes = None
        self.strategy = None
        self.module_extractor = None
        self.modules = None
        self.cluster = None
        self.verification_obj_desc = {}
        self.linux_kernel = {}

        # These dirs are excluded from cleaning by lkvog
        self.dynamic_excluded_clean = multiprocessing.Manager().list()

    def generate_verification_objects(self):
        adapter = get_source_adapter(self.conf['project']['name'])
        strategy = get_division_strategy(self.conf['VOG strategy']['name'])
        divider = get_module_extractor(self.conf['VOG extractor']['name'])

        # todo: This trash we need to move somewhere
        self.dependencies = self._parse_linux_kernel_mod_function_deps()
        self.sizes = self._parse_sizes_from_file()
        if self.dependencies:
            self.strategy.set_dependencies(self.dependencies, self.sizes)

        strategy = strategy(self.logger, self.conf['VOG strategy'])
        adapter = adapter(self.logger, self.conf)

        if not self.conf['project']['is base cached']:
            # Prepare Linux kernel working source tree and extract build commands exclusively but just with other
            # sub-jobs of a given job. It would be more properly to lock working source trees especially if different
            # sub-jobs use different trees (https://forge.ispras.ru/issues/6647).
            with self.locks['build']:
                self.prepare_and_build()

        # self.clade = Clade()
        # self.clade.set_work_dir(self.conf['Clade']['base'], self.conf['Clade']['storage'])

        # todo: Set them according to strategy and project
        # self.common_prj_attrs = [
        #     {
        #         'name': 'Linux kernel',
        #         'value': [{'name': name, 'value': value} for name, value in self.linux_kernel.items()]
        #     },
        #     # TODO: this is of course incomplete list of attributes but it is the as in master.
        #     {
        #         'name': 'LKVOG strategy',
        #         'value': [{'name': 'name', 'value': self.conf['LKVOG strategy']['name']}]
        #     }
        # ]
        self.set_common_prj_attrs()
        core.utils.report(self.logger,
                          'attrs',
                          {
                              'id': self.id,
                              'attrs': self.common_prj_attrs
                          },
                          self.mqs['report files'],
                          self.vals['report id'],
                          self.conf['main working directory'])

        self.generate_all_verification_obj_descs()

        self.clean_dir = True
        self.excluded_clean = [d for d in self.dynamic_excluded_clean]
        self.logger.debug("Excluded {0}".format(self.excluded_clean))

    def prepare_and_build(self, strategy, adapter):
        self.logger.info("Wait for model headers from VOG")
        model_headers = self.mqs["model headers"].get()
        # todo: refactor options below
        modules_to_build, is_build_all_modules = \
            strategy.get_modules_to_build((module if 'external modules' not in self.conf['source']
                                           else 'ext-modules/' + module for module in
                                           self.conf['project']['modules']))
        adapter.configure()
        adapter.build(modules_to_build, is_build_all_modules)

    def generate_all_verification_obj_descs(self):
        # todo: also get the list of all strategies dinamically
        module_extractor_name = self.conf['Module extractor']['name']
        if module_extractor_name not in module_extractors_list:
            raise NotImplementedError("Module extractor '{0}' has not implemented".format(module_extractor_name))

        self.strategy.set_clade(self.clade)
        if self.strategy.need_callgraph():
            callgraph = self.clade.get_callgraph()
            callgraph_dict = callgraph.load_callgraph()
            self.strategy.set_callgraph(callgraph_dict)

        extractor_conf = {}
        extractor_conf.update(self.conf['Module extractor'])
        extractor_conf.update({
            'specific files': self.strategy.get_specific_files(self.conf['Linux kernel'].get('modules', [])),
            'specific modules': self.strategy.get_specific_modules()
        })
        self.logger.debug('Specific files are {0}'.format(str(extractor_conf['specific modules'])))
        self.modules = divider.divide()
        self.logger.debug("Modules are {0}".format(json.dumps(self.modules, indent=4, sort_keys=True)))
        self.strategy.set_modules(self.modules)
        if self.sizes is None:
            self.sizes = self._get_sizes()
        if self.dependencies is None and self.strategy.need_dependencies():
            self.dependencies = self._get_dependencies()
            self.strategy.set_dependencies(self.dependencies, self.sizes)

        modules_in_clusters = set()

        subsystems = list(filter(lambda target: self.strategy.is_subsystem(target),
                                 self.conf['Linux kernel'].get('modules', [])))
        self.logger.debug("Subsystems are {0}".format(subsystems))
        strict = self.conf['Linux kernel'].get('strict subsystems filter', False)
        for module in sorted(self.modules):
            if module not in modules_in_clusters and self.modules[module].get('separate verify', True):
                if 'all' in self.conf['Linux kernel'].get('modules', []):
                    self.all_clusters.update(self.strategy.divide(module))
                else:
                    if module in self.conf['Linux kernel'].get('modules', []) \
                            or (module.startswith('ext-modules/')
                                and module[len('ext-modules/'):] in self.conf['Linux kernel'].get('modules', [])):
                        clusters = self.strategy.divide(module)
                        self.add_new_clusters(clusters, modules_in_clusters)
                    else:
                        for subsystem in subsystems:
                            if self.strategy.is_module_in_subsystem(module, subsystem, strict):
                                clusters = self.strategy.divide(module)
                                self.add_new_clusters(clusters, modules_in_clusters)
                                break

        for func in self.conf['Linux kernel'].get('functions', []):
            clusters = self.strategy.divide_by_function(func)
            self.add_new_clusters(clusters, modules_in_clusters)

        for cluster in self.all_clusters:
            self.logger.debug("Going to verify cluster")
            self.cluster = cluster
            self.module = cluster.root.id
            self.generate_verification_obj_desc()

    def add_new_clusters(self, clusters, modules_in_clusters):
        self.all_clusters.update(clusters)
        for cluster in clusters:
            # Draw graph if need it
            if self.conf['LKVOG strategy'].get('draw graphs'):
                cluster.draw('.')
            modules_in_clusters.update([module.id for module in cluster.modules])

    def send_loc_report(self):
        core.utils.report(self.logger,
                          'data',
                          {
                              'id': self.id,
                              'data': self.loc
                          },
                          self.mqs['report files'],
                          self.vals['report id'],
                          self.conf['main working directory'])

    main = generate_verification_objects

    def _get_sizes(self):
        sizes = {}
        for module in self.modules:
            current_size = 0
            for cc in self.modules[module]['CCs']:
                desc = self.clade.get_cc().load_json_by_id(cc)
                for in_file in desc['in']:
                    try:
                        with open(self.clade.get_file(os.path.join(desc['cwd'], in_file))) as fp:
                            current_size += sum(1 for _ in fp)
                    except:
                        continue
            sizes[module] = current_size

        return sizes

    def generate_verification_obj_desc(self):
        self.logger.info('Generate Linux kernel verification object description for module "{0}" ({1})'.
                         format(self.module, self.verification_obj_desc_num + 1))

        self.verification_obj_desc = dict()
        # todo: This mess is linux specific and further code is also should be corrected
        self.verification_obj_desc['id'] = re.sub(r'\.o$', '.ko', self.cluster.root.id)

        if len(self.cluster.modules) > 1:
            self.verification_obj_desc['id'] += self.cluster.md5_hash

        self.logger.debug('Linux kernel verification object id is "{0}"'.format(self.verification_obj_desc['id']))

        self.verification_obj_desc['grps'] = []
        self.verification_obj_desc['deps'] = {}
        self.loc[self.verification_obj_desc['id']] = 0
        for module in self.cluster.modules:
            if module.id not in self.modules:
                raise Exception("Module {0} does not exist".format(module.id))
            ccs = self.modules[module.id]['CCs']
            self.verification_obj_desc['grps'].append({'id': module.id, 'CCs': ccs})
            self.verification_obj_desc['deps'][module.id] = \
                [predecessor.id for predecessor in module.predecessors if predecessor in self.cluster.modules]
            self.loc[self.verification_obj_desc['id']] += self.sizes.get(module.id, 0)

        if 'maximum verification object size' in self.conf \
                and self.loc[self.verification_obj_desc['id']] > self.conf['maximum verification object size']:
            self.logger.debug('Linux kernel verification object "{0}" is rejected since it exceeds maximum size'.format(
                self.verification_obj_desc['id']))
            self.verification_obj_desc = None
            return
        elif 'minimum verification object size' in self.conf \
                and self.loc[self.verification_obj_desc['id']] < self.conf['minimum verification object size']:
            self.logger.debug('Linux kernel verification object "{0}" is rejected since it is less than minimum size'
                              .format(self.verification_obj_desc['id']))
            self.verification_obj_desc = None
            return

        self.logger.debug(
            'Linux kernel verification object groups are "{0}"'.format(self.verification_obj_desc['grps']))

        self.logger.debug(
            'Linux kernel verification object dependencies are "{0}"'.format(self.verification_obj_desc['deps']))

        self.verification_obj_desc_file = '{0}.json'.format(self.verification_obj_desc['id'])
        if os.path.isfile(self.verification_obj_desc_file):
            raise FileExistsError('Linux kernel verification object description file "{0}" already exists'.format(
                self.verification_obj_desc_file))
        self.logger.debug('Dump Linux kernel verification object description for module "{0}" to file "{1}"'.format(
            self.module, self.verification_obj_desc_file))
        dir_path = os.path.dirname(self.verification_obj_desc_file).encode('utf8')
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # Add dir to exlcuded from cleaning by lkvog
        root_dir_id = self.verification_obj_desc_file.split('/')[0]
        if root_dir_id not in self.dynamic_excluded_clean:
            self.logger.debug("Add excl {0}".format(root_dir_id))
            self.dynamic_excluded_clean.append(root_dir_id)

        callgraph = self._generate_analysis_data()
        callgraph_file = "{0}_callgraph.json".format(self.verification_obj_desc['id'])
        self.verification_obj_desc['callgraph'] = os.path.relpath(os.path.join(os.path.curdir, callgraph_file),
                                                                  os.path.join(self.conf["main working directory"],
                                                                               os.path.pardir))
        with open(callgraph_file, 'w', encoding='utf-8') as fp:
            json.dump(callgraph, fp, ensure_ascii=False, sort_keys=True, indent=4)

        functions = self._extract_functions_for_cluster(callgraph)
        if functions:
            functions_file = "{0}_functions.json".format(self.verification_obj_desc['id'])
            self.verification_obj_desc['functions'] = os.path.relpath(os.path.join(os.path.curdir, functions_file),
                                                                      os.path.join(self.conf['main working directory'],
                                                                                   os.path.pardir))
            with open(functions_file, 'w', encoding='utf-8') as fp:
                json.dump(functions, fp, ensure_ascii=False, sort_keys=True, indent=4)

        with open(self.verification_obj_desc_file, 'w', encoding='utf8') as fp:
            json.dump(self.verification_obj_desc, fp, ensure_ascii=False, sort_keys=True, indent=4)

        # Count the number of successfully generated verification object descriptions.
        self.verification_obj_desc_num += 1

    def _extract_functions_for_cluster(self, callgraph):
        result = set()
        if self.conf.get('autoextract functions') or 'functions' not in self.conf['Linux kernel']:
            cc_files = set()
            for grp in self.verification_obj_desc['grps']:
                for cc in grp['CCs']:
                    cc_files.update(self.clade.get_cc().load_json_by_id(cc)['in'])
                for function, function_desc in callgraph['callgraph'].items():
                    for file, file_desc in function_desc.items():
                        if file_desc.get('type') == 'global' and file in cc_files:
                            result.add(function)
        elif self.conf['Linux kernel']['functions']:
            result = set(self.conf['Linux kernel']['functions']) & set(callgraph['callgraph'].keys())
            self.logger.debug("Functions intersect is {0}".format(result))
        return sorted(result)

    def _generate_analysis_data(self):
        call_graph = self.clade.get_callgraph()

        allowed_files = set()
        cc = self.clade.get_cc()

        # Collect all files that will be included into group callgraph
        for grp in self.verification_obj_desc['grps']:
            for file in grp['CCs']:
                full_desc = cc.load_json_by_id(file)
                allowed_files.update(full_desc['deps'].values())
                allowed_files.update(full_desc['in'])

        allowed_files.add("unknown")

        return {
            'callgraph': self._generate_callgraph(allowed_files, call_graph),
            'variables': self._generate_variables(allowed_files, call_graph),
            'macros': self._generate_macros(allowed_files, call_graph),
            'typedefs': self._generate_typedefs(allowed_files, call_graph)
        }

    # todo: functions below are static mostly and required to covert callgraph, so it is better to extract them to a separate file
    @staticmethod
    def _generate_callgraph(allowed_files, call_graph):
        call_graph_dict = call_graph.load_detailed_callgraph(allowed_files)
        group_callgraph = {}

        # todo: Compile a new callgraph especially from allowed files
        for func, files in call_graph_dict.items():
            for file, descs in files.items():
                # Firstly, copy all desc
                group_callgraph.setdefault(func, {})
                group_callgraph[func][file] = dict(descs)

                # Then, for these four types ('declared_in' also) clear and fill with only allowed files
                for tag in ('called_in', 'calls', 'used_in_func'):
                    if tag in descs:
                        group_callgraph[func][file][tag] = {}
                        for called_func, called_files in descs[tag].items():
                            for called_file, called_file_descs in called_files.items():
                                if called_file in allowed_files:
                                    group_callgraph[func][file][tag].setdefault(called_func, {})
                                    group_callgraph[func][file][tag][called_func][called_file] = called_file_descs
                if 'declared_in' in descs:
                    group_callgraph[func][file]['declared_in'] = {}
                    for decl_file, decl_descs in descs['declared_in'].items():
                        if decl_file in allowed_files:
                            group_callgraph[func][file]['declared_in'].setdefault(decl_file, {})
                            group_callgraph[func][file]['declared_in'][decl_file] = decl_descs

                # Remove if empty
                if not group_callgraph[func][file].get('called_in') \
                        and not group_callgraph[func][file].get('calls') \
                        and not group_callgraph[func][file].get('declared_in') \
                        and not group_callgraph[func][file].get('used_in_func'):
                    group_callgraph[func][file] = {}

                # Remove if empty
                if func in group_callgraph and not group_callgraph[func].get(file, True):
                    del group_callgraph[func][file]
            # Remove if empty
            if not group_callgraph.get(func, True):
                del group_callgraph[func]
        return group_callgraph

    @staticmethod
    def _generate_variables(allowed_files, call_graph):
        variables_dict = call_graph.load_variables()
        group_variables = []
        for var_desc in variables_dict:
            if var_desc.get('path') in allowed_files:
                group_variables.append(var_desc)
        return group_variables

    @staticmethod
    def _generate_macros(allowed_files, call_graph):
        macros_dict = call_graph.load_macros()
        group_macros = {}
        for macro, macro_desc in macros_dict.items():
            new_macro_desc = {}
            for file, desc in macro_desc.items():
                if file in allowed_files:
                    new_macro_desc[file] = desc
            if new_macro_desc:
                group_macros[macro] = new_macro_desc
        return group_macros

    @staticmethod
    def _generate_typedefs(allowed_files, call_graph):
        typedefs_dict = call_graph.load_typedefs()
        typedefs = {}
        for file, desc in typedefs_dict.items():
            if file in allowed_files:
                typedefs[file] = desc
        return typedefs

    def _get_dependencies(self):
        module_by_file = {}
        for module in self.modules:
            for file in self.modules[module]['in files']:
                module_by_file[file] = module

        call_graph = self.clade.get_callgraph()
        call_graph_dict = call_graph.load_callgraph()
        dependencies = []
        for func in call_graph_dict:
            file = list(call_graph_dict[func].keys())[0]
            module = module_by_file.get(file)
            if not module:
                continue
            for called_func in call_graph_dict[func][file].get('calls', []):
                called_file = list(call_graph_dict[func][file]['calls'][called_func].keys())[0]
                called_module = module_by_file.get(called_file)
                if not called_module:
                    continue
                if module != called_module:
                    dependencies.append((module, called_func, called_module))

        return dependencies

    def _parse_linux_kernel_mod_function_deps(self):
        # todo Linux specifics again
        if 'module dependencies file' in self.conf['Linux kernel']:
            deps_file = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                    self.conf['Linux kernel']['module dependencies file'])
            dependencies = []
            with open(deps_file, encoding='utf-8') as fp:
                for line in fp:

                    # Remove newline symbols
                    if line[-1] == '\n':
                        line = line[:-1]

                    #line = re.subn(r'\.ko', '.o', line)[0]
                    splts = line.split(' ')

                    # Format is 'first_modules needs "func": second_module'
                    first_module = splts[0]
                    second_module = splts[3]
                    func = splts[2]

                    # Remove quotes and semicolon around function
                    func = func[1:-2]

                    KERNEL_PREFIX = 'kernel/'
                    EXTRA_PREFIX = 'extra/'
                    EXT_PREFIX = 'ext-modules/'

                    # Remove 'kernel/' and useless path prefix
                    first_module, second_module = (m if not m.startswith(KERNEL_PREFIX) else m[len(KERNEL_PREFIX):]
                                                for m in (first_module, second_module))

                    # Replace 'extra/' and remove useless path prefix
                    first_module, second_module = (m if not m.startswith(EXTRA_PREFIX) else EXT_PREFIX + m[len(EXTRA_PREFIX):]
                                                for m in (first_module, second_module))

                    dependencies.append((second_module, func, first_module))
            return dependencies
        else:
            return None

    def _parse_sizes_from_file(self):
        if 'module sizes file' in self.conf['Linux kernel']:
            sizes_file = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                     self.conf['Linux kernel']['module sizes file'])
            with open(sizes_file, encoding='utf8') as fp:
                return json.load(fp)
        else:
            return None

    def __get_builtin_modules(self):
        for subsystem in os.listdir(self.linux_kernel['work src tree']):
            # Skip dirs that doesn't contain Makefile or Kconfig file
            if os.path.isdir(os.path.join(self.linux_kernel['work src tree'], subsystem)) \
                    and os.path.isfile(os.path.join(self.linux_kernel['work src tree'], subsystem, 'Makefile')) \
                    and os.path.isfile(os.path.join(self.linux_kernel['work src tree'], subsystem, 'Kconfig')):
                # Run script that creates 'modules.builtin' file
                core.utils.execute(self.logger, ['make', '-f', os.path.join('scripts', 'Makefile.modbuiltin'),
                                                 'obj={0}'.format(subsystem), 'srctree=.'],
                                   cwd=self.linux_kernel['work src tree'])

        # Just walk through the dirs and process 'modules.builtin' files
        result_modules = set()
        for subsystem, dirs, files in os.walk(self.linux_kernel['work src tree']):
            if os.path.samefile(self.linux_kernel['work src tree'], subsystem):
                continue
            if 'modules.builtin' in files:
                with open(os.path.join(subsystem, 'modules.builtin'), 'r', encoding='utf-8') as fp:
                    for line in fp:
                        result_modules.add(line[len('kernel/'):-1])
        return result_modules
