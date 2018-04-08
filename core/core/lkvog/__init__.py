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
import multiprocessing
import os
import re
import shutil
import tarfile

from clade import Clade

from core.lkvog.strategies import scotch
from core.lkvog.strategies import closure
from core.lkvog.strategies import advanced
from core.lkvog.strategies import strategies_list
from core.lkvog.strategies import strategy_utils

from core.lkvog.module_extractors import module_extractors_list

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
    def generate_linux_kernel_verification_objects(self):
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

        # These dirs are excluded from cleaning by lkvog
        self.dynamic_excluded_clean = multiprocessing.Manager().list()

        self.prepare_strategy()

        if not self.conf['Clade']['is base cached']:
            # Prepare Linux kernel working source tree and extract build commands exclusively but just with other
            # sub-jobs of a given job. It would be more properly to lock working source trees especially if different
            # sub-jobs use different trees (https://forge.ispras.ru/issues/6647).
            with self.locks['build']:
                self.build_linux_kernel()

        self.clade = Clade()
        self.clade.set_work_dir(self.conf['Clade']['base'], self.conf['Clade']['storage'])

        self.set_common_prj_attrs()

        self.generate_all_verification_obj_descs()

        self.clean_dir = True
        self.excluded_clean = [d for d in self.dynamic_excluded_clean]
        self.logger.debug("Excluded {0}".format(self.excluded_clean))

    def prepare_strategy(self):
        strategy_name = self.conf['LKVOG strategy']['name']
        if strategy_name not in strategies_list:
            raise NotImplementedError("Strategy {0} not implemented".format(strategy_name))

        self.dependencies = self._parse_linux_kernel_mod_function_deps()
        self.sizes = self._parse_sizes_from_file()
        strategy_params = {'work dir': os.path.abspath(os.path.join(self.conf['main working directory'],
                                                                    strategy_name))}
        self.strategy = strategies_list[strategy_name](self.logger, strategy_params, self.conf['LKVOG strategy'])
        if self.dependencies:
            self.strategy.set_dependencies(self.dependencies, self.sizes)

    def build_linux_kernel(self):
        try:
            src = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                              self.conf['Linux kernel']['source'])
        except FileNotFoundError:
            # Linux kernel source code is not provided in form of file or directory.
            src = self.conf['Linux kernel']['source']

        try:
            conf = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                               self.conf['Linux kernel']['configuration'])
        except FileNotFoundError:
            # Linux kernel configuration is not provided in form of file.
            conf = self.conf['Linux kernel']['configuration']

        arch = self.conf['Linux kernel'].get('architecture') or self.conf['architecture']

        build_jobs = str(core.utils.get_parallel_threads_num(self.logger, self.conf, 'Build'))

        if 'all' in self.conf['Linux kernel']['modules'] or 'functions' in self.conf['Linux kernel']:
            is_build_all_modules = True
            modules_to_build = []
        else:
            modules_to_build, is_build_all_modules = \
                self.strategy.get_modules_to_build(self.conf['Linux kernel']['modules'])

        modules_to_build = [module if not module.startswith('ext-modules/') else module[len('ext-modules/'):]
                            for module in modules_to_build]

        ext_modules = self.prepare_ext_modules()

        clade_conf = {
            'work_dir': self.conf['Clade']['base'],
            'remove_existing_work_dir': True,
            'storage_dir': self.conf['Clade']['storage'],
            'internal_extensions': ['CommandGraph', 'Callgraph'],
            'CC.with_system_header_files': False,
            'CommandGraph.as_picture': True,
            'Common.filter': ['.*?\\.tmp$'],
            'Common.filter_in': [
                '-',
                '/dev/null',
                'scripts/(?!mod/empty\\.c)',
                'kernel/.*?bounds.*?',
                'arch/x86/tools/relocs',
                'arch/x86/kernel/asm-offsets.c',
                '.*\.mod\.c'
            ],
            'Common.filter_out': [
                '/dev/null',
                '.*?\\.cmd$',
                '.*/built-in.o',
                'vmlinux'
            ],
            'global_data': {
                'search directories': core.utils.get_search_dirs(self.conf['main working directory'], abs_paths=True),
                'external modules': os.path.abspath(ext_modules) if ext_modules else None,
            },
            'extensions': [
                {
                    'name': 'FetchWorkSrcTree',
                    'use original source tree': self.conf['allow local source directories use'],
                    'src': src,
                    'work_src_tree': 'linux',
                    'Git repository': self.conf['Linux kernel'].get('Git repository')
                },
                {'name': 'MakeCanonicalWorkSrcTree'},
                # TODO: make in parallel since it helps much!
                {'name': 'CleanLinuxKernelWorkSrcTree'},
                {
                    'name': 'Execute',
                    'command': ['make', '-j', build_jobs, '-s', 'kernelversion'],
                    'save_output': True,
                    'output_key': 'Linux kernel version'
                },
                {
                    'name': 'ConfigureLinuxKernel',
                    'jobs': build_jobs,
                    'architecture': arch,
                    'configuration': conf,
                },
                {
                    'name': 'BuildLinuxKernel',
                    'jobs': build_jobs,
                    'architecture': arch,
                    'configuration': conf,
                    # TODO: indeed LKVOG strategies should set these parameters as well as some other ones.
                    'kernel': False,
                    'modules': modules_to_build if not is_build_all_modules else ["all"],
                    'external modules': ext_modules,
                    'model headers': self.mqs['model headers'].get(),
                    'intercept_commands': True,
                }
            ]
        }

        with open('clade.json', 'w', encoding='utf8') as fp:
            json.dump(clade_conf, fp, indent=4, sort_keys=True)

        core.utils.execute(self.logger, tuple(['clade', '--config', 'clade.json']))

    def generate_all_verification_obj_descs(self):
        module_extractor_name = self.conf['Module extractor']['name']
        if module_extractor_name not in module_extractors_list:
            raise NotImplementedError("Module extractor '{0}' has not implemented".format(module_extractor_name))
        self.module_extractor = module_extractors_list[module_extractor_name](self.logger,
                                                                              self.clade,
                                                                              self.conf['Module extractor'])
        self.modules = self.module_extractor.divide()
        self.strategy.set_clade(self.clade)
        self.strategy.set_modules(self.modules)

        if self.sizes is None:
            self.sizes = self._get_sizes()
        if self.dependencies is None and self.strategy.need_dependencies():
            self.dependencies = self._get_dependencies()
            self.strategy.set_dependencies(self.dependencies, self.sizes)
        if self.strategy.need_callgraph():
            callgraph = self.clade.get_callgraph()
            callgraph_dict = callgraph.load_callgraph()
            self.strategy.set_callgraph(callgraph_dict)

        modules_in_clusters = set()

        subsystems = list(filter(lambda target: self.strategy.is_subsystem(target),
                                 self.conf['Linux kernel']['modules']))
        for module in self.modules:
            if module not in modules_in_clusters:
                if 'all' in self.conf['Linux kernel']['modules']:
                    self.all_clusters.update(self.strategy.divide(module))
                else:
                    if module in self.conf['Linux kernel']['modules']:
                        clusters = self.strategy.divide(module)
                        self.add_new_clusters(clusters, modules_in_clusters)
                    else:
                        for subsystem in subsystems:
                            if module.startswith(subsystem):
                                clusters = self.strategy.divide(module)
                                self.add_new_clusters(clusters, modules_in_clusters)
                                break

        for function in self.conf['Linux kernel'].get('functions', []):
            clusters = self.strategy.divide_by_function(function)
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

    def prepare_ext_modules(self):
        if 'external modules' not in self.conf['Linux kernel']:
            return None

        work_src_tree = 'ext-modules'

        self.logger.info(
            'Fetch source code of external Linux kernel modules from "{0}" to working source tree "{1}"'
            .format(self.conf['Linux kernel']['external modules'], work_src_tree))

        src = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                          self.conf['Linux kernel']['external modules'])

        if os.path.isdir(src):
            self.logger.debug('External Linux kernel modules source code is provided in form of source tree')
            shutil.copytree(src, work_src_tree, symlinks=True)
        elif os.path.isfile(src):
            self.logger.debug('External Linux kernel modules source code is provided in form of archive')
            with tarfile.open(src, encoding='utf8') as TarFile:
                TarFile.extractall(work_src_tree)

        self.logger.info('Make canonical working source tree of external Linux kernel modules')
        work_src_tree_root = None
        for dirpath, dirnames, filenames in os.walk(work_src_tree):
            ismakefile = False
            for filename in filenames:
                if filename == 'Makefile':
                    ismakefile = True
                    break

            # Generate Linux kernel module Makefiles recursively starting from source tree root directory if they do not
            # exist.
            if self.conf['generate makefiles']:
                if not work_src_tree_root:
                    work_src_tree_root = dirpath

                if not ismakefile:
                    with open(os.path.join(dirpath, 'Makefile'), 'w', encoding='utf-8') as fp:
                        fp.write('obj-m += $(patsubst %, %/, $(notdir $(patsubst %/, %, {0})))\n'
                                 .format('$(filter %/, $(wildcard $(src)/*/))'))
                        fp.write('obj-m += $(notdir $(patsubst %.c, %.o, $(wildcard $(src)/*.c)))\n')
                        # Specify additional directory to search for model headers. We assume that this directory is
                        # preserved as is at least during solving a given job. So, we treat headers from it as system
                        # ones, i.e. headers that aren't copied when .
                        fp.write('ccflags-y += -isystem ' + os.path.abspath(os.path.dirname(
                            core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                        self.conf['rule specifications DB']))))
            elif ismakefile:
                work_src_tree_root = dirpath
                break

        if not work_src_tree_root:
            raise ValueError('Could not find Makefile in working source tree "{0}"'.format(work_src_tree))
        elif not os.path.samefile(work_src_tree_root, work_src_tree):
            self.logger.debug('Move contents of "{0}" to "{1}"'.format(work_src_tree_root, work_src_tree))
            for path in os.listdir(work_src_tree_root):
                shutil.move(os.path.join(work_src_tree_root, path), work_src_tree)
            trash_dir = work_src_tree_root
            while True:
                parent_dir = os.path.join(trash_dir, os.path.pardir)
                if os.path.samefile(parent_dir, work_src_tree):
                    break
                trash_dir = parent_dir
            self.logger.debug('Remove "{0}"'.format(trash_dir))
            shutil.rmtree(os.path.realpath(trash_dir))

        return work_src_tree

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

        clade_global_data = self.clade.get_global_data()

        self.common_prj_attrs = [
            {'Linux kernel': [
                {'version': clade_global_data['Linux kernel version'][0]},
                {'architecture': clade_global_data['Linux kernel architecture']},
                {'configuration': clade_global_data['Linux kernel configuration']}
            ]},
            {'LKVOG strategy': [{'name': self.conf['LKVOG strategy']['name']}]}
        ]

        core.utils.report(self.logger,
                          'attrs',
                          {
                              'id': self.id,
                              'attrs': self.common_prj_attrs
                          },
                          self.mqs['report files'],
                          self.vals['report id'],
                          self.conf['main working directory'])

    def _get_sizes(self):
        #TODO implement me
        return None

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
            if module.id not in self.modules:
                raise Exception("Module {0} does not exist".format(module.id))
            ccs = self.modules[module.id]['CCs']
            self.verification_obj_desc['grps'].append({'id': module.id, 'CCs': ccs})
            self.verification_obj_desc['deps'][module.id] = \
                [predecessor.id for predecessor in module.predecessors if predecessor in self.cluster.modules]
            self.loc[self.verification_obj_desc['id']] += self.__get_module_loc(ccs)

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

        with open(self.verification_obj_desc_file, 'w', encoding='utf8') as fp:
            json.dump(self.verification_obj_desc, fp, ensure_ascii=False, sort_keys=True, indent=4)

        # Count the number of successfully generated verification object descriptions.
        self.verification_obj_desc_num += 1

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

    def __get_module_loc(self, cc_full_desc_files):
        loc = 0
        return loc
        # TODO: get from clade
        for cc_full_desc_file in cc_full_desc_files:
            #TODO extract files more accurately
            with open(os.path.join(self.conf['main working directory'], cc_full_desc_file), encoding='utf8') as fp:
            #with open(os.path.join(self.conf['main working directory'], cc_full_desc_file), encoding='utf8') as fp:
                cc_full_desc = json.load(fp)
            for file in cc_full_desc['in']:
                # Simple file's line counter
                #TODO extact files more accurately
                with open(file) as fp:
                #with open(os.path.join(self.conf['main working directory'], cc_full_desc['cwd'], file),
                          #encoding='utf8', errors='ignore') as fp:
                    loc += sum(1 for _ in fp)
        return loc

    def _parse_linux_kernel_mod_function_deps(self):
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
        for dir in os.listdir(self.linux_kernel['work src tree']):
            # Skip dirs that doesn't contain Makefile or Kconfig file
            if os.path.isdir(os.path.join(self.linux_kernel['work src tree'], dir)) \
                    and os.path.isfile(os.path.join(self.linux_kernel['work src tree'], dir, 'Makefile')) \
                    and os.path.isfile(os.path.join(self.linux_kernel['work src tree'], dir, 'Kconfig')):
                # Run script that creates 'modules.builtin' file
                core.utils.execute(self.logger, ['make', '-f', os.path.join('scripts', 'Makefile.modbuiltin'),
                                                 'obj={0}'.format(dir), 'srctree=.'],
                                   cwd=self.linux_kernel['work src tree'])

        # Just walk through the dirs and process 'modules.builtin' files
        result_modules = set()
        for dir, dirs, files in os.walk(self.linux_kernel['work src tree']):
            if os.path.samefile(self.linux_kernel['work src tree'], dir):
                continue
            if 'modules.builtin' in files:
                with open(os.path.join(dir, 'modules.builtin'), 'r', encoding='utf-8') as fp:
                    for line in fp:
                        result_modules.add(line[len('kernel/'):-1])
        return result_modules

    """
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
    """

    """
    def __get_module_sizes(self):
        sizes = {}

        for module in self.list_modules:
            for desc in self.linux_kernel_build_cmd_out_file_desc[module]:
                sizes[module.replace('.ko', '.o')] = desc.get('output size', 0)

        return sizes
    """
