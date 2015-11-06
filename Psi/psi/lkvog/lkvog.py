#!/usr/bin/python3

import copy
import json
import multiprocessing
import os
import re

import psi.components
import psi.utils


def before_launch_all_components(context):
    context.mqs['Linux kernel attrs'] = multiprocessing.Queue()
    context.mqs['Linux kernel build cmd descs'] = multiprocessing.Queue()


def after_extract_linux_kernel_attrs(context):
    context.mqs['Linux kernel attrs'].put(context.linux_kernel['attrs'])


def after_process_linux_kernel_raw_build_cmd(context):
    # Do not dump full description if input file is absent or '/dev/null' or STDIN ('-') or output file is absent.
    # Corresponding CC commands will not be traversed when building verification object descriptions.
    if context.linux_kernel['build cmd']['type'] == 'CC' \
            and context.linux_kernel['build cmd']['in files'] \
            and context.linux_kernel['build cmd']['in files'][0] != '-' \
            and not re.search(r'^/', context.linux_kernel['build cmd']['in files'][0]) \
            and context.linux_kernel['build cmd']['out file']:
        context.linux_kernel['build cmd']['full desc file'] = '{0}.json'.format(
            context.linux_kernel['build cmd']['out file'])

        context.logger.debug(
            'Dump Linux kernel CC full description to file "{0}"'.format(
                context.linux_kernel['build cmd']['full desc file']))
        with open(
                os.path.join(context.conf['root id'], 'linux', context.linux_kernel['build cmd']['full desc file']),
                'w') as fp:
            json.dump({attr: context.linux_kernel['build cmd'][attr] for attr in ('in files', 'out file', 'opts')}, fp,
                      sort_keys=True, indent=4)

    # We need to copy build command description since it may be accidently overwritten by LKBCE.
    context.mqs['Linux kernel build cmd descs'].put(
        {attr: copy.deepcopy(context.linux_kernel['build cmd'][attr]) for attr in
         ('type', 'in files', 'out file', 'full desc file') if attr in context.linux_kernel['build cmd']})


def after_process_all_linux_kernel_raw_build_cmds(context):
    context.logger.info('Terminate Linux kernel build command descriptions message queue')
    context.mqs['Linux kernel build cmd descs'].put(None)


class LKVOG(psi.components.Component):
    def generate_linux_kernel_verification_objects(self):
        self.linux_kernel_verification_objs_gen = {}
        self.common_prj_attrs = {}
        self.linux_kernel_build_cmd_out_file_desc = multiprocessing.Manager().dict()
        self.linux_kernel_module_names_mq = multiprocessing.Queue()
        self.module = {}
        self.all_modules = {}
        self.verification_obj_desc = {}

        self.extract_linux_kernel_verification_objs_gen_attrs()
        psi.utils.invoke_callbacks(self.extract_common_prj_attrs)
        psi.utils.report(self.logger,
                         'attrs',
                         {'id': self.name,
                          'attrs': self.linux_kernel_verification_objs_gen['attrs']},
                         self.mqs['report files'],
                         self.conf['root id'])
        self.launch_subcomponents((self.process_all_linux_kernel_build_cmd_descs,
                                   self.generate_all_verification_obj_descs))

    main = generate_linux_kernel_verification_objects

    def extract_common_prj_attrs(self):
        self.logger.info('Extract common project atributes')
        self.common_prj_attrs = self.linux_kernel_verification_objs_gen['attrs']

    def extract_linux_kernel_verification_objs_gen_attrs(self):
        self.logger.info('Extract Linux kernel verification objects generation strategy atributes')

        self.linux_kernel_verification_objs_gen['attrs'] = self.mqs['Linux kernel attrs'].get()
        self.mqs['Linux kernel attrs'].close()
        self.linux_kernel_verification_objs_gen['attrs'].extend(
            [{'LKVOG strategy': [{'name': self.conf['LKVOG strategy']['name']}]}])

    def generate_all_verification_obj_descs(self):
        self.logger.info('Generate all Linux kernel verification object decriptions')

        while True:
            self.module['name'] = self.linux_kernel_module_names_mq.get()

            if self.module['name'] is None:
                self.logger.debug('Linux kernel module names was terminated')
                self.linux_kernel_module_names_mq.close()
                break

            # Collect all modules for what we generate verification objects to avoid generation of the same verification
            # object.
            if not self.module['name'] in self.all_modules:
                self.all_modules[self.module['name']] = True
                # TODO: specification requires to do this in parallel...
                psi.utils.invoke_callbacks(self.generate_verification_obj_desc)

    def generate_verification_obj_desc(self):
        self.logger.info(
            'Generate Linux kernel verification object description for module "{0}"'.format(self.module['name']))

        strategy = self.conf['LKVOG strategy']['name']

        if strategy == 'separate modules':
            self.verification_obj_desc['id'] = 'linux/{0}'.format(self.module['name'])
            self.logger.debug('Linux kernel verification object id is "{0}"'.format(self.verification_obj_desc['id']))

            self.module['cc full desc files'] = self.__find_cc_full_desc_files(self.module['name'])
            self.verification_obj_desc['grps'] = [
                {'id': self.module['name'], 'cc full desc files': self.module['cc full desc files']}]
            self.logger.debug(
                'Linux kernel verification object groups are "{0}"'.format(self.verification_obj_desc['grps']))

            self.verification_obj_desc['deps'] = {self.module['name']: []}
            self.logger.debug(
                'Linux kernel verification object dependencies are "{0}"'.format(self.verification_obj_desc['deps']))

            if self.conf['debug']:
                verification_obj_desc_file = '{0}.json'.format(self.verification_obj_desc['id'])
                self.logger.debug(
                    'Dump Linux kernel verification object description for module "{0}" to file "{1}"'.format(
                        self.module['name'], verification_obj_desc_file))
                with open(os.path.join(self.conf['root id'], verification_obj_desc_file), 'w') as fp:
                    json.dump(self.verification_obj_desc, fp, sort_keys=True, indent=4)

        elif strategy == "multimodule":
            #TODO write real multimodule, not separate module
            self.verification_obj_desc['id'] = 'linux/{0}'.format(self.module['name'])
            self.logger.debug('Linux kernel verification object id is "{0}"'.format(self.verification_obj_desc['id']))

            self.module['cc full desc files'] = self.__find_cc_full_desc_files(self.module['name'])
            self.verification_obj_desc['grps'] = [
                {'id': self.module['name'], 'cc full desc files': self.module['cc full desc files']}]
            self.logger.debug(
                'Linux kernel verification object groups are "{0}"'.format(self.verification_obj_desc['grps']))

            self.verification_obj_desc['deps'] = {self.module['name']: ["module1", "module2"]}
            self.logger.debug(
                'Linux kernel verification object dependencies are "{0}"'.format(self.verification_obj_desc['deps']))

            if self.conf['debug']:
                verification_obj_desc_file = '{0}.json'.format(self.verification_obj_desc['id'])
                self.logger.debug(
                    'Dump Linux kernel verification object description for module "{0}" to file "{1}"'.format(
                        self.module['name'], verification_obj_desc_file))
                with open(os.path.join(self.conf['root id'], verification_obj_desc_file), 'w') as fp:
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

        self.linux_kernel_build_cmd_out_file_desc[desc['out file']] = desc

        if desc['type'] == 'LD' and re.search(r'\.ko$', desc['out file']):
            match = False
            if 'whole build' in self.conf['Linux kernel']:
                match = True
            elif 'modules' in self.conf['Linux kernel']:
                for modules in self.conf['Linux kernel']['modules']:
                    if re.search(r'^{0}'.format(modules), desc['out file']):
                        match = True
                        break
            if match:
                self.linux_kernel_module_names_mq.put(desc['out file'])

    def __find_cc_full_desc_files(self, out_file):
        self.logger.debug('Find CC full description files for "{0}"'.format(out_file))

        cc_full_desc_files = []

        out_file_desc = self.linux_kernel_build_cmd_out_file_desc[out_file]

        if out_file_desc['type'] == 'CC':
            cc_full_desc_files.append(out_file_desc['full desc file'])
        else:
            for in_file in out_file_desc['in files']:
                if not re.search(r'\.mod\.o$', in_file):
                    cc_full_desc_files.extend(self.__find_cc_full_desc_files(in_file))

        return cc_full_desc_files
