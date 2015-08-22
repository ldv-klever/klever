#!/usr/bin/python3

import os
import random

import psi.components
import psi.utils

name = 'VTSC'


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

        # Verification tasks are solved on another computer.
        verification_comp = [
            {'node name': 'chehab.intra.ispras.ru'},
            {'CPU model': 'Intel(R) Core(TM) i5-2500 CPU @ 3.30GHz'}, {'CPUs num': '4'},
            {'mem size': '8404367360'}, {'Linux kernel version': '3.8.0-44-generic'},
            {'arch': 'x86_64'}
        ]

        # Solve verification tasks produced by "WRAPPER".
        for i, verification_obj in enumerate(('drivers/usb/core/usbcore.ko', 'drivers/usb/usb-commmon.ko')):
            for j, rule_spec in enumerate(('mutex', 'spin lock')):
                # "WRAPPER11" doesn't produce any verification task since it wasn't started.
                if i == 1 and j == 1:
                    continue

                # We have two different bug kinds for mutex and "WRAPPER*0" produces one verification task per each bug
                # kind first. Then "WRAPPER10" produces one more verification task for the second bug kind.
                if j == 0:
                    for k, bug_kind in enumerate(
                            ('linux:one thread:double acquisition', 'linux:one thread:unreleased at exit')):
                        id = '{0}/{1}/{2}/verifier'.format(verification_obj, rule_spec, bug_kind)
                        verifier_work_dir = 'VERIFIER{0}{1}{2}'.format(i, j, k)

                        os.makedirs(verifier_work_dir)
                        os.chdir(verifier_work_dir)

                        psi.utils.report(self.logger,
                                         'verification',
                                         {'id': id,
                                          'parent id': 'VTSC',
                                          'attrs': [{'verification obj': verification_obj}, {'rule spec': rule_spec},
                                                    {'bug kind': bug_kind}],
                                          'name': 'BLAST 2.7.2' if i == 0 else 'CPAchecker r12345',
                                          'comp': verification_comp,
                                          'resources': {'wall time': random.randint(0, 10000),
                                                        'CPU time': random.randint(0, 10000),
                                                        'max mem size': random.randint(0, 1000000000)},
                                          'log': '',
                                          'data': ''},
                                         self.mqs['report files'],
                                         self.conf['root id'])

                        if i == 1 and k == 1:
                            psi.utils.report(self.logger,
                                             'verification',
                                             {'id': id + '-retry',
                                              'parent id': 'VTSC',
                                              'attrs': [{'verification obj': verification_obj},
                                                        {'rule spec': rule_spec},
                                                        {'bug kind': bug_kind}],
                                              'name': 'CPAchecker r12345',
                                              'comp': verification_comp,
                                              'resources': {'wall time': random.randint(0, 10000),
                                                            'CPU time': random.randint(0, 10000),
                                                            'max mem size': random.randint(0, 1000000000)},
                                              'log': '',
                                              'data': ''},
                                             self.mqs['report files'],
                                             self.conf['root id'],
                                             'retry')

                        os.chdir(os.pardir)

                # We have two different entry points for spin lock and "WRAPPER10" produces one verification task per
                # each entry point.
                if j == 1:
                    for k, entry_point in enumerate(
                            ('ldv_entry_point_1', 'ldv_entry_point_2')):
                        id = '{0}/{1}/{2}/verifier'.format(verification_obj, rule_spec, entry_point)
                        verifier_work_dir = 'VERIFIER{0}{1}{2}'.format(i, j, k)

                        os.makedirs(verifier_work_dir)
                        os.chdir(verifier_work_dir)

                        psi.utils.report(self.logger,
                                         'verification',
                                         {'id': id,
                                          'parent id': 'VTSC',
                                          'attrs': [{'verification obj': verification_obj}, {'rule spec': rule_spec},
                                                    {'bug kind': 'linux:one thread:double acquisition'}],
                                          'name': 'BLAST 2.7.2',
                                          'comp': verification_comp,
                                          'resources': {'wall time': random.randint(0, 10000),
                                                        'CPU time': random.randint(0, 10000),
                                                        'max mem size': random.randint(0, 1000000000)},
                                          'log': '',
                                          'data': ''},
                                         self.mqs['report files'],
                                         self.conf['root id'])

                        os.chdir(os.pardir)
