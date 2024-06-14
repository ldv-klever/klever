#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
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

import os
import re
import json
import copy
import hashlib
import importlib
import collections
import resource

import klever.core.components
import klever.core.utils
import klever.core.session

from klever.scheduler.schedulers.global_config import clear_workers_cpu_cores, reserve_workers_cpu_cores

# Classes for queue transfer
Abstract = collections.namedtuple('AbstractTask', 'fragment rule_class')
Task = collections.namedtuple('Task', 'fragment rule_class envmodel rule workdir, envattrs')


class VTG(klever.core.components.Component):

    def __init__(self, conf, logger, parent_id, mqs, vals, cur_id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False):
        super().__init__(conf, logger, parent_id, mqs, vals, cur_id, work_dir, attrs,
                         separate_from_parent, include_child_resources)
        self.model_headers = {}
        self.req_spec_descs = []
        self.req_spec_classes = []
        self.fragment_descs = {}
        self.resource_limits = klever.core.utils.read_max_resource_limitations(self.logger, self.conf)
        self.max_worker_threads = klever.core.utils.get_parallel_threads_num(self.logger, self.conf, 'EMG')

    def generate_verification_tasks(self):
        self.__extract_fragments_descs()
        self.__extract_req_spec_descs()
        self.__classify_req_spec_descs()

        # Wait until all tasks are generated
        self.__generate_all_abstract_verification_task_descs()

        self.clean_dir = True
        self.logger.info('Terminating the last queues')
        self.mqs['pending tasks'].put(None)

    main = generate_verification_tasks

    def __extract_template_plugin_descs(self, tmpl_descs):
        for tmpl_id, tmpl_desc in tmpl_descs.items():
            self.logger.info('Extract options for plugins of template "%s"', tmpl_id)

            if 'plugins' not in tmpl_desc:
                raise ValueError('Template "{0}" has not mandatory attribute "plugins"'.format(tmpl_id))

            for idx, plugin_desc in enumerate(tmpl_desc['plugins']):
                if not isinstance(plugin_desc, dict) or 'name' not in plugin_desc:
                    raise ValueError(
                        'Description of template "{0}" plugin "{1}" has incorrect format'.format(tmpl_id, idx))

            self.logger.debug(
                'Template "%s" plugins are "%s"', tmpl_id, [plugin_desc['name'] for plugin_desc in
                                                            tmpl_desc['plugins']])

            # Get options for plugins specified in base template and merge them with the ones extracted above.
            if 'template' in tmpl_desc:
                if tmpl_desc['template'] not in tmpl_descs:
                    raise ValueError(
                        'Template "{0}" of template "{1}" could not be found in specifications base'
                        .format(tmpl_desc['template'], tmpl_id))

                self.logger.debug('Template "%s" template is "%s"', tmpl_id, tmpl_desc['template'])

                for plugin_desc in tmpl_desc['plugins']:
                    for base_tmpl_plugin_desc in tmpl_descs[tmpl_desc['template']]['plugins']:
                        if plugin_desc['name'] == base_tmpl_plugin_desc['name']:
                            if 'options' in base_tmpl_plugin_desc:
                                if 'options' in plugin_desc:
                                    base_tmpl_plugin_opts = copy.deepcopy(base_tmpl_plugin_desc['options'])
                                    plugin_desc['options'] = klever.core.utils.merge_confs(
                                        base_tmpl_plugin_opts, plugin_desc['options'])
                                else:
                                    plugin_desc['options'] = base_tmpl_plugin_desc['options']
                            break

    # TODO: support inheritance of template sequences, i.e. when requirement needs template that is template of another one.
    def __extract_req_spec_descs(self):
        self.logger.info('Extract requirement specification descriptions')

        if 'specifications base' not in self.conf:
            raise KeyError('Nothing will be verified since specifications base is not specified')

        if 'requirement specifications' not in self.conf:
            raise KeyError('Nothing will be verified since requirement specifications to be checked are not specified')

        # Read specifications base.
        with open(self.conf['specifications base'], encoding='utf-8') as fp:
            raw_req_spec_descs = json.load(fp)

        if 'templates' not in raw_req_spec_descs:
            raise KeyError('Specifications base has not mandatory attribute "templates"')

        if 'requirement specifications' not in raw_req_spec_descs:
            raise KeyError('Specifications base has not mandatory attribute "requirement specifications"')

        tmpl_descs = raw_req_spec_descs['templates']
        self.__extract_template_plugin_descs(tmpl_descs)

        def exist_tmpl(tmpl_id, cur_req_id):
            if tmpl_id and tmpl_id not in tmpl_descs:
                raise KeyError('Template "{0}" for "{1}" is not described'.format(tmpl_id, cur_req_id))

        # Get identifiers, template identifiers and plugin options for all requirement specifications.
        def get_req_spec_descs(cur_req_spec_descs, cur_req_id, parent_tmpl_id):
            # Requirement specifications are described as a tree where leaves correspond to individual requirement
            # specifications while intermediate nodes hold common parts of requirement specification identifiers,
            # optional template identifiers and optional descriptions.
            # Handle sub-tree.
            if isinstance(cur_req_spec_descs, list):
                res_req_spec_descs = {}
                for idx, cur_req_spec_desc in enumerate(cur_req_spec_descs):
                    if 'identifier' not in cur_req_spec_desc:
                        raise KeyError('Identifier is not specified for {0} child of "{1}"'.format(idx, cur_req_id))

                    next_req_id = '{0}{1}'.format('{0}:'.format(cur_req_id) if cur_req_id else '',
                                                  cur_req_spec_desc['identifier'])

                    # Templates can be specified for requirement specification sub-trees and individual requirement
                    # specifications.
                    if 'template' in cur_req_spec_desc:
                        cur_tmpl_id = cur_req_spec_desc['template']
                        exist_tmpl(cur_tmpl_id, next_req_id)
                    else:
                        cur_tmpl_id = parent_tmpl_id

                    # Handle another one sub-tree.
                    if 'children' in cur_req_spec_desc:
                        res_req_spec_descs.update(get_req_spec_descs(cur_req_spec_desc['children'], next_req_id,
                                                                     cur_tmpl_id))
                    # Handle tree leaf.
                    else:
                        # Remove useless attributes.
                        for attr in ('identifier', 'description', 'template'):
                            if attr in cur_req_spec_desc:
                                del cur_req_spec_desc[attr]

                        if not cur_tmpl_id:
                            raise KeyError('Template is not specified for requirement "{0}"'.format(next_req_id))

                        cur_req_spec_desc['template'] = cur_tmpl_id
                        res_req_spec_descs[next_req_id] = cur_req_spec_desc

                return res_req_spec_descs
            # Handle tree root.
            # Template can be specified for all requirement specifications.
            root_tmpl_id = cur_req_spec_descs.get('template')
            exist_tmpl(root_tmpl_id, cur_req_id)
            if 'children' in cur_req_spec_descs:
                return get_req_spec_descs(cur_req_spec_descs['children'], '', root_tmpl_id)

            raise KeyError('Specifications base does not describe any requirement specifications')

        req_spec_descs = get_req_spec_descs(raw_req_spec_descs['requirement specifications'], '', None)

        # Get requirement specifications to be checked.
        check_req_spec_ids = set()
        matched_req_spec_id_patterns = set()
        for req_spec_id in req_spec_descs:
            for req_spec_id_pattern in self.conf['requirement specifications']:
                if re.search(r'^{0}$'.format(req_spec_id_pattern), req_spec_id):
                    matched_req_spec_id_patterns.add(req_spec_id_pattern)
                    check_req_spec_ids.add(req_spec_id)
                    break

        check_req_spec_ids = sorted(check_req_spec_ids)

        self.logger.debug('Following requirement specifications will be checked "%s"',
                          ', '.join(check_req_spec_ids))

        unmatched_req_spec_id_patterns = set(self.conf['requirement specifications']).difference(
            matched_req_spec_id_patterns)
        if unmatched_req_spec_id_patterns:
            raise ValueError('Following requirement specification identifier patters were not matched: "{0}"'
                             .format(', '.join(unmatched_req_spec_id_patterns)))

        # Complete descriptions of requirement specifications to be checked by adding plugin options specific for
        # requirement specifications to common template ones.
        for check_req_spec_id in check_req_spec_ids:
            check_req_spec_desc = req_spec_descs[check_req_spec_id]
            # Copy template plugin descriptions since we will overwrite them while the same template can be used by
            # different requirement specifications.
            tmpl_plugin_descs = copy.deepcopy(tmpl_descs[check_req_spec_desc['template']]['plugins'])

            check_req_spec_plugin_descs = []
            if 'plugins' in check_req_spec_desc:
                check_req_spec_plugin_descs = check_req_spec_desc['plugins']
                # Check requirement specification plugin descriptions.
                for idx, check_req_spec_plugin_desc in enumerate(check_req_spec_plugin_descs):
                    if 'name' not in check_req_spec_plugin_desc or 'options' not in check_req_spec_plugin_desc:
                        raise KeyError('Invalid description of {0} plugin of requirement specification "{1}"'
                                       .format(idx, check_req_spec_id))

            matched_req_spec_plugin_names = set()
            for tmpl_plugin_desc in tmpl_plugin_descs:
                # Template plugin description can miss specific options.
                if 'options' not in tmpl_plugin_desc:
                    tmpl_plugin_desc['options'] = {}

                for check_req_spec_plugin_desc in check_req_spec_plugin_descs:
                    if check_req_spec_plugin_desc['name'] == tmpl_plugin_desc['name']:
                        matched_req_spec_plugin_names.add(check_req_spec_plugin_desc['name'])
                        tmpl_plugin_desc['options'].update(check_req_spec_plugin_desc['options'])

            unmatched_req_spec_plugin_names = []
            for check_req_spec_plugin_desc in check_req_spec_plugin_descs:
                if check_req_spec_plugin_desc['name'] not in matched_req_spec_plugin_names:
                    unmatched_req_spec_plugin_names.append(check_req_spec_plugin_desc['name'])

            if unmatched_req_spec_plugin_names:
                raise KeyError('Following requirement specification plugins are not described within template: "{0}'
                               .format(', '.join(unmatched_req_spec_plugin_names)))

            # Add final description of requirements specification to be checked.
            self.req_spec_descs.append({
                'identifier': check_req_spec_id,
                'plugins': tmpl_plugin_descs
            })

        if self.conf['keep intermediate files']:
            self.logger.debug('Create file "%s" with descriptions of requirement specifications to be checked',
                              'checked requirement specifications.json')
            with open('checked requirement specifications.json', 'w', encoding='utf-8') as fp:
                json.dump(self.req_spec_descs, fp, ensure_ascii=False, sort_keys=True, indent=4)

    def __classify_req_spec_descs(self):
        # Determine requirement specification classes.
        # Divide classes by EMG options
        tmp_classes = {}
        for req_desc in self.req_spec_descs:
            for plugin in req_desc['plugins']:
                if plugin['name'] == 'EMG':
                    opt_cache = hashlib.sha224(str(plugin['options']).encode('UTF8')).hexdigest()
                    if opt_cache in tmp_classes:
                        tmp_classes[opt_cache].append(req_desc)
                    else:
                        tmp_classes[opt_cache] = [req_desc]
                    break
            else:
                # Strange, that there is no EMG
                tmp_classes[req_desc['identifier']] = [req_desc]

        # Replace hashes by rule names and convert lists to dictionary
        self.req_spec_classes = [{r['identifier']: r for r in rules}
                                 for rules in tmp_classes.values()]

        self.logger.info("Generated %s requirement classes from given descriptions", len(self.req_spec_classes))

    def __gradual_submit(self, items_queue, quota):
        # Because we use i for deletion we always delete the element near the end to not break order of
        # following of the rest unprocessed elements
        for i, p in reversed(list(enumerate(list(self.prepare_workers)))):
            if not p.is_alive():
                # Just remove it
                self.prepare_workers.pop(i)

        quota = min(quota, len(items_queue), self.max_worker_threads - len(self.prepare_workers))
        # It is possible, that quota < 0, when we change max_worker_threads
        submitted = max(0, quota)
        self.logger.info("Going to start %s new workers", quota)
        while 0 < quota:
            quota -= 1
            worker = items_queue.pop()
            self.prepare_workers.append(worker)
            worker.start()

        used_cores = len(self.prepare_workers)
        reserve_workers_cpu_cores(used_cores)
        self.logger.debug("Reserve %s cores for tasks preparation", used_cores)

        return submitted

    def __extract_fragments_descs(self):
        # Fetch fragment
        self.fragment_descs, attrs = self.mqs['program fragment desc'].get()
        self.mqs['program fragment desc'].close()
        self.logger.debug('Found descriptions of %s fragments', len(self.fragment_descs))

        self._report('patch',
                     {
                         'identifier': self.id,
                         'attrs': attrs
                     })

    def __generate_all_abstract_verification_task_descs(self):
        # Statuses
        waiting = 0
        prepare = []
        atask_work_dirs = {}
        atask_tasks = {}

        max_tasks = int(self.conf['max solving tasks per sub-job'])
        keep_dirs = self.conf['keep intermediate files']

        self.logger.info('Generate all abstract verification task descriptions')

        # Get abstract tasks from program fragment descriptions
        self.logger.info('Generate abstract tasks')
        for fragment in self.fragment_descs:
            if len(self.req_spec_descs) == 0:
                self.logger.warning('Program fragment %s will not be verified since requirement specifications'
                                    ' are not specified', fragment)
            else:
                for rule_class_id, _ in enumerate(self.req_spec_classes):
                    task = Abstract(fragment, rule_class_id)
                    self.logger.debug('Create abstract task %s', task)
                    identifier = "EMGW/{}/{}".format(fragment, rule_class_id)
                    workdir = os.path.join(fragment, "rule_class_{}".format(rule_class_id))
                    plugin_conf = next(iter(self.req_spec_classes[rule_class_id].values()))['plugins'][0]
                    worker = EMGW(self.conf, self.logger, self.parent_id, self.mqs, self.vals, identifier,
                                  workdir, plugin_conf, self.fragment_descs[fragment], task, self.resource_limits)
                    prepare.append(worker)

        self.logger.info('There are %s abstract tasks in total', len(prepare))

        # Get the number of abstract tasks
        left_abstract_tasks = len(prepare)
        self.logger.info('There are %s abstract tasks in total', left_abstract_tasks)
        total_tasks = 0

        # Check that we can generate a variable number of environment models
        single_model = self.conf.get('single environment model per fragment', True)
        if single_model:
            total_tasks = len(self.fragment_descs) * len([1 for cl in self.req_spec_classes for _ in cl])
            # Submit the number of tasks
            self.logger.info(
                'Submit the total number of tasks expecting a single environment model per a fragment: %s', total_tasks)
            self.mqs['total tasks'].put([self.conf['sub-job identifier'], total_tasks])

        self.logger.info('Go to the main working loop for abstract tasks')
        self.prepare_workers = []
        is_agile_threads = True
        clear_workers_cpu_cores()

        while prepare or waiting:
            self.logger.debug('Going to process %s tasks and abstract tasks and wait for %s', len(prepare), waiting)

            # Submit more work to do
            quota = (max_tasks - waiting) if max_tasks > waiting else 0
            waiting += self.__gradual_submit(prepare, quota)

            # Get processed abstract tasks.
            new_items = klever.core.utils.get_waiting_first(self.mqs['processed'], timeout=3)
            for kind, desc, *other in new_items:
                waiting -= 1
                self.logger.debug('Received item %s', kind)
                if kind == Abstract.__name__:
                    atask = Abstract(*desc)
                    left_abstract_tasks -= 1
                    models = None
                    if other:
                        aworkdir, models = other

                        if not keep_dirs:
                            atask_work_dirs[atask] = aworkdir
                            atask_tasks[atask] = set()

                    # Generate a verification task per a new environment model and rule
                    if models:
                        for env_model, workdir, envattrs in models:
                            for rule in self.req_spec_classes[atask.rule_class]:
                                new_workdir = os.path.join(workdir, rule)
                                new = Task(atask.fragment, atask.rule_class, env_model, rule, new_workdir, envattrs)
                                self.logger.debug('Create verification task %s', new)
                                if not keep_dirs:
                                    atask_tasks[atask].add(new)

                                identifier = "PLUGINS/{}/{}/{}/{}".format(atask.fragment, atask.rule_class,
                                                                          env_model, rule)
                                plugin_conf = self.req_spec_classes[atask.rule_class][rule]['plugins'][1:]
                                worker = PLUGINS(self.conf, self.logger, self.parent_id, self.mqs, self.vals,
                                                 identifier, new_workdir, plugin_conf,
                                                 self.fragment_descs[atask.fragment], new, self.resource_limits)
                                prepare.append(worker)
                                if not single_model:
                                    total_tasks += 1
                    else:
                        self.logger.warning('There is no tasks generated for %s', atask)
                        if single_model:
                            for _ in self.req_spec_classes[atask.rule_class]:
                                self.mqs['finished and failed tasks'].put((self.conf['sub-job identifier'], 'failed'))

                    if not single_model and left_abstract_tasks == 0:
                        # Submit the number of tasks
                        self.logger.info('Submit the total number of tasks: %s', total_tasks)
                        self.mqs['total tasks'].put([self.conf['sub-job identifier'], total_tasks])
                    elif not single_model:
                        self.logger.debug('Wait for abstract tasks %s', left_abstract_tasks)

                    if is_agile_threads:
                        self.max_worker_threads = klever.core.utils.get_parallel_threads_num(self.logger, self.conf,
                                                                                             'Plugins')
                        is_agile_threads = False
                        self.logger.info("Change number of workers to %s", self.max_worker_threads)
                else:
                    task = Task(*desc)

                    # Check solution
                    if other:
                        self.logger.info('Received solution for %s', task)
                        status = 'finished'
                    else:
                        self.logger.info('No solution received for %s', task)
                        status = 'failed'

                    # Send status to the progress watcher
                    self.mqs['finished and failed tasks'].put((self.conf['sub-job identifier'], status))

                    # Delete abstract task working directory (with EMG dir)
                    if not keep_dirs:
                        self.logger.debug('Delete task working directory %s', task.workdir)
                        klever.core.utils.reliable_rmtree(self.logger, task.workdir)

                        atask = Abstract(task.fragment, task.rule_class)
                        atask_tasks[atask].remove(task)
                        if not atask_tasks[atask]:
                            self.logger.debug('Delete working directories related to %s: %s',
                                              atask, atask_work_dirs[atask])
                            klever.core.utils.reliable_rmtree(self.logger, atask_work_dirs[atask])
                            del atask_tasks[atask]
                            del atask_work_dirs[atask]

        clear_workers_cpu_cores()
        # Close the queue
        self.mqs['processed'].close()

        self.logger.info("Stop generating verification tasks")


class VTGW(klever.core.components.Component):

    def __init__(self, conf, logger, parent_id, mqs, vals, cur_id, work_dir, plugin_conf,
                 fragment_desc, task, resource_limits):
        super().__init__(conf, logger, parent_id, mqs, vals, cur_id, work_dir, [], True)
        self.initial_abstract_task_desc_file = 'initial abstract task.json'
        self.out_abstract_task_desc_file = 'abstract tasks.json'
        self.final_abstract_task_desc_file = 'final abstract task.json'

        # Get tuple and convert it back
        self.task = task
        self.resource_limits = resource_limits
        self.plugins_conf = plugin_conf

        self.fragment_desc = fragment_desc
        self.prepared_tasks = []

    def tasks_generator_worker(self):
        self._submit_attrs()
        self._generate_abstract_verification_task_desc()
        if not self.vals['task solving flag'].value:
            with self.vals['task solving flag'].get_lock():
                self.vals['task solving flag'].value = 1

    main = tasks_generator_worker

    def _generate_abstract_verification_task_desc(self):
        # Implement the method to do the workload
        pass

    def _run_plugin(self, plugin_desc, abstract_task_desc):
        plugin_name = plugin_desc['name']
        plugin_work_dir = plugin_desc['name'].lower()
        plugin_conf = copy.deepcopy(plugin_desc['options'])
        plugin_conf_file = f'{plugin_name.lower()} conf.json'

        self.logger.info('Launch plugin %s', plugin_name)
        if 'options' in plugin_desc:
            plugin_conf.update(self.conf)

        # Get plugin configuration on the basis of common configuration, plugin options specific for requirement
        # specification and information on requirement itself. In addition put either initial or
        # current description of abstract verification task into plugin configuration.
        self.dump_if_necessary(plugin_conf_file, plugin_conf, "configuration of plugin {}".format(plugin_name))

        plugin = getattr(importlib.import_module(f'.{plugin_name.lower()}', 'klever.core.vtg'), plugin_name)
        p = plugin(plugin_conf, self.logger, self.id, self.mqs, self.vals, abstract_task_desc,
                   plugin_name, plugin_work_dir,
                   # Weaver can execute workers in parallel but it does not launch any heavyweight subprocesses for
                   # which it is necessary to include child resources. These workers can execute time consuming CIF and
                   # appropriate resources are dumped to directory "child resources" and after all they are taken into
                   # account when calculating Weaver resources since we wouldn't like to separately show resources
                   # consumed by workers. Moreover, we even wouldn't like to execute them in separate working
                   # directories like sub-jobs to simplify the workflow and debugging.
                   include_child_resources=plugin_name != 'Weaver')
        if not os.path.isdir(plugin_work_dir):
            self.logger.info(
                'Create working directory "%s" for component "%s"', plugin_work_dir, plugin_name)
            os.makedirs(plugin_work_dir.encode('utf-8'))

        p.run()

        return p.abstract_task_desc

    def plugin_fail_processing(self):
        self.logger.debug('Submit the information about the failure to the Job processing class')
        data = type(self.task).__name__, tuple(self.task)
        self.mqs['processed'].put(data)
        if 'verification statuses' in self.mqs:
            self.mqs['verification statuses'].put({
                'program fragment id': self.task.fragment,
                'req spec id': self.task.rule if hasattr(self.task, 'rule') else self.task.rule_class,
                'environment model': self.task.envmodel if hasattr(self.task, 'envmodel') else 'base',
                'verdict': 'non-verifier unknown',
                'sub-job identifier': self.conf['sub-job identifier'],
                'ideal verdicts': self.conf['ideal verdicts'],
                'data': self.conf.get('data')
            })

    def _submit_attrs(self):
        # Prepare program fragment description file
        files_list_file = 'files list.txt'
        klever.core.utils.save_program_fragment_description(self.fragment_desc, files_list_file)

        # Add attributes
        self.attrs.extend(
            [
                {
                    "name": "Program fragment",
                    "value": self.task.fragment,
                    "data": files_list_file,
                    "compare": True
                },
                {
                    "name": "Requirements specification class",
                    "value": str(self.task.rule_class)
                }
            ]
        )

        # Send attributes to the Bridge
        self._report('patch',
                     {
                         'identifier': self.id,
                         'attrs': self.attrs
                     },
                     data_files=[files_list_file])


class EMGW(VTGW):

    def _send_prepared_data(self):
        # Send tasks to the VTG
        if self.prepared_tasks:
            self.logger.info('Found %s generated tasks', len(self.prepared_tasks))
        else:
            self.logger.info('There is no environment models generated for %s', self.task)

        triples = []
        # Generate task descriptions for further tasks
        for task_desc in self.prepared_tasks:
            env_path = task_desc.get("environment model pathname")
            env_attrs = tuple(sorted(task_desc.get("environment model attributes", {}).items(), key=lambda x: x[0]))
            task_workdir = os.path.join(self.work_dir, env_path)
            os.makedirs(env_path, exist_ok=True)
            task_file = os.path.join(env_path, self.initial_abstract_task_desc_file)
            with open(task_file, 'w', encoding='utf-8') as handle:
                klever.core.utils.json_dump(task_desc, handle, self.conf['keep intermediate files'])
            triples.append([env_path, task_workdir, env_attrs])

        # Submit new tasks to the VTG
        prepared_data = type(self.task).__name__, tuple(self.task), self.work_dir, triples

        self.logger.info("Now send the data to the VTG for %s", self.task)
        self.mqs['processed'].put(prepared_data)

    def _generate_abstract_verification_task_desc(self):
        fragment = self.task.fragment
        rule_class = self.task.rule_class

        self.logger.info("Start generating tasks for %s and requirements specification %s", fragment, rule_class)
        cur_abstract_task_desc = self.__prepare_initial_abstract_task(fragment, rule_class)

        # Update resource limits
        soft_time, hard_time = resource.getrlimit(resource.RLIMIT_CPU)
        soft_mem, hard_mem = resource.getrlimit(resource.RLIMIT_AS)
        cpu_time_limit = self.conf["resource limits"]["CPU time for EMG"]
        memory_limit = self.conf["resource limits"]["memory size for EMG"]
        self.logger.debug(
            'Got the following limitations for EMG: CPU time = %ss, '
            'memory = %sB', cpu_time_limit, memory_limit
        )
        resource.prlimit(0, resource.RLIMIT_CPU, (cpu_time_limit, hard_time))
        resource.prlimit(0, resource.RLIMIT_AS, (memory_limit, hard_mem))

        # Here plugin will put modified abstract verification task description.
        try:
            self.prepared_tasks = self._run_plugin(self.plugins_conf, cur_abstract_task_desc)
            self.dump_if_necessary(self.out_abstract_task_desc_file, self.prepared_tasks,
                                   "modified abstract verification task description")
            # If we send it later, in case of failure the data is sent twice:
            # in _send_prepared_data() and in plugin_fail_processing()
            self._send_prepared_data()
        except klever.core.components.ComponentError:
            self.logger.warning('EMG has failed')
            self.plugin_fail_processing()

        # Restore limitations
        resource.prlimit(0, resource.RLIMIT_CPU, (soft_time, hard_time))
        resource.prlimit(0, resource.RLIMIT_AS, (soft_mem, hard_mem))

    def __prepare_initial_abstract_task(self, fragment, rule_class):
        # Initial abstract verification task looks like corresponding program fragment.
        initial_abstract_task_desc = copy.deepcopy(self.fragment_desc)
        initial_abstract_task_desc['id'] = '{0}/{1}'.format(fragment, rule_class)
        initial_abstract_task_desc['attrs'] = ()

        self.dump_if_necessary(self.initial_abstract_task_desc_file, initial_abstract_task_desc,
                               "initial abstract verification task description")

        return initial_abstract_task_desc


class PLUGINS(VTGW):

    def _submit_attrs(self):
        self.attrs.append(
            {
                "name": "Requirements specification",
                "value": self.task.rule,
                "compare": True
            }
        )
        if self.task.envattrs:
            for entry, value in self.task.envattrs:
                if value:
                    self.attrs.append(
                        {
                            "name": f"Environment model '{entry}'",
                            "value": value,
                            "compare": True
                        }
                    )
        super()._submit_attrs()

    def _prepare_initial_task_desc(self):
        initial_abstract_task_desc_file = os.path.join(os.path.pardir, self.initial_abstract_task_desc_file)
        # Initial abstract verification task looks like corresponding program fragment.
        with open(initial_abstract_task_desc_file, 'r', encoding='utf-8') as fp:
            initial_abstract_task_desc = json.load(fp)
        initial_abstract_task_desc['id'] = '/'.join((self.task.fragment, str(self.task.rule_class), self.task.envmodel,
                                                     self.task.rule))

        self.dump_if_necessary(self.initial_abstract_task_desc_file, initial_abstract_task_desc,
                               "initial abstract verification task description")

        return initial_abstract_task_desc

    def _submit_task(self, plugin_desc, final_task_data):
        plugin_work_dir = plugin_desc['name'].lower()

        self.dump_if_necessary(self.final_abstract_task_desc_file, final_task_data,
                               "abstract verification task description")

        # VTG will consume this abstract verification task description file.
        if os.path.isfile(os.path.join(plugin_work_dir, 'task.json')) and \
                os.path.isfile(os.path.join(plugin_work_dir, 'task files.zip')):
            session = klever.core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])
            task_id = session.schedule_task(os.path.join(plugin_work_dir, 'task.json'),
                                            os.path.join(plugin_work_dir, 'task files.zip'))

            # Plan for checking status
            self.mqs['pending tasks'].put(
                [str(task_id), tuple(self.task), final_task_data["result processing"], self.fragment_desc,
                 final_task_data['verifier'], final_task_data['additional sources'],
                 final_task_data['verification task files']])

            self.logger.info("Submitted successfully verification task %s for solution",
                             os.path.join(plugin_work_dir, 'task.json'))
        else:
            self.logger.warning("There is no verification task generated by the last plugin, expect %s",
                                os.path.join(plugin_work_dir, 'task.json'))

    def _generate_abstract_verification_task_desc(self):
        # Prepare initial task desc
        self.logger.info("Start generating tasks for %s", self.task)
        cur_abstract_task_desc = self._prepare_initial_task_desc()

        # Invoke all plugins one by one.
        for plugin_desc in self.plugins_conf:
            plugin_desc.get('options', {}).update({
                'solution class': self.task.rule,
                'override resource limits': self.resource_limits
            })

            try:
                cur_abstract_task_desc = self._run_plugin(plugin_desc, cur_abstract_task_desc)

                out_abstract_task_desc_file = '{0} abstract task.json'.format(plugin_desc['name'].lower())
                out_abstract_task_desc_file = os.path.relpath(
                    os.path.join(os.path.pardir, out_abstract_task_desc_file))

                self.dump_if_necessary(out_abstract_task_desc_file, cur_abstract_task_desc,
                                       "modified abstract verification task description")
            except klever.core.components.ComponentError:
                self.logger.warning('Plugin %s failed', plugin_desc['name'])

                # Call the job hook
                self.plugin_fail_processing()
                break
        else:
            self._submit_task(plugin_desc, cur_abstract_task_desc)
