#!/usr/bin/python3

import os

import psi.components
import psi.utils

name = 'LKVOG'


class PsiComponentCallbacks(psi.components.PsiComponentCallbacksBase):
    pass


class PsiComponent(psi.components.PsiComponentBase):
    def launch(self):
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
