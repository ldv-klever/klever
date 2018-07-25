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

from core.lkvog.strategies import scotch
from core.lkvog.strategies import closure
from core.lkvog.strategies import advanced
from core.lkvog.strategies import strategies_list
from core.lkvog.strategies import strategy_utils
import core.components
import core.utils


@core.components.before_callback
def __launch_sub_job_components(context):
    context.mqs['Linux kernel attrs'] = multiprocessing.Queue()
    context.mqs['Linux kernel build cmd desc files'] = multiprocessing.Queue()
    context.mqs['Linux kernel module dependencies'] = multiprocessing.Queue()
    context.mqs['Linux kernel module sizes'] = multiprocessing.Queue()
    context.mqs['Linux kernel modules'] = multiprocessing.Queue()
    context.mqs['Linux kernel additional modules'] = multiprocessing.Queue()


@core.components.after_callback
def __set_linux_kernel_attrs(context):
    context.mqs['Linux kernel attrs'].put(context.linux_kernel['attrs'])


@core.components.after_callback
def __get_linux_kernel_build_cmd_desc(context):
    context.mqs['Linux kernel build cmd desc files'].put(context.linux_kernel['build cmd desc file'])


@core.components.after_callback
def __get_all_linux_kernel_build_cmd_descs(context):
    context.logger.info('Terminate Linux kernel build command descriptions message queue')
    context.mqs['Linux kernel build cmd desc files'].put(None)


class LKVOG(core.components.Component):
    def generate_linux_kernel_verification_objects(self):
        self.linux_kernel_verification_objs_gen = {}
        self.common_prj_attrs = {}
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

        # These dirs are excluded from cleaning by lkvog
        self.dynamic_excluded_clean = multiprocessing.Manager().list()

        self.extract_linux_kernel_verification_objs_gen_attrs()
        self.set_common_prj_attrs()
        core.utils.report(self.logger,
                          'attrs',
                          {
                              'id': self.id,
                              'attrs': self.linux_kernel_verification_objs_gen['attrs']
                          },
                          self.mqs['report files'],
                          self.vals['report id'],
                          self.conf['main working directory'])
        self.launch_subcomponents(True,
                                  ('ALKBCDP', self.process_all_linux_kernel_build_cmd_descs),
                                  ('AVODG', self.generate_all_verification_obj_descs))

        self.clean_dir = True
        self.excluded_clean = [d for d in self.dynamic_excluded_clean]
        self.logger.debug("Excluded {0}".format(self.excluded_clean))

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

    main = generate_linux_kernel_verification_objects

    def set_common_prj_attrs(self):
        self.logger.info('Set common project atributes')
        self.common_prj_attrs = self.linux_kernel_verification_objs_gen['attrs']

    def extract_linux_kernel_verification_objs_gen_attrs(self):
        self.logger.info('Extract Linux kernel verification objects generation strategy atributes')

        self.linux_kernel_verification_objs_gen['attrs'] = self.mqs['Linux kernel attrs'].get()
        self.mqs['Linux kernel attrs'].close()
        self.linux_kernel_verification_objs_gen['attrs'].extend([{
            'name': 'LKVOG strategy',
            'value': [{
                'name': 'name',
                'value': self.conf['LKVOG strategy']['name']
            }]
        }])

    def get_modules_from_deps(self, subsystem, deps):
        # Extract all modules in subsystem from dependencies.
        ret = set()
        for module_pred, _, module_succ in deps:
            if module_pred.startswith(subsystem):
                ret.add(module_pred)
            if module_succ.startswith(subsystem):
                ret.add(module_succ)

        return ret

    def is_part_of_subsystem(self, module, modules):
        # Returns true if module is a part of subsystem that contains in modules.
        for module2 in modules:
            if module.id.startswith(module2):
                return True
        else:
            return False

    def generate_all_verification_obj_descs(self):
        self.logger.info('Generate all verification object decriptions')

        strategy_name = self.conf['LKVOG strategy']['name']

        subsystems = list(filter(lambda target: not target.endswith('.ko'), self.conf['Linux kernel']['modules']))
        if 'external modules' in self.conf['Linux kernel']:
            subsystems = ['ext-modules/' + subsystem for subsystem in subsystems]

        self.linux_kernel_src = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                               self.conf['Linux kernel']['source'])

        if 'all' in self.conf['Linux kernel']['modules'] and not len(self.conf['Linux kernel']['modules']) == 1:
            raise ValueError('You can not specify "all" modules together with some other modules')

        module_deps_function = {}
        module_sizes = {}

        # If user specify files for multimodule analysis, then get them
        if 'module dependencies file' in self.conf['Linux kernel']:
            module_deps_function = self.mqs['Linux kernel module dependencies'].get()
        if 'module sizes file' in self.conf['Linux kernel']:
            module_sizes = self.mqs['Linux kernel module sizes'].get()

        to_build = None
        # Else, we should build all kernel if multimodule strategy is non-trivial
        if 'module dependencies file' not in self.conf['Linux kernel']:
            if strategy_name == 'separate modules':
                to_build = {'build kernel': False,
                            'modules': self.conf['Linux kernel']['modules']}
            elif strategy_name != 'manual':
                if 'external modules' not in self.conf['Linux kernel']:
                    to_build = {'build kernel': True,
                                'modules': []}

                else:
                    to_build = {'build kernel': True,
                                'modules': self.conf['Linux kernel']['modules']}

        if to_build:
            self.mqs['Linux kernel modules'].put(to_build)
            self.mqs['Linux kernel additional modules'].put(to_build)
            self.mqs['Linux kernel additional modules'].close()

            if to_build['build kernel']:
                module_deps_function = self.mqs['Linux kernel module dependencies'].get()
                module_sizes = self.mqs['Linux kernel module sizes'].get()

        self.mqs['Linux kernel module dependencies'].close()
        self.mqs['Linux kernel module sizes'].close()

        if strategy_name not in strategies_list:
            raise NotImplementedError("Strategy {0} not implemented".format(strategy_name))

        # Getting strategy
        strategy_params = {'module_deps_function': module_deps_function,
                           'work dir': os.path.abspath(os.path.join(self.conf['main working directory'],
                                                                    strategy_name)),
                           'module_sizes': module_sizes}
        strategy = strategies_list[strategy_name](self.logger, strategy_params, self.conf['LKVOG strategy'])

        # Make clusters for each module by the strategy
        build_modules = set()
        self.logger.debug("Initial list of modules to be built: {0}".format(self.conf['Linux kernel']['modules']))
        for kernel_module in self.conf['Linux kernel']['modules']:
            kernel_module = kernel_module if 'external modules' not in self.conf['Linux kernel'] \
                else 'ext-modules/' + kernel_module
            # Should replace .ko extension to .o
            kernel_module = re.sub('\.ko$', '.o', kernel_module)

            self.logger.debug('Use strategy for {0} module'.format(kernel_module))
            clusters = strategy.divide(kernel_module)
            self.all_clusters.update(clusters)
            for cluster in clusters:
                # Draw graph if need it
                if self.conf['LKVOG strategy'].get('draw graphs', False):
                    cluster.draw(".")
                # Build list of modules that will build
                for cluster_module in cluster.modules:
                    for subsystem in subsystems:
                        if cluster_module.id.startswith(subsystem):
                            break
                    else:
                        build_modules.add(cluster_module.id)

                    self.checked_modules.add(cluster_module.id)

        self.logger.debug('Final list of modules to be build: {0}'.format(build_modules))

        # If user specified files for multimodule analysis of strategy is manual,
        # then we should put modules that will be built
        if 'module dependencies file' in self.conf['Linux kernel'] or strategy_name == 'manual':
            if 'all' in self.conf['Linux kernel']['modules']:
                to_build = {'build kernel': False,
                            'modules': ('all',)}
                self.mqs['Linux kernel modules'].put({'build kernel': False,
                                                      'modules': ('all',)})
            else:
                prefix = 'ext-modules/'
                modules_to_build = [re.sub(r'\.o$', '.ko', module) for module in build_modules] + subsystems
                to_build = {'build kernel': False, 'modules':
                            [m if not m.startswith(prefix) else m[len(prefix):] for m in modules_to_build]}
            self.mqs['Linux kernel modules'].put(to_build)
            self.mqs['Linux kernel additional modules'].put(to_build)
            self.mqs['Linux kernel additional modules'].close()
        else:
            self.mqs['Linux kernel module dependencies'].close()
        self.logger.info('Generate all Linux kernel verification object decriptions')

        self.all_clusters = set([cluster for cluster in self.all_clusters
                                 if 'all' not in [module.id for module in cluster.modules]])

        # Process incoming modules
        cc_ready = set()
        while True:
            self.module = self.linux_kernel_module_info_mq.get()

            if self.module is None:
                self.logger.debug('Linux kernel module names message queue was terminated')
                self.linux_kernel_module_info_mq.close()
                break

            self.module = os.path.normpath(self.module)

            self.logger.debug('Recieved module {0}'.format(self.module))
            cc_ready.add(self.module)

            if self.module not in self.all_modules:
                # This modules is not checked
                module_clusters = []
                if self.module in self.checked_modules:
                    # This module is specified
                    self.all_modules.add(self.module)
                    # Find clusters for that module
                    for cluster in self.all_clusters:
                        if self.module in [module.id for module in cluster.modules]:
                            for cluster_module in cluster.modules:
                                if cluster_module.id not in cc_ready:
                                    break
                            else:
                                module_clusters.append(cluster)
                    # Remove clusters that will be checked.
                    self.all_clusters = set(filter(lambda cluster: cluster not in module_clusters,
                                                   self.all_clusters))
                elif self.module.startswith('ext-modules'):
                    # External module
                    self.all_modules.add(self.module)
                    self.checked_modules.add(strategy_utils.Module(self.module))
                    module_clusters.append(strategy_utils.Graph([strategy_utils.Module(self.module)]))
                else:
                    # This module hasn't specified. But it may be in subsystem
                    for subsystem in subsystems:
                        if subsystem != 'all' and subsystem[-1] != '/':
                            subsystem = subsystem + '/'
                        if self.module.startswith(subsystem) or \
                                self.module.startswith(os.path.join('ext-modules', subsystem)) or \
                                        subsystem == 'all':
                            self.all_modules.add(self.module)
                            self.checked_modules.add(strategy_utils.Module(self.module))
                            module_clusters.append(strategy_utils.Graph([strategy_utils.Module(self.module)]))

                # Generator verification object for that cluster
                for cluster in module_clusters:
                    self.cluster = cluster
                    self.generate_verification_obj_desc()

        # If we hasn't built all, should show error
        if self.all_clusters:
            not_builded = set()
            for cluster in self.all_clusters:
                not_builded |= set([module.id for module in cluster.modules]) - self.all_modules
            raise RuntimeError('Can not build following modules: {0}'.format(not_builded))

        # Generate lines of code
        self.send_loc_report()

        self.logger.info('The total number of verification object descriptions is "{0}"'.format(
            self.verification_obj_desc_num))

    def generate_verification_obj_desc(self):
        self.logger.info('Generate Linux kernel verification object description for module "{0}" ({1})'.
                         format(self.module, self.verification_obj_desc_num + 1))

        self.verification_obj_desc = {}

        self.verification_obj_desc['id'] = re.sub(r'\.o$', '.ko', self.cluster.root.id)

        if len(self.cluster.modules) > 1:
            self.verification_obj_desc['id'] += self.cluster.md5_hash

        self.logger.debug('Linux kernel verification object id is "{0}"'.format(self.verification_obj_desc['id']))

        self.verification_obj_desc['grps'] = []
        self.verification_obj_desc['deps'] = {}
        self.loc[self.verification_obj_desc['id']] = 0
        for module in self.cluster.modules:
            cc_full_desc_files = self.__find_cc_full_desc_files(module.id)
            self.verification_obj_desc['grps'].append({'id': module.id,
                                                       'cc full desc files': cc_full_desc_files})
            self.verification_obj_desc['deps'][module.id] = \
                [predecessor.id for predecessor in module.predecessors if predecessor in self.cluster.modules]
            self.loc[self.verification_obj_desc['id']] += self.__get_module_loc(cc_full_desc_files)

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
        os.makedirs(os.path.dirname(self.verification_obj_desc_file).encode('utf8'), exist_ok=True)

        # Add dir to exlcuded from cleaning by lkvog
        root_dir_id = self.verification_obj_desc_file.split('/')[0]
        if root_dir_id not in self.dynamic_excluded_clean:
            self.logger.debug("Add excl {0}".format(root_dir_id))
            self.dynamic_excluded_clean.append(root_dir_id)

        with open(self.verification_obj_desc_file, 'w', encoding='utf8') as fp:
            json.dump(self.verification_obj_desc, fp, ensure_ascii=False, sort_keys=True, indent=4)

        # Count the number of successfully generated verification object descriptions.
        self.verification_obj_desc_num += 1

    def process_all_linux_kernel_build_cmd_descs(self):
        self.logger.info('Process all Linux kernel build command decriptions')

        self.list_modules = set()

        # If user specified files for multimodule analysis, read them
        if 'module dependencies file' in self.conf['Linux kernel']:
            deps_file = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                     self.conf['Linux kernel']['module dependencies file'])
            with open(deps_file, encoding='utf-8') as fp:
                dependencies = self.parse_linux_kernel_mod_function_deps(fp)
                self.mqs['Linux kernel module dependencies'].put(dependencies)
                self.mqs['Linux kernel module dependencies'].close()

        if 'module sizes file' in self.conf['Linux kernel']:
            sizes_file = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                     self.conf['Linux kernel']['module sizes file'])
            with open(sizes_file, encoding='utf8') as fp:
                self.mqs['Linux kernel module sizes'].put(json.load(fp))
                self.mqs['Linux kernel module sizes'].close()

        # Get build info
        to_build = self.mqs['Linux kernel additional modules'].get()
        # Get user-specified (and extracted from multimodule analysis) modules to be built
        self.force_modules = set((m.replace('.ko', '.o') for m in to_build['modules']))

        while True:
            desc_file = self.mqs['Linux kernel build cmd desc files'].get()

            if desc_file is None:
                self.logger.debug('Linux kernel build command descriptions message queue was terminated')
                self.mqs['Linux kernel build cmd desc files'].close()
                self.logger.info('Terminate Linux kernel module names message queue')

                # If user didn't provide files for multimodule analysis and he uses multimodule strategy,
                # we should provide these dependencies
                if 'module dependencies file' not in self.conf['Linux kernel'] and to_build['build kernel']:
                    self.mqs['Linux kernel module dependencies'].put(self.__build_dependencies())
                    self.mqs['Linux kernel module dependencies'].close()
                if 'module sizes file' not in self.conf['Linux kernel'] and to_build['build kernel']:
                    self.mqs['Linux kernel module sizes'].put(self.__get_module_sizes())
                    self.mqs['Linux kernel module sizes'].close()

                self.linux_kernel_module_info_mq.put(None)
                break

            self.process_linux_kernel_build_cmd_desc(desc_file)

    def process_linux_kernel_build_cmd_desc(self, desc_file):
        with open(os.path.join(self.conf['main working directory'], desc_file), encoding='utf8') as fp:
            desc = json.load(fp)

        desc['out file'] = os.path.normpath(desc['out file'])
        desc['in files'] = [os.path.normpath(in_file) for in_file in desc['in files']]

        self.logger.info(
            'Process description of Linux kernel build command "{0}" {1}'.format(desc['type'],
                                                                                 '(output file is {0})'.format(
                                                                                     '"{0}"'.format(desc['out file'])
                                                                                     if desc['out file']
                                                                                     else 'not specified')))

        # Build map from Linux kernel build command output files to correpsonding descriptions.
        # If more than one build command has the same output file their descriptions are added as list in chronological
        # order (more early commands are processed more early and placed at the beginning of this list).
        self.linux_kernel_build_cmd_out_file_desc_lock.acquire()
        if desc['out file'] in self.linux_kernel_build_cmd_out_file_desc:
            self.linux_kernel_build_cmd_out_file_desc[desc['out file']] = self.linux_kernel_build_cmd_out_file_desc[
                                                                              desc['out file']] + [desc]
        else:
            self.linux_kernel_build_cmd_out_file_desc[desc['out file']] = [desc]
        self.linux_kernel_build_cmd_out_file_desc_lock.release()

        # Firstly, we should allow modules, that specified by user (force modules)
        # Secondly, we should allow modules, that ends with .ko and doesn't specified by user
        if (desc['type'] == 'LD' and desc['out file'].endswith('.ko')
            and desc['out file'].replace('.ko', '.o') not in self.force_modules) \
                or (desc['out file'].endswith('.o')
                    and desc['out file'].replace('ext-modules/', '') in self.force_modules):
            self.list_modules.add(desc['out file'])
            self.linux_kernel_module_info_mq.put(desc['out file'].replace('.ko', '.o'))

    def __find_cc_full_desc_files(self, out_file):
        self.logger.debug('Find CC full description files for "{0}"'.format(out_file))

        if out_file in self.cc_full_descs_files:
            self.logger.debug('CC full description files for "{0}" were already found'.format(out_file))
            return self.cc_full_descs_files[out_file]

        cc_full_desc_files = []
        # Get more older build commands more early if more than one build command has the same output file.
        self.linux_kernel_build_cmd_out_file_desc_lock.acquire()
        out_file_desc = self.linux_kernel_build_cmd_out_file_desc[out_file][-1]

        # Remove got build command description from map. It is assumed that each build command output file can be used
        # as input file of another build command just once.
        self.linux_kernel_build_cmd_out_file_desc[out_file] = self.linux_kernel_build_cmd_out_file_desc[out_file][:-1]
        self.linux_kernel_build_cmd_out_file_desc_lock.release()

        if out_file_desc:
            if out_file_desc['type'] == 'CC':
                # Do not include assembler files into verification objects since we have no means to instrument and to
                # analyse them.
                if not re.search(r'\.S$', out_file_desc['in files'][0], re.IGNORECASE):
                    cc_full_desc_files.append(out_file_desc['full desc file'])
            else:
                for in_file in out_file_desc['in files']:
                    cc_full_desc_files.extend(self.__find_cc_full_desc_files(in_file))

        self.cc_full_descs_files[out_file] = cc_full_desc_files
        
        return cc_full_desc_files

    def __get_module_loc(self, cc_full_desc_files):
        loc = 0
        for cc_full_desc_file in cc_full_desc_files:
            with open(os.path.join(self.conf['main working directory'], cc_full_desc_file), encoding='utf8') as fp:
                cc_full_desc = json.load(fp)
            for file in cc_full_desc['in files']:
                # Simple file's line counter
                with open(os.path.join(self.conf['main working directory'], cc_full_desc['cwd'], file),
                          encoding='utf8', errors='ignore') as fp:
                    loc += sum(1 for _ in fp)
        return loc

    def parse_linux_kernel_mod_function_deps(self, lines):
        dependencies = []
        for line in lines:

            # Remove newline symbols
            if line[-1] == '\n':
                line = line[:-1]

            line = re.subn(r'\.ko', '.o', line)[0]
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

    def __build_dependencies(self):
        reverse_provided = {}
        dependencies = []

        # Build a dictionary for extracting module by export function
        for module in self.list_modules:
            for desc in self.linux_kernel_build_cmd_out_file_desc[module]:
                for provided_function in desc.get('provided functions', tuple()):
                    reverse_provided[provided_function] = module.replace('.ko', '.o')

        for module in self.list_modules:
            for desc in self.linux_kernel_build_cmd_out_file_desc[module]:
                for required_function in desc.get('required functions', tuple()):
                    if required_function in reverse_provided:
                        dependencies.append((reverse_provided[required_function], required_function,
                                             module.replace('.ko', '.o')))

        self.logger.debug("Going to write deps")
        with open("dependencies.txt", 'w', encoding='utf-8') as fp:
            for m1, f, m2 in dependencies:
                fp.write('{0} needs "{1}": {2}\n'.format(m2, f, m1))

        return sorted(dependencies)

    def __get_module_sizes(self):
        sizes = {}

        for module in self.list_modules:
            for desc in self.linux_kernel_build_cmd_out_file_desc[module]:
                sizes[module.replace('.ko', '.o')] = desc.get('output size', 0)

        return sizes
