#!/usr/bin/python3

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


def before_launch_sub_job_components(context):
    context.mqs['Linux kernel attrs'] = multiprocessing.Queue()
    context.mqs['Linux kernel build cmd descs'] = multiprocessing.Queue()
    context.mqs['Linux kernel module dependencies'] = multiprocessing.Queue()
    context.mqs['Linux kernel module sizes'] = multiprocessing.Queue()
    context.mqs['Linux kernel modules'] = multiprocessing.Queue()
    context.mqs['Linux kernel additional modules'] = multiprocessing.Queue()


def after_set_linux_kernel_attrs(context):
    context.mqs['Linux kernel attrs'].put(context.linux_kernel['attrs'])


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
        self.all_modules = set()
        self.verification_obj_desc = {}
        self.all_clusters = set()
        self.checked_modules = set()
        self.loc = {}
        self.cc_full_descs_files = {}
        self.verification_obj_desc_file = None

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

    def send_loc_report(self):
        core.utils.report(self.logger,
                          'data',
                          {
                              'id': self.id,
                              'data': json.dumps(self.loc)
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'])

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
        strategy_name = self.conf['LKVOG strategy']['name']

        if 'all' in self.conf['Linux kernel']['modules'] and not len(self.conf['Linux kernel']['modules']) == 1:
            raise ValueError('You can not specify "all" modules together with some other modules')

        module_deps_function = {}
        module_sizes = {}
        if 'module dependencies file' in self.conf['Linux kernel']:
            module_deps_function = self.mqs['Linux kernel module dependencies'].get()
        if 'module sizes file' in self.conf['Linux kernel']:
            module_sizes = self.mqs['Linux kernel module sizes'].get()

        if 'module dependencies file' not in self.conf['Linux kernel']:
            if strategy_name == 'separate modules':
                self.mqs['Linux kernel modules'].put({'build kernel': False,
                                                      'modules': self.conf['Linux kernel']['modules']})
            elif strategy_name != 'manual':
                if 'external modules' not in self.conf['Linux kernel']:
                    self.mqs['Linux kernel modules'].put({'build kernel': True})

                else:
                    self.mqs['Linux kernel modules'].put({'build kernel': True,
                                                          'modules': self.conf['Linux kernel']['modules']})

                module_deps_function = self.mqs['Linux kernel module dependencies'].get()
                module_sizes = self.mqs['Linux kernel module sizes'].get()

        self.mqs['Linux kernel module dependencies'].close()
        self.mqs['Linux kernel module sizes'].close()

        if strategy_name not in strategies_list:
            raise NotImplementedError("Strategy {0} not implemented".format(strategy_name))

        strategy_params = {'module_deps_function': module_deps_function,
                           'work dir': os.path.abspath(os.path.join(self.conf['main working directory'],
                                                                    strategy_name)),
                           'module_sizes': module_sizes}
        strategy = strategies_list[strategy_name](self.logger, strategy_params, self.conf['LKVOG strategy'])

        build_modules = set()
        self.logger.debug("Initial list of modules to be built: {0}".format(self.conf['Linux kernel']['modules']))
        for kernel_module in self.conf['Linux kernel']['modules']:
            kernel_module = kernel_module if 'external modules' not in self.conf['Linux kernel'] \
                else 'ext-modules/' + kernel_module
            if re.search(r'\.k?o$', kernel_module) or kernel_module == 'all':
                # Invidiual module.
                self.logger.debug('Use strategy for {0} module'.format(kernel_module))
                clusters = strategy.divide(kernel_module)
                self.all_clusters.update(clusters)
                for cluster in clusters:
                    if self.conf['LKVOG strategy'].get('draw graphs', False):
                        cluster.draw(".")
                    for cluster_module in cluster.modules:
                        build_modules.add(cluster_module.id)
                        self.checked_modules.add(cluster_module.id)
            else:
                # Module is subsystem.
                build_modules.add(kernel_module)
                subsystem_modules = self.get_modules_from_deps(kernel_module, module_deps_function)
                for module2 in subsystem_modules:
                    clusters = strategy.divide(module2)
                    self.all_clusters.update(clusters)
                    for cluster in clusters:
                        if self.conf['LKVOG strategy'].get('draw graphs', False):
                            cluster.draw(".")
                        for module3 in cluster.modules:
                            self.checked_modules.add(module3.id)
                            if not self.is_part_of_subsystem(module3, build_modules):
                                build_modules.add(module3.id)
        self.logger.debug('Final list of modules to be build: {0}'.format(build_modules))

        if 'module dependencies file' in self.conf['Linux kernel'] or strategy_name == 'manual':
            if 'all' in self.conf['Linux kernel']['modules']:
                build_modules = [module for module in build_modules if module.endswith('.o')]
                build_modules.append('all')
                self.mqs['Linux kernel modules'].put({'build kernel': False,
                                                      'modules': build_modules})
            else:
                self.mqs['Linux kernel modules'].put({'build kernel': False, 'modules':
                    [module if not module.startswith('ext-modules/') else module[12:] for module in build_modules]})
        else:
            self.mqs['Linux kernel module dependencies'].close()
        self.logger.info('Generate all Linux kernel verification object decriptions')

        self.all_clusters = set([cluster for cluster in self.all_clusters if 'all' not in [module.id for module in cluster.modules]])
        cc_ready = set()
        while True:
            self.module['name'] = self.linux_kernel_module_names_mq.get()

            if self.module['name'] is None:
                self.logger.debug('Linux kernel module names message queue was terminated')
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
            self.logger.debug('Recieved module {0}'.format(self.module['name']))
            cc_ready.add(self.module['name'])

            if not self.module['name'] in self.all_modules:
                module_clusters = []
                if self.module['name'] in self.checked_modules:
                    self.all_modules.add(self.module['name'])
                    # Find clusters
                    for cluster in self.all_clusters:
                        if self.module['name'] in [module.id for module in cluster.modules]:
                            for cluster_module in cluster.modules:
                                if cluster_module.id not in cc_ready:
                                    break
                            else:
                                module_clusters.append(cluster)
                    # Remove clusters that will be checked.
                    self.all_clusters = set(filter(lambda cluster: cluster not in module_clusters,
                                                   self.all_clusters))
                else:
                    if self.module['name'].endswith('.o'):
                        self.logger.debug('Module {0} skipped'.format(self.module['name']))
                        continue
                    self.all_modules.add(self.module['name'])
                    self.checked_modules.add(strategy_utils.Module(self.module['name']))
                    module_clusters.append(strategy_utils.Graph([strategy_utils.Module(self.module['name'])]))

                for cluster in module_clusters:
                    self.cluster = cluster
                    # TODO: specification requires to do this in parallel...
                    self.generate_verification_obj_desc()

        if self.all_clusters:
            not_builded = set()
            for cluster in self.all_clusters:
                not_builded |= set([module.id for module in cluster.modules]) - self.all_modules
            raise RuntimeError('Can not build following modules: {0}'.format(not_builded))

        self.send_loc_report()

    def generate_verification_obj_desc(self):
        self.logger.info(
            'Generate Linux kernel verification object description for module "{0}"'.format(self.module['name']))

        self.verification_obj_desc = {}

        self.verification_obj_desc['id'] = self.cluster.root.id

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
            self.module['name'], self.verification_obj_desc_file))
        os.makedirs(os.path.dirname(self.verification_obj_desc_file), exist_ok=True)
        with open(self.verification_obj_desc_file, 'w', encoding='ascii') as fp:
            json.dump(self.verification_obj_desc, fp, sort_keys=True, indent=4)

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

        # Build map from Linux kernel build command output files to correpsonding descriptions.
        # If more than one build command has the same output file their descriptions are added as list in chronological
        # order (more early commands are processed more early and placed at the beginning of this list).
        if desc['out file'] in self.linux_kernel_build_cmd_out_file_desc:
            self.linux_kernel_build_cmd_out_file_desc[desc['out file']] = self.linux_kernel_build_cmd_out_file_desc[
                                                                              desc['out file']] + [desc]
        else:
            self.linux_kernel_build_cmd_out_file_desc[desc['out file']] = [desc]

        if desc['type'] == 'LD' and re.search(r'\.k?o$', desc['out file']):
            self.linux_kernel_module_names_mq.put(desc['out file'])

    def __find_cc_full_desc_files(self, out_file):
        self.logger.debug('Find CC full description files for "{0}"'.format(out_file))

        if out_file in self.cc_full_descs_files:
            self.logger.debug('CC full description files for "{0}" were already found'.format(out_file))
            return self.cc_full_descs_files[out_file]

        cc_full_desc_files = []
        # Get more older build commands more early if more than one build command has the same output file.
        out_file_desc = self.linux_kernel_build_cmd_out_file_desc[out_file][-1]

        # Remove got build command description from map. It is assumed that each build command output file can be used
        # as input file of another build command just once.
        self.linux_kernel_build_cmd_out_file_desc[out_file] = self.linux_kernel_build_cmd_out_file_desc[out_file][:-1]

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
            with open(os.path.join(self.conf['main working directory'], cc_full_desc_file)) as fp:
                cc_full_desc = json.load(fp)
            for file in cc_full_desc['in files']:
                # Simple file's line counter
                with open(os.path.join(self.conf['main working directory'], cc_full_desc['cwd'], file),
                          encoding='utf8', errors='ignore') as fp:
                    loc += sum(1 for _ in fp)
        return loc
