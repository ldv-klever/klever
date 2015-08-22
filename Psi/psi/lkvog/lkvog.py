#!/usr/bin/python3

import multiprocessing

import psi.components
import psi.utils

name = 'LKVOG'


def before_launch_all_components(context):
    context['MQs']['Linux kernel attrs'] = multiprocessing.Queue()


def after_extract_linux_kernel_attrs(context):
    context.mqs['Linux kernel attrs'].put(context.linux_kernel['attrs'])


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

    def extract_linux_kernel_verification_objs_gen_attrs(self):
        self.logger.info('Extract Linux kernel verification objects generation strategy atributes')

        self.linux_kernel_verification_objs_gen['attrs'] = self.mqs['Linux kernel attrs'].get()
        self.mqs['Linux kernel attrs'].close()
        self.linux_kernel_verification_objs_gen['attrs'].extend(
            [{'Linux kernel verification objs gen strategy': [
                {'name': self.conf['Linux kernel verification objs gen strategy']['name']}]}])
