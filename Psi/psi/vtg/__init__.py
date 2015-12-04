#!/usr/bin/python3

import copy
import multiprocessing
import os
import random

import psi.components
import psi.utils

# VTG strategies.
from psi.vtg.abkm import ABKM

_strategies = (ABKM,)


def before_launch_all_components(context):
    context.mqs['VTG common prj attrs'] = multiprocessing.Queue()
    context.mqs['abstract task descs'] = multiprocessing.Queue()


def after_extract_common_prj_attrs(context):
    context.mqs['VTG common prj attrs'].put(context.common_prj_attrs)


def after_generate_abstact_verification_task_desc(context):
    # We need to copy abstrtact verification task description since it may be accidently overwritten by AVTG.
    if context.abstract_task_desc:
        context.mqs['abstract task descs'].put(copy.deepcopy(context.abstract_task_desc))


def after_generate_all_abstract_verification_task_descs(context):
    context.logger.info('Terminate abstract verification task descriptions message queue')
    context.mqs['abstract task descs'].put(None)


class VTG(psi.components.Component):
    def generate_verification_tasks(self):
        self.strategy = None
        self.common_prj_attrs = {}

        # Get strategy as early as possible to terminate without any delays if strategy isn't supported.
        self.get_strategy()
        self.extract_common_prj_attrs()
        psi.utils.report(self.logger,
                         'attrs',
                         {'id': self.name,
                          'attrs': self.common_prj_attrs},
                         self.mqs['report files'],
                         self.conf['main working directory'])

        self.generate_all_verification_task_descs()

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
                                 self.conf['main working directory'])

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
                                             self.conf['main working directory'])
                        elif i == 0 and k == 1:
                            psi.utils.report(self.logger,
                                             'unsafe',
                                             {'id': 'unsafe',
                                              'parent id': id,
                                              'attrs': [{'bug kind': bug_kind}],
                                              'error trace': 'Error trace 1'},
                                             self.mqs['report files'],
                                             self.conf['main working directory'])
                        else:
                            psi.utils.report(self.logger,
                                             'unsafe',
                                             {'id': 'unsafe1',
                                              'parent id': id,
                                              'attrs': [{'bug kind': bug_kind}],
                                              'error trace': 'Error trace 2'},
                                             self.mqs['report files'],
                                             self.conf['main working directory'],
                                             '1')
                            psi.utils.report(self.logger,
                                             'unsafe',
                                             {'id': 'unsafe2',
                                              'parent id': id,
                                              'attrs': [{'bug kind': bug_kind}],
                                              'error trace': 'Error trace 2'},
                                             self.mqs['report files'],
                                             self.conf['main working directory'],
                                             '2')
                            psi.utils.report(self.logger,
                                             'unknown',
                                             {'id': 'unknown',
                                              'parent id': id,
                                              'attrs': [{'bug kind': bug_kind}],
                                              'problem desc': 'Fatal error!'},
                                             self.mqs['report files'],
                                             self.conf['main working directory'])

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
                                             self.conf['main working directory'])
                        else:
                            psi.utils.report(self.logger,
                                             'unknown',
                                             {'id': 'unknown',
                                              'parent id': id,
                                              'attrs': [{'entry point': entry_point},
                                                        {'bug kind': 'one thread:double acquisition'}],
                                              'problem desc': 'Fatal error!'},
                                             self.mqs['report files'],
                                             self.conf['main working directory'])

                psi.utils.report(self.logger,
                                 'finish',
                                 {'id': id,
                                  'resources': {'wall time': random.randint(0, 10000),
                                                'CPU time': random.randint(0, 10000),
                                                'max mem size': random.randint(0, 1000000000)},
                                  'log': '',
                                  'data': ''},
                                 self.mqs['report files'],
                                 self.conf['main working directory'])

                os.chdir(os.pardir)

    main = generate_verification_tasks

    def get_strategy(self):
        self.logger.info('Get strategy')

        for strategy in _strategies:
            if ''.join([word[0] for word in self.conf['VTG strategy']['name'].split(' ')]) == strategy.__name__.lower():
                self.strategy = strategy

        if not self.strategy:
            NotImplementedError('Strategy {0} is not supported'.format(self.conf['VTG strategy']['name']))

    def extract_common_prj_attrs(self):
        self.logger.info('Extract common project atributes')

        self.common_prj_attrs = self.mqs['VTG common prj attrs'].get()

        self.mqs['VTG common prj attrs'].close()

    def generate_all_verification_task_descs(self):
        self.logger.info('Generate all verification task decriptions')

        while True:
            abstact_task_desc = self.mqs['abstract task descs'].get()

            if abstact_task_desc is None:
                self.logger.debug('Abstract verification task descriptions message queue was terminated')
                self.mqs['abstract task descs'].close()
                break

            # TODO: specification requires to do this in parallel...
            self.generate_verification_task_descs(abstact_task_desc)

    def generate_verification_task_descs(self, abstract_task_desc):
        # TODO: print progress: n + 1/N, where n/N is the number of already generated/all to be generated verification tasks.
        self.logger.info('Generate verification task descriptions for abstract verification task "{0}"'.format(
            abstract_task_desc['id']))

        attr_vals = tuple(attr[name] for attr in abstract_task_desc['attrs'] for name in attr)

        work_dir = os.path.join(
            os.path.relpath(
                os.path.join(self.conf['main working directory'],
                             '{0}.task'.format(abstract_task_desc['attrs'][0]['verification object']),
                             abstract_task_desc['attrs'][1]['rule specification'])),
            self.strategy.__name__.lower())
        os.makedirs(work_dir)
        self.logger.debug('Working directory is "{0}"'.format(work_dir))

        self.conf['abstract task desc'] = abstract_task_desc

        p = self.strategy(self.conf, self.logger, self.name, self.callbacks, self.mqs,
                          '{0}/{1}/{2}'.format(*list(attr_vals) + [self.strategy.__name__.lower()]),
                          work_dir, abstract_task_desc['attrs'], True, True)
        p.start()
        p.join()
