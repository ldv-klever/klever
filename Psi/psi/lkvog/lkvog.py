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
        self.linux_kernel = {}
        self.linux_kernel['attrs'] = self.mqs['Linux kernel attrs'].get()

        # TODO: delete following stub code after all.
        psi.utils.report(self.logger,
                         'attrs',
                         {'id': self.name,
                          'attrs': [
                              {"Linux kernel": [
                                  {"version": "3.5.0"},
                                  {"arch": "x86_64"},
                                  {"conf shortcut": "allmodconfig"}
                              ]},
                              {'Linux kernel verification objs gen strategy': [
                                  {'name': 'separate module'},
                                  {'opts': [{'name1': 'value1'}, {'name2': 'value2'}]}
                              ]}
                          ]},
                         self.mqs['report files'],
                         self.conf['root id'])
