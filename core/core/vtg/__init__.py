#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import importlib
import json
import multiprocessing
import os

import core.components
import core.utils


def before_launch_sub_job_components(context):
    context.mqs['VTG common prj attrs'] = multiprocessing.Queue()
    context.mqs['abstract task desc files'] = multiprocessing.Queue()
    context.mqs['num of abstract task descs to be generated'] = multiprocessing.Queue()


def after_set_common_prj_attrs(context):
    context.mqs['VTG common prj attrs'].put(context.common_prj_attrs)


def after_generate_abstact_verification_task_desc(context):
    context.mqs['abstract task desc files'].put(
        os.path.relpath(context.abstract_task_desc_file, context.conf['main working directory'])
        if context.abstract_task_desc_file
        else '')


def after_evaluate_abstract_verification_task_descs_num(context):
    context.mqs['num of abstract task descs to be generated'].put(context.abstract_task_descs_num.value)


def after_generate_all_abstract_verification_task_descs(context):
    context.logger.info('Terminate abstract verification task descriptions message queue')
    for i in range(core.utils.get_parallel_threads_num(context.logger, context.conf, 'Tasks generation')):
        context.mqs['abstract task desc files'].put(None)


class VTG(core.components.Component):
    def generate_verification_tasks(self):
        self.strategy_name = None
        self.strategy = None
        self.common_prj_attrs = {}
        self.faulty_generated_abstract_task_descs_num = multiprocessing.Value('i', 0)
        self.num_of_abstract_task_descs_to_be_processed = multiprocessing.Value('i', 0)
        self.processed_abstract_task_desc_num = multiprocessing.Value('i', 0)
        self.faulty_processed_abstract_task_descs_num = multiprocessing.Value('i', 0)

        # Get strategy as early as possible to terminate without any delays if strategy isn't supported.
        self.get_strategy()

        self.get_common_prj_attrs()
        core.utils.report(self.logger,
                          'attrs',
                          {
                              'id': self.id,
                              'attrs': self.common_prj_attrs
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'])

        self.generate_all_verification_tasks()

    main = generate_verification_tasks

    def get_strategy(self, specific_strategy_desc=None):
        self.logger.info('Get strategy')

        strategy_desc = specific_strategy_desc if specific_strategy_desc else self.conf['VTG strategy']

        self.strategy_name = ''.join([word[0] for word in strategy_desc['name'].split(' ')])

        try:
            self.strategy = getattr(importlib.import_module('.{0}'.format(self.strategy_name), 'core.vtg'),
                                    self.strategy_name.upper())
        except ImportError:
            raise NotImplementedError('Strategy "{0}" is not supported'.format(strategy_desc['name']))


    def get_common_prj_attrs(self):
        self.logger.info('Get common project atributes')

        self.common_prj_attrs = self.mqs['VTG common prj attrs'].get()

        self.mqs['VTG common prj attrs'].close()

    def generate_all_verification_tasks(self):
        self.logger.info('Generate all verification tasks')

        subcomponents = [('NAVTDBPE', self.evaluate_num_of_abstract_verification_task_descs_to_be_processed)]
        for i in range(core.utils.get_parallel_threads_num(self.logger, self.conf, 'Tasks generation')):
            subcomponents.append(('Worker {0}'.format(i), self._generate_verification_tasks))

        self.launch_subcomponents(*subcomponents)

        self.mqs['abstract task desc files'].close()

        if self.faulty_processed_abstract_task_descs_num.value:
            self.logger.info('Could not process "{0}" abstract verification task descriptions'.format(
                self.faulty_processed_abstract_task_descs_num.value))

    def evaluate_num_of_abstract_verification_task_descs_to_be_processed(self):
        self.logger.info('Get the total number of abstract verification task descriptions to be generated in ideal')

        num_of_abstract_task_descs_to_be_generated = self.mqs['num of abstract task descs to be generated'].get()

        self.mqs['num of abstract task descs to be generated'].close()

        self.logger.debug(
            'The total number of abstract verification task descriptions to be generated in ideal is "{0}"'.format(
                num_of_abstract_task_descs_to_be_generated))

        self.num_of_abstract_task_descs_to_be_processed.value = num_of_abstract_task_descs_to_be_generated

        self.logger.info(
            'The total number of abstract verification task descriptions to be processed in ideal is "{0}"'.format(
                self.num_of_abstract_task_descs_to_be_processed.value -
                self.faulty_generated_abstract_task_descs_num.value))

        if self.faulty_generated_abstract_task_descs_num.value:
            self.logger.debug(
                'It was taken into account that generation of "{0}" abstract verification task descriptions failed'.
                format(self.faulty_generated_abstract_task_descs_num.value))

    def _generate_verification_tasks(self):
        while True:
            abstract_task_desc_file = self.mqs['abstract task desc files'].get()

            if abstract_task_desc_file is None:
                self.logger.debug('Abstract verification task descriptions message queue was terminated')
                break

            if abstract_task_desc_file is '':
                with self.faulty_generated_abstract_task_descs_num.get_lock():
                    self.faulty_generated_abstract_task_descs_num.value += 1
                self.logger.info(
                    'The total number of abstract verification task descriptions to be processed in ideal is "{0}"'
                    .format(self.num_of_abstract_task_descs_to_be_processed.value -
                            self.faulty_generated_abstract_task_descs_num.value))
                self.logger.debug(
                    'It was taken into account that generation of "{0}" abstract verification task descriptions failed'.
                    format(self.faulty_generated_abstract_task_descs_num.value))
                continue

            # Count the number of processed abstract verification task descriptions.
            self.processed_abstract_task_desc_num.value += 1

            abstract_task_desc_file = os.path.join(self.conf['main working directory'], abstract_task_desc_file)

            with open(abstract_task_desc_file, encoding='utf8') as fp:
                abstract_task_desc = json.load(fp)

            if not self.conf['keep intermediate files']:
                os.remove(abstract_task_desc_file)

            self.logger.info('Generate verification tasks for abstract verification task "{0}" ({1}{2})'.format(
                    abstract_task_desc['id'], self.processed_abstract_task_desc_num.value,
                    '/{0}'.format(self.num_of_abstract_task_descs_to_be_processed.value -
                                  self.faulty_generated_abstract_task_descs_num.value)
                    if self.num_of_abstract_task_descs_to_be_processed.value else ''))

            attr_vals = tuple(attr[name] for attr in abstract_task_desc['attrs'] for name in attr)
            work_dir = os.path.join(abstract_task_desc['attrs'][0]['verification object'],
                                    abstract_task_desc['attrs'][1]['rule specification'],
                                    self.strategy_name)
            os.makedirs(work_dir.encode('utf8'))
            self.logger.debug('Working directory is "{0}"'.format(work_dir))

            self.conf['abstract task desc'] = abstract_task_desc

            if 'VTG strategy' in abstract_task_desc:
                self.get_strategy(abstract_task_desc['VTG strategy'])

            p = self.strategy(self.conf, self.logger, self.id, self.callbacks, self.mqs, self.locks,
                              '{0}/{1}/{2}'.format(*list(attr_vals) + [self.strategy_name]),
                              work_dir,
                              # Always report just verification object as attribute.
                              attrs=[abstract_task_desc['attrs'][0]],
                              # Rule specification will be added just in case of failures since otherwise it is added
                              # somehow by strategies themselves.
                              unknown_attrs=[abstract_task_desc['attrs'][1]],
                              separate_from_parent=True, include_child_resources=True)
            try:
                p.start()
                p.join()
            # Do not fail if verification task generation strategy fails. Just proceed to other abstract verification
            # tasks. Do not print information on failure since it will be printed automatically by core.components.
            except core.components.ComponentError:
                # Count the number of abstract verification task descriptions that weren't processed to print it at the
                # end of work. Note that the total number of abstract verification task descriptions to be processed in
                # ideal will be printed at least once already.
                with self.faulty_processed_abstract_task_descs_num.get_lock():
                    self.faulty_processed_abstract_task_descs_num.value += 1
                    core.utils.report(self.logger,
                                      'data',
                                      {
                                          'id': self.id,
                                          'data': json.dumps({
                                              'faulty processed abstract verification task descriptions':
                                                  self.faulty_processed_abstract_task_descs_num.value
                                          }, ensure_ascii=False, sort_keys=True, indent=4)
                                      },
                                      self.mqs['report files'],
                                      self.conf['main working directory'],
                                      self.faulty_processed_abstract_task_descs_num.value)
