#!/usr/bin/python3

import copy
import multiprocessing
import os

import core.components
import core.utils

# VTG strategies.
from core.vtg.abkm import ABKM

_strategies = (ABKM,)


def before_launch_all_components(context):
    context.mqs['VTG common prj attrs'] = multiprocessing.Queue()
    context.mqs['abstract task descs and nums'] = multiprocessing.Queue()
    context.mqs['abstract task descs num'] = multiprocessing.Queue()
    context.mqs['VTG src tree root'] = multiprocessing.Queue()


def after_extract_common_prj_attrs(context):
    context.mqs['VTG common prj attrs'].put(context.common_prj_attrs)


def after_extract_src_tree_root(context):
    context.mqs['VTG src tree root'].put(context.src_tree_root)


def after_generate_abstact_verification_task_desc(context):
    # We need to copy abstrtact verification task description since it may be accidently overwritten by AVTG.
    if context.abstract_task_desc:
        context.mqs['abstract task descs and nums'].put({
            'desc': copy.deepcopy(context.abstract_task_desc),
            'num': context.abstract_task_desc_num
        })


def after_generate_all_abstract_verification_task_descs(context):
    context.logger.info('Terminate abstract verification task descriptions message queue')
    for i in range(core.utils.get_parallel_threads_num(context.logger, context.conf, 'Tasks generation')):
        context.mqs['abstract task descs and nums'].put(None)
    context.mqs['abstract task descs num'].put(context.abstract_task_desc_num)


class VTG(core.components.Component):
    def generate_verification_tasks(self):
        self.strategy = None
        self.common_prj_attrs = {}
        self.abstract_task_descs_num = multiprocessing.Value('i', 0)

        # Get strategy as early as possible to terminate without any delays if strategy isn't supported.
        self.get_strategy()

        self.extract_common_prj_attrs()
        core.utils.report(self.logger,
                          'attrs',
                          {
                              'id': self.id,
                              'attrs': self.common_prj_attrs
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'])

        self.extract_src_tree_root()

        core.utils.invoke_callbacks(self.generate_all_verification_tasks)

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

    def extract_src_tree_root(self):
        self.logger.info('Extract source tree root')

        self.conf['source tree root'] = self.mqs['VTG src tree root'].get()

        self.mqs['VTG src tree root'].close()

        self.logger.debug('Source tree root is "{0}"'.format(self.conf['source tree root']))

    def generate_all_verification_tasks(self):
        self.logger.info('Generate all verification tasks')

        self.launch_subcomponents(
                [self.get_abstract_verification_task_descs_num] +
                [self._generate_verification_tasks for i in
                 range(core.utils.get_parallel_threads_num(self.logger, self.conf, 'Tasks generation'))]
        )

        self.mqs['abstract task descs and nums'].close()

    def get_abstract_verification_task_descs_num(self):
        self.logger.info('Get the total number of abstract verification task descriptions')

        self.abstract_task_descs_num.value = self.mqs['abstract task descs num'].get()

        self.logger.debug('The total number of abstract verification task descriptions is "{0}"'.format(
            self.abstract_task_descs_num.value))

        self.mqs['abstract task descs num'].close()

    def _generate_verification_tasks(self):
        while True:
            abstract_task_desc_and_num = self.mqs['abstract task descs and nums'].get()

            if abstract_task_desc_and_num is None:
                self.logger.debug('Abstract verification task descriptions message queue was terminated')
                break

            abstract_task_desc = abstract_task_desc_and_num['desc']

            # Print progress in form of "the number of already generated abstract verification task descriptions/the
            # number of all abstract verification task descriptions". The latter may be omitted for early abstract
            # verification task descriptions because of it isn't known until the end of AVTG operation.
            self.logger.info('Generate verification tasks for abstract verification task "{0}" ({1}{2})'.format(
                    abstract_task_desc['id'], abstract_task_desc_and_num['num'],
                    '/{0}'.format(self.abstract_task_descs_num.value) if self.abstract_task_descs_num.value else ''))

            attr_vals = tuple(attr[name] for attr in abstract_task_desc['attrs'] for name in attr)

            work_dir = os.path.join(
                    os.path.relpath(
                            os.path.join(self.conf['source tree root'],
                                         '{0}.task'.format(abstract_task_desc['attrs'][0]['verification object']),
                                         abstract_task_desc['attrs'][1]['rule specification'])),
                    self.strategy.__name__.lower())
            os.makedirs(work_dir)
            self.logger.debug('Working directory is "{0}"'.format(work_dir))

            self.conf['abstract task desc'] = abstract_task_desc

            p = self.strategy(self.conf, self.logger, self.id, self.callbacks, self.mqs,
                              '{0}/{1}/{2}'.format(*list(attr_vals) + [self.strategy.__name__.lower()]),
                              work_dir, abstract_task_desc['attrs'], True, True)
            try:
                p.start()
                p.join()
            # Do not fail if verification task generation strategy fails. Just proceed to other abstract verification
            # tasks. Do not print information on failure since it will be printed automatically by core.components.
            except core.components.ComponentError:
                pass
