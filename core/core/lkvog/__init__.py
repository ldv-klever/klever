#!/usr/bin/python3

import json
import multiprocessing
import os
import re

from core.lkvog.strategies import scotch
from core.lkvog.strategies import closure
from core.lkvog.strategies import advanced
from core.lkvog.strategies import strategies_list
from core.lkvog.strategies import module
import core.components
import core.utils


def before_launch_sub_job_components(context):
    context.mqs['Linux kernel attrs'] = multiprocessing.Queue()
    context.mqs['Linux kernel build cmd descs'] = multiprocessing.Queue()
    context.mqs['Linux kernel module dependencies'] = multiprocessing.Queue()
    context.mqs['Linux kernel module sizes'] = multiprocessing.Queue()
    context.mqs['Linux kernel modules'] = multiprocessing.Queue()
    context.mqs['Linux kernel additional modules'] = multiprocessing.Queue()


def after_set_linux_kernel_attrs(context):
    context.mqs['Linux kernel attrs'].put(context.linux_kernel['attrs'])


def after_process_all_linux_kernel_raw_build_cmds(context):
    context.logger.info('Terminate Linux kernel build command descriptions message queue')
    context.mqs['Linux kernel build cmd descs'].put(None)



def after_get_linux_kernel_build_cmd_desc(context):
    with open(context.linux_kernel['build cmd desc file'], encoding='ascii') as fp:
        context.mqs['Linux kernel build cmd descs'].put(json.load(fp))


def after_get_all_linux_kernel_build_cmd_descs(context):
    context.logger.info('Terminate Linux kernel build command descriptions message queue')
    context.mqs['Linux kernel build cmd descs'].put(None)


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

        module_deps_function = {}
        module_sizes = {}
        if 'module dependencies file' in self.conf['Linux kernel']:
            module_deps_function = self.mqs['Linux kernel module dependencies'].get()
        if 'module sizes file' in self.conf['Linux kernel']:
            module_sizes = self.mqs['Linux kernel module sizes'].get()

        if 'modules dependencies' not in self.conf['Linux kernel']:
            if strategy_name == 'separate modules':
                self.mqs['Linux kernel modules'].put({'build kernel': False,
                                                      'modules': self.conf['Linux kernel']['modules']})


            else:
                if 'external modules' not in self.conf['Linux kernel']:
                    self.mqs['Linux kernel modules'].put({'build kernel': True})


                else:
                    self.mqs['Linux kernel modules'].put({'build kernel': True,
                                                          'modules': self.conf['Linux kernel']['modules']})

                module_deps_function = self.mqs['Linux kernel module deps function'].get()
                module_sizes = self.mqs['Linux kernel module sizes'].get()

        self.mqs['Linux kernel module dependencies'].close()
        self.mqs['Linux kernel module sizes'].close()

        if strategy_name not in strategies_list:
            raise NotImplementedError("Strategy {} not implemented".format(strategy_name))

        strategy_params = {'module_deps_function': module_deps_function,
                           'work dir': os.path.abspath(os.path.join(self.conf['main working directory'],
                                                                    strategy_name)),
                           'module_sizes': module_sizes}
        strategy = strategies_list[strategy_name](self.logger, strategy_params, self.conf['LKVOG strategy'])

        build_modules = set()
        self.logger.debug("Initial build modules: {}".format(self.conf['Linux kernel']['modules']))
        for kernel_module in self.conf['Linux kernel']['modules']:
            kernel_module = kernel_module if 'external modules' not in self.conf['Linux kernel'] else 'ext-modules/' + kernel_module
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
                subsystem_modules = self.get_modules_from_deps(kernel_module, module_deps_function)
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

        if 'module dependencies file' in self.conf['Linux kernel'] and strategy_name != 'separate modules':
            self.mqs['Linux kernel modules'].put({'build kernel': False, 'modules': list(build_modules)})
        else:
            self.mqs['Linux kernel module dependencies'].close()
        self.logger.info('Generate all Linux kernel verification object decriptions')

        cc_ready = set()
        while True:
            self.module['name'] = self.linux_kernel_module_names_mq.get()

            if self.module['name'] is None:
                self.logger.debug('Linux kernel module names was terminated')
                self.linux_kernel_module_names_mq.close()
                break

            match = False
            if 'modules' in self.conf['Linux kernel']:
                if 'all' in self.conf['Linux kernel']['modules']:
                    match = True
                else:
                    for modules in build_modules:
                        if re.search(r'^{0}|{1}'.format(modules, os.path.join('ext-modules', modules)),
                                     self.module['name']):
                            match = True
                            break
            else:
                self.logger.warning(
                    'Module {0} will not be verified since modules to be verified are not specified'.format(
                        self.module['name']))
            if not match:
                continue
            self.logger.debug('Recieved module {}'.format(self.module['name']))
            cc_ready.add(self.module['name'])

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

        self.verification_obj_desc['id'] = self.cluster.root.id

        if len(self.cluster.modules) > 1:
            self.verification_obj_desc['id'] += self.cluster.md5_hash()

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
            verification_obj_desc_file = '{0}.json'.format(self.verification_obj_desc['id'])
            if os.path.isfile(verification_obj_desc_file):
                raise FileExistsError(
                    'Linux kernel verification object description file "{0}" already exists'.format(
                        verification_obj_desc_file))
            self.logger.debug(
                'Dump Linux kernel verification object description for module "{0}" to file "{1}"'.format(
                    self.module['name'], verification_obj_desc_file))
            os.makedirs(os.path.dirname(verification_obj_desc_file), exist_ok=True)
            with open(verification_obj_desc_file, 'w', encoding='ascii') as fp:
                    json.dump(self.verification_obj_desc, fp, sort_keys=True, indent=4)

        else:
            raise NotImplementedError(
                'Linux kernel verification object generation strategy "{0}" is not supported'.format(strategy))

    def process_all_linux_kernel_build_cmd_descs(self):
        self.logger.info('Process all Linux kernel build command decriptions')

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
