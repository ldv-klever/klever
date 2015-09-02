#!/usr/bin/python3

import copy
import multiprocessing
import os
import random

import psi.components
import psi.utils

name = 'AVTG'


def before_launch_all_components(context):
    context['MQs']['{0} common prj attrs'.format(name)] = multiprocessing.Queue()
    context['MQs']['verification obj descs'] = multiprocessing.Queue()


def after_extract_common_prj_attrs(context):
    context.mqs['{0} common prj attrs'.format(name)].put(context.common_prj_attrs)


def after_generate_verification_obj_desc(context):
    # We need to copy verification object description since it may be accidently overwritten by LKVOG.
    context.mqs['verification obj descs'].put(copy.deepcopy(context.verification_obj_desc))


def after_generate_all_verification_obj_descs(context):
    context.logger.info('Terminate verification object descriptions message queue')
    context.mqs['verification obj descs'].put(None)


# TODO: get callbacks of plugins.


class PsiComponent(psi.components.PsiComponentBase):
    def launch(self):
        self.common_prj_attrs = {}
        self.extract_common_prj_attrs()
        psi.utils.report(self.logger,
                         'attrs',
                         {'id': self.name,
                          'attrs': self.common_prj_attrs},
                         self.mqs['report files'],
                         self.conf['root id'])
        self.rule_spec_descs = _extract_rule_spec_descs(self.conf, self.logger)
        psi.utils.invoke_callbacks(self.generate_all_abstract_verification_task_descs)

        # TODO: delete following stub code after all.
        # Start and finish AVTG plugins.
        for i, verification_obj in enumerate(('drivers/usb/core/usbcore.ko', 'drivers/usb/usb-commmon.ko')):
            for j, rule_spec in enumerate(('mutex', 'spin lock')):
                for plugin in ('DEG', 'RI'):
                    # Surprise! RI11 isn't started since DEG11 is going to fail. Keep in touch!
                    if i == 1 and j == 1 and plugin == 'RI':
                        continue

                    id = '{0}/{1}/{2}'.format(verification_obj, rule_spec, plugin)
                    plugin_work_dir = '{0}{1}{2}'.format(plugin, i, j)

                    os.makedirs(plugin_work_dir)
                    os.chdir(plugin_work_dir)

                    psi.utils.report(self.logger,
                                     'start',
                                     {'id': id,
                                      'attrs': [{'verification object': verification_obj},
                                                {'rule specification': rule_spec}],
                                      'name': plugin,
                                      'parent id': 'AVTG'},
                                     self.mqs['report files'],
                                     self.conf['root id'])

                    # As promised DEG11 fails.
                    if i == 1 and j == 1 and plugin == 'DEG':
                        psi.utils.report(self.logger,
                                         'unknown',
                                         {'id': 'unknown',
                                          'parent id': id,
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

    def extract_common_prj_attrs(self):
        self.logger.info('Extract common project atributes')

        self.common_prj_attrs = self.mqs['{0} common prj attrs'.format(name)].get()

        self.mqs['{0} common prj attrs'.format(name)].close()

    def generate_all_abstract_verification_task_descs(self):
        self.logger.info('Generate all abstract verification task decriptions')

        while True:
            verification_obj_desc = self.mqs['verification obj descs'].get()

            if verification_obj_desc is None:
                self.logger.debug('Verification object descriptions message queue was terminated')
                self.mqs['verification obj descs'].close()
                break

            # TODO: specification requires to do this in parallel...
            for rule_spec_desc in self.rule_spec_descs:
                self.generate_abstact_verification_task_desc(verification_obj_desc, rule_spec_desc)

    def generate_abstact_verification_task_desc(self, verification_obj_desc, rule_spec_desc):
        self.logger.info(
            'Generate abstract verification task description for {0}'.format(
                'verification object "{0}" and rule specification "{1}"'.format(
                    verification_obj_desc['id'], rule_spec_desc['id'])))

        # TODO: generate abstract verification task description!


def _extract_rule_spec_descs(conf, logger):
    logger.info('Extract rule specificaction decriptions')

    descs = []

    for id in conf['rule specs']:
        # TODO: get actual rule specification descriptions!
        desc = {'id': id}
        descs.append(desc)

    return descs
