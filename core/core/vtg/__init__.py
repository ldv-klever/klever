#!/usr/bin/python3

import importlib
import json
import multiprocessing
import os
import glob
import re

import core.components
import core.utils


def before_launch_sub_job_components(context):
    context.mqs['VTG common prj attrs'] = multiprocessing.Queue()
    context.mqs['abstract task desc files and nums'] = multiprocessing.Queue()
    context.mqs['abstract task descs num'] = multiprocessing.Queue()


def after_set_common_prj_attrs(context):
    context.mqs['VTG common prj attrs'].put(context.common_prj_attrs)


def after_generate_abstact_verification_task_desc(context):
    if context.abstract_task_desc_file:
        context.mqs['abstract task desc files and nums'].put({
            'desc file': os.path.relpath(context.abstract_task_desc_file, context.conf['main working directory']),
            'num': context.abstract_task_desc_num
        })


def after_generate_all_abstract_verification_task_descs(context):
    context.logger.info('Terminate abstract verification task descriptions message queue')
    for i in range(core.utils.get_parallel_threads_num(context.logger, context.conf, 'Tasks generation')):
        context.mqs['abstract task desc files and nums'].put(None)
    context.mqs['abstract task descs num'].put(context.abstract_task_desc_num)


class VTG(core.components.Component):

    verifier_results_regexp = r"\[assert=\[(.+)\], time=(\d+), verdict=(\w+)\]"
    xi = 5  # TODO:should be placed outside
    phi = 1/2

    def generate_verification_tasks(self):
        self.strategy_name = None
        self.strategy = None
        self.common_prj_attrs = {}
        self.abstract_task_descs_num = multiprocessing.Value('i', 0)
        self.time_limit = self.conf['VTG strategy']['resource limits']['CPU time']

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

    def get_strategy(self):
        self.logger.info('Get strategy')

        self.strategy_name = ''.join([word[0] for word in self.conf['VTG strategy']['name'].split(' ')])

        if self.strategy_name == "g":
            # Global
            self.logger.info('Using GLOBAL strategy')
        else:
            try:
                self.strategy = getattr(importlib.import_module('.{0}'.format(self.strategy_name), 'core.vtg'),
                                        self.strategy_name.upper())
            except ImportError:
                raise NotImplementedError('Strategy "{0}" is not supported'.format(self.conf['VTG strategy']['name']))

    def get_common_prj_attrs(self):
        self.logger.info('Get common project atributes')

        self.common_prj_attrs = self.mqs['VTG common prj attrs'].get()

        self.mqs['VTG common prj attrs'].close()

    def generate_all_verification_tasks(self):
        self.logger.info('Generate all verification tasks')

        subcomponents = [('AVTDNG', self.get_abstract_verification_task_descs_num)]
        if self.strategy_name == "g":
            for i in range(core.utils.get_parallel_threads_num(self.logger, self.conf, 'Tasks generation')):
                subcomponents.append(('Worker {0}'.format(i), self._generate_global_verification_tasks))
        else:
            for i in range(core.utils.get_parallel_threads_num(self.logger, self.conf, 'Tasks generation')):
                subcomponents.append(('Worker {0}'.format(i), self._generate_verification_tasks))

        self.launch_subcomponents(*subcomponents)

        self.logger.info('Terminate abstract verification task description files and numbers message queue')
        self.mqs['abstract task desc files and nums'].close()

    def get_abstract_verification_task_descs_num(self):
        self.logger.info('Get the total number of abstract verification task descriptions')

        self.abstract_task_descs_num.value = self.mqs['abstract task descs num'].get()

        self.mqs['abstract task descs num'].close()

        self.logger.debug('The total number of abstract verification task descriptions is "{0}"'.format(
            self.abstract_task_descs_num.value))

        core.utils.report(self.logger,
                          'data',
                          {
                              'id': self.id,
                              'data': json.dumps(self.abstract_task_descs_num.value)
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'])

    def parse_bug_kind(self, bug_kind):
        match = re.search(r'(.+)::(.*)', bug_kind)
        if match:
            return match.groups()[0]
        else:
            return ''

    def _generate_verification_tasks(self):
        while True:
            abstract_task_desc_file_and_num = self.mqs['abstract task desc files and nums'].get()

            if abstract_task_desc_file_and_num is None:
                self.logger.debug('Abstract verification task descriptions message queue was terminated')
                break

            abstract_task_desc_file = os.path.join(self.conf['main working directory'],
                                                   abstract_task_desc_file_and_num['desc file'])

            with open(abstract_task_desc_file, encoding='ascii') as fp:
                abstract_task_desc = json.load(fp)

            if not self.conf['keep intermediate files']:
                os.remove(abstract_task_desc_file)

            # Print progress in form of "the number of already generated abstract verification task descriptions/the
            # number of all abstract verification task descriptions". The latter may be omitted for early abstract
            # verification task descriptions because of it isn't known until the end of AVTG operation.
            self.logger.info('Generate verification tasks for abstract verification task "{0}" ({1}{2})'.format(
                    abstract_task_desc['id'], abstract_task_desc_file_and_num['num'],
                    '/{0}'.format(self.abstract_task_descs_num.value) if self.abstract_task_descs_num.value else ''))

            attr_vals = tuple(attr[name] for attr in abstract_task_desc['attrs'] for name in attr)
            work_dir = os.path.join(abstract_task_desc['attrs'][0]['verification object'],
                                    abstract_task_desc['attrs'][1]['rule specification'],
                                    self.strategy_name)
            os.makedirs(work_dir)
            self.logger.debug('Working directory is "{0}"'.format(work_dir))

            self.conf['abstract task desc'] = abstract_task_desc

            asserts = 0
            latest_assert = None
            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                if 'bug kinds' in extra_c_file:
                    asserts += 1
                    common_bug_kind = extra_c_file['bug kinds'][0]
                    latest_assert = self.parse_bug_kind(common_bug_kind)

            if (self.strategy_name == 'mavr' or self.strategy_name == 'mpvr') and asserts == 1:
                self.logger.info('Changing "{0}" strategy to SR'.format(self.strategy_name))
                self.conf['unite rule specifications'] = False
                self.strategy = getattr(importlib.import_module('.{0}'.format('sr'), 'core.vtg'), 'SR')
                self.conf['abstract task desc']['attrs'][1]['rule specification'] = latest_assert

            p = self.strategy(self.conf, self.logger, self.id, self.callbacks, self.mqs, self.locks,
                              '{0}/{1}/{2}'.format(*list(attr_vals) + [self.strategy_name]),
                              work_dir, abstract_task_desc['attrs'], True, True)
            try:
                p.start()
                p.join()
            # Do not fail if verification task generation strategy fails. Just proceed to other abstract verification
            # tasks. Do not print information on failure since it will be printed automatically by core.components.
            except core.components.ComponentError:
                pass

    def _generate_global_verification_tasks(self):
        while True:
            abstract_task_desc_file_and_num = self.mqs['abstract task desc files and nums'].get()

            if abstract_task_desc_file_and_num is None:
                self.logger.debug('Abstract verification task descriptions message queue was terminated')
                break

            abstract_task_desc_file = os.path.join(self.conf['main working directory'],
                                                   abstract_task_desc_file_and_num['desc file'])

            with open(abstract_task_desc_file, encoding='ascii') as fp:
                abstract_task_desc = json.load(fp)

            if not self.conf['keep intermediate files']:
                os.remove(abstract_task_desc_file)

            # Print progress in form of "the number of already generated abstract verification task descriptions/the
            # number of all abstract verification task descriptions". The latter may be omitted for early abstract
            # verification task descriptions because of it isn't known until the end of AVTG operation.
            self.logger.debug('Generate verification tasks for abstract verification task "{0}" ({1}{2})'.format(
                    abstract_task_desc['id'], abstract_task_desc_file_and_num['num'],
                    '/{0}'.format(self.abstract_task_descs_num.value) if self.abstract_task_descs_num.value else ''))

            attr_vals = tuple(attr[name] for attr in abstract_task_desc['attrs'] for name in attr)
            work_dir = os.path.join(abstract_task_desc['attrs'][0]['verification object'],
                                    abstract_task_desc['attrs'][1]['rule specification'],
                                    self.strategy_name, 'step1')
            os.makedirs(work_dir)
            self.logger.debug('Working directory is "{0}"'.format(work_dir))

            self.conf['abstract task desc'] = abstract_task_desc

            # Step 1. external CMAV L1 with only 1 iteration.
            self.logger.info('GLOBAL: Execute step 1')
            self.logger.info('GLOBAL: Launch CMAV L1 with only 1 iteration')

            relevant = []
            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                if 'relevant' in extra_c_file and 'bug kinds' in extra_c_file:
                    common_bug_kind = extra_c_file['bug kinds'][0]
                    latest_assert = self.parse_bug_kind(common_bug_kind)
                    if extra_c_file['relevant']:
                        relevant.append(latest_assert)

            self.logger.info('GLOBAL: Got {0} most likely relevant rules'.format(len(relevant)))

            results = {}
            unknown_reasons = {}
            is_completed = True
            is_good_results = False
            is_error = False
            is_skip_1_step = False
            if len(relevant) >= self.xi:
                # The task is too complex, so skip step 1.
                is_skip_1_step = True
                is_completed = False
                is_good_results = False
                self.logger.info('GLOBAL: Skipping step 1 due to too complex task')
                for extra_c_file in self.conf['abstract task desc']['extra C files']:
                    if 'bug kinds' in extra_c_file:
                        common_bug_kind = extra_c_file['bug kinds'][0]
                        latest_assert = self.parse_bug_kind(common_bug_kind)
                        if latest_assert in relevant:
                            results[latest_assert] = 'unknown-incomplete'
                        else:
                            results[latest_assert] = 'checking'

            if not is_skip_1_step:
                self.strategy = getattr(importlib.import_module('.{0}'.format('mavr'), 'core.vtg'), 'MAVR')
                self.conf['unite rule specifications'] = True
                self.conf['VTG strategy']['verifier']['relaunch'] = 'no'
                self.conf['VTG strategy']['verifier']['alias'] = 'cmav'  # TODO: place it in some config file
                self.conf['VTG strategy']['verifier']['MAV preset'] = 'L1'
                self.conf['VTG strategy']['verifier']['options'] = [{'-ldv': ''}]
                self.conf['RSG strategy'] = 'instrumentation'
                self.conf['VTG strategy']['resource limits']['CPU time'] = round(self.phi * self.time_limit)
                p = self.strategy(self.conf, self.logger, self.id, self.callbacks, self.mqs, self.locks,
                                  '{0}/{1}/{2}/step1'.format(*list(attr_vals) + [self.strategy_name]),
                                  work_dir, abstract_task_desc['attrs'], True, True)
                try:
                    p.start()
                    p.join()
                # Do not fail if verification task generation strategy fails. Just proceed to other abstract verification
                # tasks. Do not print information on failure since it will be printed automatically by core.components.
                except core.components.ComponentError:
                    pass

                self.logger.info('GLOBAL: Step 1 has been completed')
                path_to_cmav_results = '{0}/output/mav_results_file'.format(p.work_dir)
                self.logger.debug('Path to CMAV results file is "{0}"'.format(path_to_cmav_results))
                log_files = glob.glob(os.path.join(p.work_dir, 'output', 'benchmark*logfiles/*'))
                if log_files:
                    path_to_cmav_log = log_files[0]
                    self.logger.debug('Path to CMAV log file is "{0}"'.format(path_to_cmav_log))

                # Analyse results file.
                if os.path.isfile(path_to_cmav_results):
                    with open(path_to_cmav_results) as f_res:
                        for line in f_res:
                            result = re.search(self.verifier_results_regexp, line)
                            if result:
                                bug_kind = result.group(1)
                                verdict = result.group(3).lower()
                                if verdict == 'safe':
                                    is_good_results = True
                                if verdict == 'safe' or verdict == 'unsafe':
                                    results[bug_kind] = verdict
                                elif verdict == 'unknown':
                                    is_completed = False
                                    results[bug_kind] = 'unknown-incomplete'
                                else:
                                    is_completed = False
                                    results[bug_kind] = 'checking'
                            else:
                                result = re.search(r'\[(.+)\]', line)
                                if result:
                                    # LCA here.
                                    LCA = result.group(1)
                                    if results[LCA] == 'checking':
                                        results[LCA] = 'unknown-incomplete'
                                        unknown_reasons[LCA] = 'LCA'
                else:
                    # Verifier failed before even starting verification.
                    # There is nothing to be done - strategy should stop.
                    self.logger.info('GLOBAL: Stop due to global error: no results file')
                    is_error = True

                # Analyse log file.
                if not is_completed:
                    if path_to_cmav_log and os.path.isfile(path_to_cmav_log):
                        with open(path_to_cmav_log) as f_res:
                            for line in f_res:
                                result = re.search(r'Assert \[(.+)\] has exhausted its Basic Interval Time Limit', line)
                                if result:
                                    rule = result.group(1)
                                    unknown_reasons[rule] = 'BITL'
                                result = re.search(r'Assert \[(.+)\] has exhausted its Assert Time Limit', line)
                                if result:
                                    rule = result.group(1)
                                    unknown_reasons[rule] = 'ATL'
                                    results[rule] = 'unknown'
                                result = re.search(r'Error: First Interval Time Limit has been exhausted', line)
                                if result:
                                    for rule, verdict in results.items():
                                        if verdict != 'unsafe':
                                            results[rule] = 'checking'
                    else:
                        # It should not be reached, but we should process it anyway.
                        self.logger.info('GLOBAL: Stop due to global error: no log file')
                        is_error = True

            # Results of Step 1.
            is_completed = True
            number_of_separated = 0
            for rule, verdict in results.items():
                if verdict == 'checking' or verdict == 'unknown-incomplete':
                    is_completed = False
                self.logger.debug('Rule "{0}" got verdict "{1}"'.format(rule, verdict))
                if verdict == 'unknown':
                    if rule in unknown_reasons:
                        self.logger.debug('Rule "{0}" got unknown verdict due to "{1}"'.format(rule, unknown_reasons[rule]))
                if verdict == 'unknown-incomplete':
                    if rule in unknown_reasons:
                        self.logger.debug('Rule "{0}" got unknown-incomplete verdict due to "{1}"'.format(rule, unknown_reasons[rule]))
                    number_of_separated += 1

            if not is_completed and not is_error:
                old_extra_c_files = self.conf['abstract task desc']['extra C files']
                if number_of_separated >= 1:
                    self.logger.info('GLOBAL: Execute step 2')
                    extra_c_files = []
                    for extra_c_file in self.conf['abstract task desc']['extra C files']:
                        if 'bug kinds' in extra_c_file:
                            if 'C file' in extra_c_file:
                                del extra_c_file['C file']
                            common_bug_kind = extra_c_file['bug kinds'][0]
                            rule = self.parse_bug_kind(common_bug_kind)
                            verdict = results[rule]
                            if verdict == 'unknown-incomplete':
                                self.logger.debug('Rule "{0}" will be rechecked separately'.format(rule))
                                extra_c_files.append(extra_c_file)
                        else:
                            extra_c_files.append(extra_c_file)

                    self.conf['abstract task desc']['extra C files'] = extra_c_files

                    if number_of_separated == 1:
                        self.logger.info('GLOBAL: Launch SR')
                        self.conf['unite rule specifications'] = False
                        self.conf['RSG strategy'] = 'property automaton'
                        self.conf['VTG strategy']['verifier']['alias'] = 'mpv'  # TODO: place it in some config file
                        self.conf['VTG strategy']['verifier']['options'] = [{'-ldv-spa': ''}]
                        self.conf['VTG strategy']['resource limits']['CPU time'] = self.time_limit
                        self.strategy = getattr(importlib.import_module('.{0}'.format('sr'), 'core.vtg'), 'SR')
                        for rule, verdict in results.items():
                            if verdict == 'unknown-incomplete':
                                self.conf['abstract task desc']['attrs'][1]['rule specification'] = rule
                    else:
                        self.logger.info('GLOBAL: Launch MPV-Sep')
                        self.strategy = getattr(importlib.import_module('.{0}'.format('mpvr'), 'core.vtg'), 'MPVR')
                        self.conf['RSG strategy'] = 'property automaton'
                        self.conf['unite rule specifications'] = True
                        self.conf['VTG strategy']['verifier']['MPV strategy'] = 'Sep'
                        self.conf['VTG strategy']['verifier']['alias'] = 'mpv'  # TODO: place it in some config file
                        self.conf['VTG strategy']['verifier']['options'] = [{'-ldv-mpa': ''}]
                        self.conf['VTG strategy']['resource limits']['CPU time'] = self.time_limit

                    work_dir = os.path.join(abstract_task_desc['attrs'][0]['verification object'],
                                    abstract_task_desc['attrs'][1]['rule specification'],
                                    self.strategy_name, 'step2')
                    os.makedirs(work_dir)
                    self.logger.debug('Working directory is "{0}"'.format(work_dir))

                    p = self.strategy(self.conf, self.logger, self.id, self.callbacks, self.mqs, self.locks,
                                      '{0}/{1}/{2}/step2'.format(*list(attr_vals) + [self.strategy_name]),
                                      work_dir, abstract_task_desc['attrs'], True, True)
                    try:
                        p.start()
                        p.join()
                    except core.components.ComponentError:
                        pass
                    self.logger.info('GLOBAL: Step 2 has been completed')
                else:
                    self.logger.info('GLOBAL: Step 2 is not required')

                if not is_good_results:
                    self.logger.info('GLOBAL: Execute step 3')
                    self.logger.info('GLOBAL: Launch MPV-Relevance')
                    extra_c_files = []
                    for extra_c_file in old_extra_c_files:
                        if 'bug kinds' in extra_c_file:
                            if 'C file' in extra_c_file:
                                del extra_c_file['C file']
                            common_bug_kind = extra_c_file['bug kinds'][0]
                            rule = self.parse_bug_kind(common_bug_kind)
                            verdict = results[rule]
                            if verdict == 'checking':
                                self.logger.debug('Rule "{0}" will be rechecked'.format(rule))
                                extra_c_files.append(extra_c_file)
                        else:
                            extra_c_files.append(extra_c_file)

                    self.conf['abstract task desc']['extra C files'] = extra_c_files

                    self.strategy = getattr(importlib.import_module('.{0}'.format('mpvr'), 'core.vtg'), 'MPVR')
                    self.conf['RSG strategy'] = 'property automaton'
                    self.conf['unite rule specifications'] = True
                    self.conf['VTG strategy']['verifier']['MPV strategy'] = 'Relevance'
                    self.conf['VTG strategy']['verifier']['alias'] = 'mpv'  # TODO: place it in some config file
                    self.conf['VTG strategy']['verifier']['options'] = [{'-ldv-mpa': ''}]
                    self.conf['VTG strategy']['resource limits']['CPU time'] = self.time_limit

                    work_dir = os.path.join(abstract_task_desc['attrs'][0]['verification object'],
                                    abstract_task_desc['attrs'][1]['rule specification'],
                                    self.strategy_name, 'step3')
                    os.makedirs(work_dir)
                    self.logger.debug('Working directory is "{0}"'.format(work_dir))

                    p = self.strategy(self.conf, self.logger, self.id, self.callbacks, self.mqs, self.locks,
                                      '{0}/{1}/{2}/step3'.format(*list(attr_vals) + [self.strategy_name]),
                                      work_dir, abstract_task_desc['attrs'], True, True)
                    try:
                        p.start()
                        p.join()
                    except core.components.ComponentError:
                        pass
                    self.logger.info('GLOBAL: Step 3 has been completed')
                else:
                    self.logger.info('GLOBAL: Step 3 is not required')

            self.logger.info('GLOBAL: All steps have been completed')
