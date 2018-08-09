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
import ujson


class Abstract:

    def __init__(self, logger, conf, divider):
        self.logger = logger
        self.conf = conf
        self.divider = divider

        self._max_size = self.conf['VOG strategy'].get('maximum verification object size')
        self.dynamic_excluded_clean = list()

    @property
    def attributes(self):
        return [{
            'name': 'VOG strategy',
            'value': [{'name': 'name', 'value': self.conf['VOG strategy']['name']}]
        }]

    def generate_verification_objects(self):
        for aggregation in self._aggregate():
            if not self._max_size or aggregation.size <= self._max_size:
                self.__describe_verification_object(aggregation)
            else:
                self.logger.debug('verification object {!r} is rejected since it exceeds maximum size {}'.
                                  format(aggregation.name, aggregation.size()))

    def _aggregate(self):
        raise NotImplementedError

    def __describe_verification_object(self, aggregation):
        self.logger.info('Generate verification object description for aggregation {!r}'.format(aggregation.name))
        vo_desc = dict()
        vo_desc['id'] = aggregation.name
        vo_desc['grps'] = list()
        vo_desc['deps'] = dict()
        for unit in aggregation.units:
            vo_desc['grps'].append({'id': unit.name, 'CCs': unit.ccs})
            vo_desc['deps'][unit.name] = [pred.name for pred in unit.predecessors if pred in aggregation.units]
        self.logger.debug('verification object dependencies are {}'.format(vo_desc['deps']))

        vo_desc_file = vo_desc['id'] + '.json'
        if os.path.isfile(vo_desc_file):
            raise FileExistsError('verification object description file {!r} already exists'.format(vo_desc_file))
        self.logger.debug('Dump verification object description {!r} to file {!r}'.format(vo_desc['id'], vo_desc_file))
        dir_path = os.path.dirname(vo_desc_file).encode('utf8')
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # Add dir to exlcuded from cleaning by lkvog
        root_dir_id = vo_desc_file.split('/')[0]
        if root_dir_id not in self.dynamic_excluded_clean:
            self.logger.debug("Do not clean dir {!r} on component termination".format(root_dir_id))
            self.dynamic_excluded_clean.append(root_dir_id)

        with open(vo_desc_file, 'w', encoding='utf8') as fp:
            ujson.dump(vo_desc, fp, sort_keys=True, indent=4, ensure_ascii=False, escape_forward_slashes=False)

    # def generate_verification_objects(self, extracted_modules):
    #     self._extracted_modules = extracted_modules
    #     modules_in_clusters = set()
    #
    #     # todo: Many places where we got modules but without external ones (or it is Ok?)
    #     subsystems = list(filter(lambda target: self.is_subsystem(target), self.conf['project'].get('modules', [])))
    #     self.logger.debug("Subsystems are {0}".format(subsystems))
    #     strict = self.conf['VOG strategy'].get('strict subsystems filter', False)
    #     for module in self._modules:
    #         if module not in modules_in_clusters and self._modules[module].get('separate verify', True):
    #             if 'all' in self.conf['project'].get('modules', []):
    #                 self._all_clusters.update(self._common_divide(module))
    #             else:
    #                 # todo: Again ext modules specifics
    #                 if module in self.conf['project'].get('modules', []) or \
    #                         (module.startswith('ext-modules/') and
    #                          module[len('ext-modules/'):] in self.conf['project'].get('modules', [])):
    #                     clusters = self._common_divide(module)
    #                     self._add_new_clusters(clusters, modules_in_clusters)
    #                 else:
    #                     for subsystem in subsystems:
    #                         if self._is_module_in_subsystem(module, subsystem, strict):
    #                             clusters = self._common_divide(module)
    #                             self._add_new_clusters(clusters, modules_in_clusters)
    #                             break
    #
    #     for func in self.conf['project'].get('functions', []):
    #         clusters = self._divide_by_function(func)
    #         self._add_new_clusters(clusters, modules_in_clusters)
    #
    #     for cluster in self._all_clusters:
    #         self.logger.debug("Going to verify cluster")
    #         self._cluster = cluster
    #         self._module = cluster.root.id
    #         self._generate_verification_obj_desc()
    #
    # def _common_divide(self, mdle):
    #     self.logger.debug("Module is {0}".format(mdle))
    #     self.logger.debug("Graphs is {0}".format(self._graphs))
    #     self.logger.debug("Graphs subsystem is {0}".format(self._graphs_subsystems))
    #     if self._graphs is not None:
    #         if mdle in self._graphs:
    #             return self._graphs[mdle]
    #         for sbsys in self._graphs_subsystems:
    #             if mdle.startswith(sbsys):
    #                 self.logger.debug("Module in graphs subsystem")
    #                 self.logger.debug("{0}".format(self._graphs[sbsys]))
    #                 return self._graphs[sbsys]
    #         return self._graphs.get(mdle, [Graph([Module(mdle)])])
    #     else:
    #         return self._divide(mdle)
    #
    # def _divide_by_function(self, func):
    #     try:
    #         modules = self._get_modules_by_func(func)
    #     except FileNotFoundError:
    #         self.logger.debug("Not found files for {0} function".format(func))
    #         return []
    #     if not modules:
    #         self.logger.debug("Skipping {0} function".format(func))
    #         return []
    #     clusters = set()
    #     for module in modules:
    #         clusters.update(self._divide(module))
    #     return clusters
    #
    # def get_modules_to_build(self):
    #     """
    #     Returns list of modules to build and whether to build all
    #     """
    #     modules = (module if 'external source' not in self.conf['project'] else 'ext-modules/' + module for module in
    #                self.conf['project']['modules'])
    #     return modules, False
    #
    # def get_specific_files(self, files):
    #     return {}
    #
    # def get_specific_modules(self):
    #     return []
    #
    # def _divide(self, module):
    #     raise NotImplementedError
    #
    # def _collect_modules_to_build(self, modules):
    #     to_build = set()
    #     self._graphs = {}
    #     for module in modules:
    #         self._graphs[module] = self._divide(module)
    #         if self.is_subsystem(module):
    #             self._graphs_subsystems.add(module)
    #         for graph in self._graphs[module]:
    #             for m in graph.modules:
    #                 to_build.add(m.id)
    #
    #     return list(to_build)
    #
    # def _get_modules_by_func(self, func_name):
    #     files = self._get_files_by_func(func_name)
    #     res = []
    #     for file in files:
    #         res.append(self._get_module_by_file(file))
    #
    #     return res
    #
    # def _get_files_by_func(self, func_name):
    #     files = set()
    #     for func in self.callgraph:
    #         if func == func_name:
    #             files.update(filter(lambda x: x != 'unknown', list(self.callgraph[func].keys())))
    #     return list(files)
    #
    # def _get_module_by_file(self, file):
    #     # todo: ANother replacement
    #     cc = self.clade.get_cc()
    #     descs = cc.load_all_json_by_in(file)
    #     for desc in descs:
    #         for module, module_desc in self._extracted_modules.items():
    #             if desc['id'] in (int(cc) for cc in module_desc['CCs']):
    #                 return module
    #
    # def _get_modules_for_subsystem(self, subsystem):
    #     ret = []
    #     for module in self._extracted_modules:
    #         for cc_file in module['CCs']:
    #             if cc_file.startswith(subsystem):
    #                 ret.append(module)
    #                 break
    #
    #     return ret
    #
    # def _is_module_in_subsystem(self, module, subsystem, strict=False):
    #     if module not in self._extracted_modules:
    #         return False
    #
    #     for in_file in self._extracted_modules[module]['in files']:
    #         if in_file.startswith(subsystem):
    #             return True
    #     if module.startswith("ext-modules/"):
    #         module = module[len('ext-modules/'):]
    #     if module.startswith(subsystem):
    #         if strict:
    #             if os.path.dirname(module) == os.path.dirname(subsystem):
    #                 return True
    #         else:
    #             return True
    #     return False
    #
    # def _is_module(self, file):
    #     return file.endswith('.o') or file.endswith('.ko')
    #
    # def is_subsystem(self, file):
    #     # todo: this is an ugly workaround
    #     # todo: an option is to check a file extension
    #     return file.endswith('/')
    #
    # def _get_sizes(self):
    #     sizes = {}
    #     for module in self._modules:
    #         current_size = 0
    #         for cc in self._modules[module]['CCs']:
    #             desc = self.clade.get_cc().load_json_by_id(cc)
    #             for in_file in desc['in']:
    #                 try:
    #                     # todo: This used in several places and it is ugly
    #                     with open(self.clade.get_file(os.path.join(desc['cwd'], in_file))) as fp:
    #                         current_size += sum(1 for _ in fp)
    #                 except:
    #                     continue
    #         sizes[module] = current_size
    #
    #     return sizes
    #
    # def _get_dependencies(self):
    #     module_by_file = {}
    #     for module in self._modules:
    #         for file in self._modules[module]['in files']:
    #             module_by_file[file] = module
    #
    #     dependencies = []
    #     for func in self.callgraph:
    #         file = list(self.callgraph[func].keys())[0]
    #         module = module_by_file.get(file)
    #         if not module:
    #             continue
    #         for called_func in self.callgraph[func][file].get('calls', []):
    #             called_file = list(self.callgraph[func][file]['calls'][called_func].keys())[0]
    #             called_module = module_by_file.get(called_file)
    #             if not called_module:
    #                 continue
    #             if module != called_module:
    #                 dependencies.append((module, called_func, called_module))
    #
    #     return dependencies
    #
    # def _parse_sizes_from_file(self):
    #     if 'module sizes file' in self.conf['project']:
    #         sizes_file = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
    #                                                  self.conf['project']['module sizes file'])
    #         with open(sizes_file, encoding='utf8') as fp:
    #             return json.load(fp)
    #     else:
    #         return None
    #
    # def _parse_function_deps(self):
    #     # todo: Move this to linux strategy
    #     if self.conf['project'].get('module dependencies file'):
    #         deps_file = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
    #                                                 self.conf['project']['module dependencies file'])
    #         dependencies = []
    #         with open(deps_file, encoding='utf-8') as fp:
    #             for line in fp:
    #
    #                 # Remove newline symbols
    #                 if line[-1] == '\n':
    #                     line = line[:-1]
    #
    #                 #line = re.subn(r'\.ko', '.o', line)[0]
    #                 splts = line.split(' ')
    #
    #                 # Format is 'first_modules needs "func": second_module'
    #                 first_module = splts[0]
    #                 second_module = splts[3]
    #                 func = splts[2]
    #
    #                 # Remove quotes and semicolon around function
    #                 func = func[1:-2]
    #
    #                 KERNEL_PREFIX = 'kernel/'
    #                 EXTRA_PREFIX = 'extra/'
    #                 EXT_PREFIX = 'ext-modules/'
    #
    #                 # Remove 'kernel/' and useless path prefix
    #                 first_module, second_module = (m if not m.startswith(KERNEL_PREFIX) else m[len(KERNEL_PREFIX):]
    #                                                for m in (first_module, second_module))
    #
    #                 # Replace 'extra/' and remove useless path prefix
    #                 first_module, second_module = (m if not m.startswith(EXTRA_PREFIX) else EXT_PREFIX + m[len(EXTRA_PREFIX):]
    #                                                for m in (first_module, second_module))
    #
    #                 dependencies.append((second_module, func, first_module))
    #         self.is_deps = True
    #         return dependencies
    #     else:
    #         return None
    #
    # def _add_new_clusters(self, clusters, modules_in_clusters):
    #     self._all_clusters.update(clusters)
    #     for cluster in clusters:
    #         # Draw graph if need it
    #         if self.conf['LKVOG strategy'].get('draw graphs'):
    #             cluster.draw('.')
    #         modules_in_clusters.update([module.id for module in cluster.modules])
    #
    # def _generate_verification_obj_desc(self):
    #     self.logger.info('Generate project verification object description for module "{0}" ({1})'.
    #                      format(self._module, vo_desc_num + 1))
    #
    #     vo_desc = dict()
    #     # todo: This mess is linux specific and further code is also should be corrected
    #     vo_desc['id'] = re.sub(r'\.o$', '.ko', self._cluster.root.id)
    #
    #     if len(self._cluster.modules) > 1:
    #         vo_desc['id'] += self._cluster.md5_hash
    #
    #     self.logger.debug('project verification object id is "{0}"'.format(vo_desc['id']))
    #
    #     vo_desc['grps'] = []
    #     vo_desc['deps'] = {}
    #     self._loc[vo_desc['id']] = 0
    #     for module in self._cluster.modules:
    #         if module.id not in self._modules:
    #             raise Exception("Module {0} does not exist".format(module.id))
    #         ccs = self._modules[module.id]['CCs']
    #         vo_desc['grps'].append({'id': module.id, 'CCs': ccs})
    #         vo_desc['deps'][module.id] = \
    #             [predecessor.id for predecessor in module.predecessors if predecessor in self._cluster.modules]
    #         self._loc[vo_desc['id']] += self._sizes.get(module.id, 0)
    #
    #     # todo: Maybe this filters better to move to divider
    #     if 'maximum verification object size' in self.conf \
    #             and self._loc[vo_desc['id']] > self.conf['maximum verification object size']:
    #         self.logger.debug('project verification object "{0}" is rejected since it exceeds maximum size'.format(
    #             vo_desc['id']))
    #         vo_desc = None
    #         return
    #     elif 'minimum verification object size' in self.conf \
    #             and self._loc[vo_desc['id']] < self.conf['minimum verification object size']:
    #         self.logger.debug('project verification object "{0}" is rejected since it is less than minimum size'
    #                           .format(vo_desc['id']))
    #         vo_desc = None
    #         return
    #
    #     self.logger.debug('project verification object groups are "{0}"'.format(vo_desc['grps']))
    #
    #     self.logger.debug('project verification object dependencies are "{0}"'.
    #                       format(vo_desc['deps']))
    #
    #     vo_desc_file = '{0}.json'.format(vo_desc['id'])
    #     if os.path.isfile(vo_desc_file):
    #         raise FileExistsError('project verification object description file "{0}" already exists'.format(
    #             vo_desc_file))
    #     self.logger.debug('Dump project verification object description for module "{0}" to file "{1}"'.format(
    #         self._module, vo_desc_file))
    #     dir_path = os.path.dirname(vo_desc_file).encode('utf8')
    #     if dir_path:
    #         os.makedirs(dir_path, exist_ok=True)
    #
    #     # Add dir to exlcuded from cleaning by lkvog
    #     root_dir_id = vo_desc_file.split('/')[0]
    #     if root_dir_id not in self.dynamic_excluded_clean:
    #         self.logger.debug("Add excl {0}".format(root_dir_id))
    #         self.dynamic_excluded_clean.append(root_dir_id)
    #
    #     with open(vo_desc_file, 'w', encoding='utf8') as fp:
    #         json.dump(vo_desc, fp, ensure_ascii=False, sort_keys=True, indent=4)
    #
    #     # Count the number of successfully generated verification object descriptions.
    #     vo_desc_num += 1
    #
    # def _extract_functions_for_cluster(self, callgraph):
    #     result = set()
    #     if self.conf.get('autoextract functions') or 'functions' not in self.conf['project']:
    #         cc_files = set()
    #         for grp in vo_desc['grps']:
    #             for cc in grp['CCs']:
    #                 # todo: need to correct
    #                 cc_files.update(self.clade.get_cc().load_json_by_id(cc)['in'])
    #             for func, function_desc in callgraph['callgraph'].items():
    #                 for file, file_desc in function_desc.items():
    #                     if file_desc.get('type') == 'global' and file in cc_files:
    #                         result.add(func)
    #     elif self.conf['project']['functions']:
    #         result = set(self.conf['project']['functions']) & set(callgraph['callgraph'].keys())
    #         self.logger.debug("Functions intersect is {0}".format(result))
    #     return sorted(result)

