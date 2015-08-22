#!/usr/bin/python3

import multiprocessing

import psi.components
import psi.utils

name = 'LKVOG'


def before_launch_all_components(context):
    context['MQs']['Linux kernel attrs'] = multiprocessing.Queue()
    context['MQs']['Linux kernel build cmd descs'] = multiprocessing.Queue()


def after_extract_linux_kernel_attrs(context):
    context.mqs['Linux kernel attrs'].put(context.linux_kernel['attrs'])


def after_process_linux_kernel_raw_build_cmd(context):
    context.mqs['Linux kernel build cmd descs'].put(
        {attr: context.linux_kernel['build cmd'][attr] for attr in ('type', 'in files', 'out file')})


def after_process_all_linux_kernel_raw_build_cmds(context):
    context.logger.info('Terminate Linux kernel build command descriptions message queue')
    context.mqs['Linux kernel build cmd descs'].put(None)


class PsiComponent(psi.components.PsiComponentBase):
    def launch(self):
        self.linux_kernel_verification_objs_gen = {}
        self.extract_linux_kernel_verification_objs_gen_attrs()
        psi.utils.report(self.logger,
                         'attrs',
                         {'id': self.name,
                          'attrs': self.linux_kernel_verification_objs_gen['attrs']},
                         self.mqs['report files'],
                         self.conf['root id'])
        self.proces_all_linux_kernel_build_cmd_descs()

    def extract_linux_kernel_verification_objs_gen_attrs(self):
        self.logger.info('Extract Linux kernel verification objects generation strategy atributes')

        self.linux_kernel_verification_objs_gen['attrs'] = self.mqs['Linux kernel attrs'].get()
        self.mqs['Linux kernel attrs'].close()
        self.linux_kernel_verification_objs_gen['attrs'].extend(
            [{'Linux kernel verification objs gen strategy': [
                {'name': self.conf['Linux kernel verification objs gen strategy']['name']}]}])

    def proces_all_linux_kernel_build_cmd_descs(self):
        while True:
            desc = self.mqs['Linux kernel build cmd descs'].get()

            if desc is None:
                self.logger.debug('Linux kernel build command descriptions message queue was terminated')
                self.mqs['Linux kernel build cmd descs'].close()
                break

            self.process_linux_kernel_build_cmd_desc(desc)

    def process_linux_kernel_build_cmd_desc(self, desc):
        self.logger.info(
            'Process description of Linux kernel build command "{0}"'.format(desc['type']))
