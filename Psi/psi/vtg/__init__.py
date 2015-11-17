#!/usr/bin/python3

import multiprocessing
import os
import random

import psi.components
import psi.utils


def before_launch_all_components(context):
    context.mqs['VTG common prj attrs'] = multiprocessing.Queue()


def after_extract_common_prj_attrs(context):
    context.mqs['VTG common prj attrs'].put(context.common_prj_attrs)


class VTG(psi.components.Component):
    def generate_verification_tasks(self):
        self.common_prj_attrs = {}
        self.extract_common_prj_attrs()
        psi.utils.report(self.logger,
                         'attrs',
                         {'id': self.name,
                          'attrs': self.common_prj_attrs},
                         self.mqs['report files'],
                         self.conf['root id'])
        return
        # TODO: delete following stub code after all.
        # Start and finish "WRAPPER". Upload safes, unsafes and unknowns in the middle.
        for i, verification_obj in enumerate(('drivers/usb/core/usbcore.ko', 'drivers/usb/usb-commmon.ko')):
            for j, rule_spec in enumerate(('linux:mutex', 'linux:spin lock')):
                # As expected "WRAPPER11" isn't started at all since DEG11 has failed.
                if i == 1 and j == 1:
                    continue

                id = '{0}/{1}/wrapper'.format(verification_obj, rule_spec)
                wrapper_work_dir = 'WRAPPER{0}{1}'.format(i, j)

                os.makedirs(wrapper_work_dir)
                os.chdir(wrapper_work_dir)

                psi.utils.report(self.logger,
                                 'start',
                                 {'id': id,
                                  'attrs': [{'verification object': verification_obj},
                                            {'rule specification': rule_spec}],
                                  'name': 'WRAPPER',
                                  'parent id': 'VTG'},
                                 self.mqs['report files'],
                                 self.conf['root id'])

                # We have two different bug kinds for mutex and "WRAPPER*0" produces one verification task per each bug
                # kind. First verification task leads to SAFE while the second one to UNSAFE for first module and to
                # SAFE and UNKNOWN for the second one. For latter UNKNOWN "WRAPPER10" produces one more verification
                # task: UNSAFE + UNSAFE + UNKNOWN.
                if j == 0:
                    for k, bug_kind in enumerate(
                            ('one thread:double acquisition', 'one thread:unreleased at exit')):
                        if k == 0:
                            psi.utils.report(self.logger,
                                             'safe',
                                             {'id': 'safe',
                                              'parent id': id,
                                              'attrs': [{'bug kind': bug_kind}],
                                              'proof': 'It does not matter...'},
                                             self.mqs['report files'],
                                             self.conf['root id'])
                        elif i == 0 and k == 1:
                            psi.utils.report(self.logger,
                                             'unsafe',
                                             {'id': 'unsafe',
                                              'parent id': id,
                                              'attrs': [{'bug kind': bug_kind}],
                                              'error trace': 'Error trace 1'},
                                             self.mqs['report files'],
                                             self.conf['root id'])
                        else:
                            psi.utils.report(self.logger,
                                             'unsafe',
                                             {'id': 'unsafe1',
                                              'parent id': id,
                                              'attrs': [{'bug kind': bug_kind}],
                                              'error trace': 'Error trace 2'},
                                             self.mqs['report files'],
                                             self.conf['root id'],
                                             '1')
                            psi.utils.report(self.logger,
                                             'unsafe',
                                             {'id': 'unsafe2',
                                              'parent id': id,
                                              'attrs': [{'bug kind': bug_kind}],
                                              'error trace': 'Error trace 2'},
                                             self.mqs['report files'],
                                             self.conf['root id'],
                                             '2')
                            psi.utils.report(self.logger,
                                             'unknown',
                                             {'id': 'unknown',
                                              'parent id': id,
                                              'attrs': [{'bug kind': bug_kind}],
                                              'problem desc': 'Fatal error!'},
                                             self.mqs['report files'],
                                             self.conf['root id'])

                # We have two different entry points for spin lock and "WRAPPER01" produces one verification task per
                # each entry point. First verification task leads to UNSAFE while the second one to UNKNOWN.
                if j == 1:
                    for k, entry_point in enumerate(
                            ('ldv_entry_point_1', 'ldv_entry_point_2')):
                        if k == 0:
                            psi.utils.report(self.logger,
                                             'unsafe',
                                             {'id': 'unsafe',
                                              'parent id': id,
                                              'attrs': [{'entry point': entry_point},
                                                        {'bug kind': 'one thread:double acquisition'}],
                                              'error trace': 'Error trace 3'},
                                             self.mqs['report files'],
                                             self.conf['root id'])
                        else:
                            psi.utils.report(self.logger,
                                             'unknown',
                                             {'id': 'unknown',
                                              'parent id': id,
                                              'attrs': [{'entry point': entry_point},
                                                        {'bug kind': 'one thread:double acquisition'}],
                                              'problem desc': 'Fatal error!'},
                                             self.mqs['report files'],
                                             self.conf['root id'])

                psi.utils.report(self.logger,
                                 'finish',
                                 {'id': id,
                                  'resources': {'wall time': random.randint(0, 10000),
                                                'CPU time': random.randint(0, 10000),
                                                'max mem size': random.randint(0, 1000000000)},
                                  'log': '',
                                  'data': ''},
                                 self.mqs['report files'],
                                 self.conf['root id'])

                os.chdir(os.pardir)

    main = generate_verification_tasks

    def extract_common_prj_attrs(self):
        self.logger.info('Extract common project atributes')

        self.common_prj_attrs = self.mqs['VTG common prj attrs'].get()

        self.mqs['VTG common prj attrs'].close()
