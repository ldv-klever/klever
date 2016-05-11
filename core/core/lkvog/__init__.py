#!/usr/bin/python3

import copy
import json
import multiprocessing
import os
import re

from core.lkvog.strategies import scotch
from core.lkvog.strategies import closure
from core.lkvog.strategies import strategy1
from core.lkvog.strategies import strategies_list
from core.lkvog.strategies import module
import core.components
import core.utils


def before_launch_all_components(context):
    context.mqs['Linux kernel attrs'] = multiprocessing.Queue()
    context.mqs['Linux kernel build cmd descs'] = multiprocessing.Queue()
    context.mqs['Linux kernel module deps'] = multiprocessing.Queue()
    context.mqs['Linux kernel module deps function'] = multiprocessing.Queue()
    context.mqs['Linux kernel module sizes'] = multiprocessing.Queue()
    context.mqs['Linux kernel modules'] = multiprocessing.Queue()
    context.mqs['Additional modules'] = multiprocessing.Queue()


def after_set_linux_kernel_attrs(context):
    context.mqs['Linux kernel attrs'].put(context.linux_kernel['attrs'])


def after_build_linux_kernel(context):
    if 'modules' in context.conf['Linux kernel'] and 'all' in context.conf['Linux kernel']['modules'] \
            and context.conf['Linux kernel'].get('build kernel', False):
        if 'modules dep file' not in context.conf['Linux kernel']:
            context.mqs['Linux kernel module deps'].put(context.linux_kernel['module deps'])
        if 'modules dep function file' not in context.conf['Linux kernel']:
            context.mqs['Linux kernel module deps function'].put(context.linux_kernel['module deps function'])
        if 'modules size file' not in context.conf['Linux kernel']:
            context.mqs['Linux kernel module sizes'].put(context.linux_kernel['module sizes'])


def after_process_all_linux_kernel_raw_build_cmds(context):
    context.logger.info('Terminate Linux kernel build command descriptions message queue')
    context.mqs['Linux kernel build cmd descs'].put(None)


def after_process_linux_kernel_raw_build_cmd(context):
    if context.linux_kernel['build cmd']['type'] == 'CC':
        # Filter out CC commands if input file is absent or '/dev/null' or STDIN ('-') or 'init/version.c' or output
        # file is absent. They won't be used when building verification object descriptions.
        if not context.linux_kernel['build cmd']['in files'] \
           or context.linux_kernel['build cmd']['in files'][0] == '/dev/null' \
           or context.linux_kernel['build cmd']['in files'][0] == '-' \
           or context.linux_kernel['build cmd']['in files'][0] == 'init/version.c' \
           or not context.linux_kernel['build cmd']['out file']:
            return

        context.linux_kernel['build cmd']['full desc file'] = '{0}.json'.format(
            context.linux_kernel['build cmd']['out file'])
        linux_kernel_build_cmd_full_desc_file = os.path.relpath(os.path.join(context.linux_kernel['work src tree'],
                                                                             '{0}.json'.format(
                                                                                 context.linux_kernel['build cmd'][
                                                                                     'out file'])))
        if os.path.isfile(linux_kernel_build_cmd_full_desc_file):
            # Sometimes when building several individual modules the same modules are built several times including
            # building of corresponding mod.o files. Do not fail in this case.
            if not context.linux_kernel['build cmd']['out file'].endswith('mod.o'):
                raise FileExistsError('Linux kernel CC full description file "{0}" already exists'.format(
                    linux_kernel_build_cmd_full_desc_file))
        else:
            context.logger.debug(
                'Dump Linux kernel CC full description to file "{0}"'.format(linux_kernel_build_cmd_full_desc_file))
            with open(linux_kernel_build_cmd_full_desc_file, 'w', encoding='ascii') as fp:
                json.dump({attr: context.linux_kernel['build cmd'][attr] for attr in ('in files', 'out file', 'opts')}, fp,
                          sort_keys=True, indent=4)

    # We need to copy build command description since it may be accidently overwritten by LKBCE.
    linux_kernel_build_cmd_desc = {
        attr: copy.deepcopy(context.linux_kernel['build cmd'][attr]) for attr in
        ('type', 'in files', 'out file', 'full desc file') if attr in context.linux_kernel['build cmd']
        }
    linux_kernel_build_cmd_desc.update({'linux kernel work src tree': context.linux_kernel['work src tree']})
    context.mqs['Linux kernel build cmd descs'].put(linux_kernel_build_cmd_desc)


class LKVOG(core.components.Component):
    def generate_linux_kernel_verification_objects(self):
        self.linux_kernel_verification_objs_gen = {}
        self.common_prj_attrs = {}
        self.linux_kernel_build_cmd_out_file_desc = multiprocessing.Manager().dict()
        self.linux_kernel_module_names_mq = multiprocessing.Queue()
        self.linux_kernel_clusters_mq = multiprocessing.Queue()
        self.module = {}
        self.all_modules = {}
        self.verification_obj_desc = {}
        self.all_clusters = set()
        self.checked_modules = set()

        self.extract_linux_kernel_verification_objs_gen_attrs()
        self.set_common_prj_attrs()
        core.utils.report(self.logger,
                          'attrs',
                          {
                              'id': self.id,
                              'attrs': self.linux_kernel_verification_objs_gen['attrs']
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'])
        self.launch_subcomponents(('ALKBCDP', self.process_all_linux_kernel_build_cmd_descs),
                                  ('AVODG', self.generate_all_verification_obj_descs))

    main = generate_linux_kernel_verification_objects

    def set_common_prj_attrs(self):
        self.logger.info('Set common project atributes')
        self.common_prj_attrs = self.linux_kernel_verification_objs_gen['attrs']

    def extract_linux_kernel_verification_objs_gen_attrs(self):
        self.logger.info('Extract Linux kernel verification objects generation strategy atributes')

        self.linux_kernel_verification_objs_gen['attrs'] = self.mqs['Linux kernel attrs'].get()
        self.mqs['Linux kernel attrs'].close()
        self.linux_kernel_verification_objs_gen['attrs'].extend(
            [{'LKVOG strategy': [{'name': self.conf['LKVOG strategy']['name']}]}])

    def get_modules_from_deps(self, subsystem, deps):
        # Extract all modules in subsystem from dependencies
        ret = set()
        for module in deps:
            if module.startswith(subsystem):
                ret.add(module)
            for dep in deps[module]:
                if dep.startswith(subsystem):
                    ret.add(dep)
        return ret

    def is_part_of_subsystem(self, module, modules):
        # Returns true if module is a part of subsystem that contains in modules
        for module2 in modules:
            if module.id.startswith(module2):
                return True
        else:
            return False

    def generate_all_verification_obj_descs(self):
        strategy_name = self.conf['LKVOG strategy']['name']

        module_deps = {}
        module_deps_function = {}
        module_sizes = {}

        if ('all' in self.conf['Linux kernel']['modules'] and
                self.conf['Linux kernel'].get('build kernel', False)):

                module_deps = self.mqs['Linux kernel module deps'].get()
                module_deps_function = self.mqs['Linux kernel module deps function'].get()
                module_sizes = self.mqs['Linux kernel module sizes'].get()
        else:
            if strategy_name != 'separate modules' and 'modules dep file' not in self.conf['Linux kernel']:
                raise RuntimeError("Strategy {} will not receive dependencied"
                                   .format(self.conf['LKVOG strategy']['name']))
            elif 'modules dep file' in self.conf['Linux kernel']:
                module_deps = self.mqs['Linux kernel module deps'].get()
            if 'modules dep function file' in self.conf['Linux kernel']:
                module_deps_function = self.mqs['Linux kernel module deps function'].get()
            if 'modules size file' in self.conf['Linux kernel']:
                module_sizes = self.mqs['Linux kernel module sizes'].get()
        self.mqs['Linux kernel module deps'].close()
        self.mqs['Linux kernel module deps function'].close()
        self.mqs['Linux kernel module sizes'].close()

        if strategy_name != 'separate modules':
            # Use strategy
            strategy = None

            if strategy_name == 'closure':
                strategy = closure.Closure(self.logger, module_deps, self.conf['LKVOG strategy'])

            elif strategy_name == 'scotch':
                scotch_dir_path = os.path.join(self.conf['main working directory'], 'scotch')
                if not os.path.isdir(scotch_dir_path):
                    os.mkdir(scotch_dir_path)
                else:
                    # Clear scotch directory
                    file_list = os.listdir(scotch_dir_path)
                    for file_name in file_list:
                        os.remove(os.path.join(scotch_dir_path, file_name))

                strategy = scotch.Scotch(self.logger, module_deps,
                                         os.path.join(scotch_dir_path, 'graph_file'),
                                         os.path.join(scotch_dir_path, 'scotch_log'),
                                         os.path.join(scotch_dir_path, 'scotch_out'), params=self.conf['LKVOG strategy'])
            elif strategy_name == 'strategy1':
                strategy = strategy1.Strategy1(self.logger, module_deps, params=self.conf['LKVOG strategy'],
                                               export_func=module_deps_function, module_sizes=module_sizes)
            elif strategy_name == 'separate modules':
                pass

            else:
                raise NotImplementedError("Strategy {} not implemented".format(strategy_name))

            build_modules = set()
            self.logger.debug("Initial build modules: {}".format(self.conf['Linux kernel']['modules']))
            for kernel_module in self.conf['Linux kernel']['modules']:
                if re.search(r'\.ko$', kernel_module) or kernel_module == 'all':
                    # Invidiual module just use strategy
                    self.logger.debug('Use strategy for {} module'.format(kernel_module))
                    clusters = strategy.divide(kernel_module)
                    self.all_clusters.update(clusters)
                    for cluster in clusters:
                        for cluster_module in cluster.modules:
                            build_modules.add(cluster_module.id)
                            self.checked_modules.add(cluster_module.id)
                else:
                    # Module is subsystem
                    build_modules.add(kernel_module)
                    subsystem_modules = self.get_modules_from_deps(kernel_module, module_deps)
                    for module2 in subsystem_modules:
                        clusters = strategy.divide(module2)
                        self.all_clusters.update(clusters)
                        for cluster in clusters:
                            # Need update build_modules and checked_modules
                            for module3 in cluster.modules:
                                self.checked_modules.add(module3.id)
                                if not self.is_part_of_subsystem(module3, build_modules):
                                    build_modules.add(module3.id)

            self.logger.debug('After dividing build modules: {}'.format(build_modules))

            if 'all' not in self.conf['Linux kernel']['modules'] \
                    or not self.conf['Linux kernel'].get('build kernel', False):
                self.mqs['Linux kernel modules'].put(build_modules)
                self.mqs['Additional modules'].put(build_modules)
        else:
            self.mqs['Linux kernel module deps'].close()
            self.mqs['Linux kernel module deps function'].close()
        self.logger.info('Generate all Linux kernel verification object decriptions')

        cc_ready = set()
        while True:
            self.module['name'] = self.linux_kernel_module_names_mq.get()
            self.logger.debug('Recieved module {}'.format(self.module['name']))
            cc_ready.add(self.module['name'])

            if self.module['name'] is None:
                self.logger.debug('Linux kernel module names was terminated')
                self.linux_kernel_module_names_mq.close()
                break

            if not self.module['name'] in self.all_modules:
                self.all_modules[self.module['name']] = True
                module_clusters = []
                if self.module['name'] in self.checked_modules:
                    # Find clusters
                    for cluster in self.all_clusters:
                        if self.module['name'] in [module.id for module in cluster.modules]:
                            for cluster_module in cluster.modules:
                                if cluster_module.id not in cc_ready:
                                    break
                            else:
                                module_clusters.append(cluster)
                    # Remove appended clusters
                    self.all_clusters = set(filter(lambda cluster: cluster not in module_clusters,
                        self.all_clusters))
                else:
                    self.checked_modules.add(module.Module(self.module['name']))
                    module_clusters.append(module.Graph([module.Module(self.module['name'])]))

                for cluster in module_clusters:
                    self.cluster = cluster
                    # TODO: specification requires to do this in parallel...
                    self.generate_verification_obj_desc()

    def generate_verification_obj_desc(self):
        self.logger.info(
            'Generate Linux kernel verification object description for module "{0}"'.format(self.module['name']))

        strategy = self.conf['LKVOG strategy']['name']

        self.verification_obj_desc['id'] = self.cluster.root.id + str(hash(self.cluster))
        self.logger.debug('Linux kernel verification object id is "{0}"'.format(self.verification_obj_desc['id']))

        self.module['cc full desc files'] = self.__find_cc_full_desc_files(self.module['name'])

        self.verification_obj_desc['grps'] = []
        self.verification_obj_desc['deps'] = {}
        for module in self.cluster.modules:
            self.verification_obj_desc['grps'].append({'id': module.id,
                                                       'cc full desc files': self.__find_cc_full_desc_files(module.id)})
            self.verification_obj_desc['deps'][module.id] = \
                [predecessor.id for predecessor in module.predecessors if predecessor in self.cluster.modules]

        self.logger.debug(
            'Linux kernel verification object groups are "{0}"'.format(self.verification_obj_desc['grps']))

        self.logger.debug(
            'Linux kernel verification object dependencies are "{0}"'.format(self.verification_obj_desc['deps']))

        if self.conf['keep intermediate files']:
            verification_obj_desc_file = os.path.join(
                        self.linux_kernel_build_cmd_out_file_desc[self.module['name']]['linux kernel work src tree'],
                        '{0}.json'.format(self.verification_obj_desc['id']))
            if os.path.isfile(verification_obj_desc_file):
                raise FileExistsError(
                    'Linux kernel verification object description file "{0}" already exists'.format(
                        verification_obj_desc_file))
            self.logger.debug(
                'Dump Linux kernel verification object description for module "{0}" to file "{1}"'.format(
                    self.module['name'], verification_obj_desc_file))
            with open(verification_obj_desc_file, 'w', encoding='ascii') as fp:
                    json.dump(self.verification_obj_desc, fp, sort_keys=True, indent=4)

        else:
            raise NotImplementedError(
                'Linux kernel verification object generation strategy "{0}" is not supported'.format(strategy))

    def process_all_linux_kernel_build_cmd_descs(self):
        self.logger.info('Process all Linux kernel build command decriptions')

        if ('all' not in self.conf['Linux kernel']['modules']
                or not self.conf['Linux kernel'].get('build kernel', False)) \
                and 'modules dep file' in self.conf['Linux kernel'] \
                and self.conf['LKVOG strategy']['name'] != 'separate_modules':
            self.conf['Linux kernel']['modules'] = self.mqs['Additional modules'].get()
        self.mqs['Additional modules'].close()


        while True:
            desc = self.mqs['Linux kernel build cmd descs'].get()

            if desc is None:
                self.logger.debug('Linux kernel build command descriptions message queue was terminated')
                self.mqs['Linux kernel build cmd descs'].close()
                self.logger.info('Terminate Linux kernel module names message queue')
                self.linux_kernel_module_names_mq.put(None)
                break

            self.process_linux_kernel_build_cmd_desc(desc)

    def process_linux_kernel_build_cmd_desc(self, desc):
        self.logger.info(
            'Process description of Linux kernel build command "{0}" {1}'.format(desc['type'],
                                                                                 '(output file is {0})'.format(
                                                                                     '"{0}"'.format(desc['out file'])
                                                                                     if desc['out file']
                                                                                     else 'not specified')))

        # Build map from Linux kernel build command output files to correpsonding descriptions. This map will be used
        # later when finding all CC full description files.
        if desc['out file'] and desc['out file'] != '/dev/null':
            # For instance, this is true for drivers/net/wireless/libertas/libertas.ko in Linux stable a533423.
            if desc['out file'] in self.linux_kernel_build_cmd_out_file_desc:
                self.logger.warning(
                    'During Linux kernel build output file "{0}" was overwritten'.format(desc['out file']))
                # Propose new artificial name to avoid infinite recursion later.
                out_file_root, out_file_ext = os.path.splitext(desc['out file'])
                desc['out file'] = '{0}{1}{2}'.format(out_file_root,
                                                      len(self.linux_kernel_build_cmd_out_file_desc[desc['out file']]),
                                                      out_file_ext)

            # Do not include assembler files into verification objects since we have no means to instrument and to
            # analyse them.
            self.linux_kernel_build_cmd_out_file_desc[desc['out file']] = None if desc['type'] == 'CC' and re.search(
                r'\.S$', desc['in files'][0], re.IGNORECASE) else desc

        if desc['type'] == 'LD' and re.search(r'\.ko$', desc['out file']):
            match = False
            if 'modules' in self.conf['Linux kernel']:
                if 'all' in self.conf['Linux kernel']['modules']:
                    match = True
                else:
                    for modules in self.conf['Linux kernel']['modules']:
                        if re.search(r'^{0}|{1}'.format(modules, os.path.join('ext-modules', modules)),
                                     desc['out file']):
                            match = True
                            break
            else:
                self.logger.warning(
                    'Module {0} will not be verified since modules to be verified are not specified'.format(
                        desc['out file']))

            if match:
                self.linux_kernel_module_names_mq.put(desc['out file'])

    def __find_cc_full_desc_files(self, out_file):
        self.logger.debug('Find CC full description files for "{0}"'.format(out_file))

        cc_full_desc_files = []

        out_file_desc = self.linux_kernel_build_cmd_out_file_desc[out_file]

        if out_file_desc:
            if out_file_desc['type'] == 'CC':
                cc_full_desc_files.append(out_file_desc['full desc file'])
            else:
                for in_file in out_file_desc['in files']:
                    if not re.search(r'\.mod\.o$', in_file):
                        cc_full_desc_files.extend(self.__find_cc_full_desc_files(in_file))

        return cc_full_desc_files
