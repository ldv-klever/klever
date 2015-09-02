#!/usr/bin/python3

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
