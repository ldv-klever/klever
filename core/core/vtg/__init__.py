#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

import importlib
import json
import multiprocessing
import os
import re
import copy
import hashlib
import time

import core.components
import core.utils
import core.session

from core.vtg.scheduling import Balancer


@core.components.before_callback
def __launch_sub_job_components(context):
    context.mqs['VTG common prj attrs'] = multiprocessing.Queue()
    context.mqs['pending tasks'] = multiprocessing.Queue()
    context.mqs['processed tasks'] = multiprocessing.Queue()
    context.mqs['prepared verification tasks'] = multiprocessing.Queue()
    context.mqs['prepare program fragments'] = multiprocessing.Queue()
    context.mqs['processing tasks'] = multiprocessing.Queue()
    context.mqs['program fragment desc files'] = multiprocessing.Queue()


@core.components.after_callback
def __prepare_descriptions_file(context):
    context.mqs['program fragment desc files'].put(
        os.path.relpath(context.PF_FILE, context.conf['main working directory']))


@core.components.after_callback
def __submit_project_attrs(context):
    context.mqs['VTG common prj attrs'].put(context.common_prj_attrs)


def _extract_template_plugin_descs(logger, tmpl_descs):
    for tmpl_id, tmpl_desc in tmpl_descs.items():
        logger.info('Extract options for plugins of template "{0}"'.format(tmpl_id))

        if 'plugins' not in tmpl_desc:
            raise ValueError('Template "{0}" has not mandatory attribute "plugins"'.format(tmpl_id))

        for idx, plugin_desc in enumerate(tmpl_desc['plugins']):
            if not isinstance(plugin_desc, dict) or 'name' not in plugin_desc:
                raise ValueError('Description of template "{0}" plugin "{1}" has incorrect format'.format(tmpl_id, idx))

        logger.debug(
            'Template "{0}" plugins are "{1}"'.format(tmpl_id,
                                                      [plugin_desc['name'] for plugin_desc in tmpl_desc['plugins']]))

        # Get options for plugins specified in base template and merge them with the ones extracted above.
        if 'template' in tmpl_desc:
            if tmpl_desc['template'] not in tmpl_descs:
                raise ValueError(
                    'Template "{0}" of template "{1}" could not be found in specifications base'
                    .format(tmpl_desc['template'], tmpl_id))

            logger.debug('Template "{0}" template is "{1}"'.format(tmpl_id, tmpl_desc['template']))

            for plugin_desc in tmpl_desc['plugins']:
                for base_tmpl_plugin_desc in tmpl_descs[tmpl_desc['template']]['plugins']:
                    if plugin_desc['name'] == base_tmpl_plugin_desc['name']:
                        if 'options' in base_tmpl_plugin_desc:
                            if 'options' in plugin_desc:
                                plugin_desc['options'] = core.utils.merge_confs(base_tmpl_plugin_desc['options'],
                                                                                plugin_desc['options'])
                            else:
                                plugin_desc['options'] = base_tmpl_plugin_desc['options']


# TODO: support inheritance of template sequences, i.e. when requirement needs template that is template of another one.
# This function is invoked to collect plugin callbacks.
def _extract_req_spec_descs(conf, logger):
    logger.info('Extract requirement specificaction decriptions')

    if 'specifications base' not in conf:
        raise KeyError('Nothing will be verified since specifications base is not specified')

    if 'requirement specifications' not in conf:
        raise KeyError('Nothing will be verified since requirement specifications to be checked are not specified')

    # Read specifications base.
    with open(conf['specifications base'], encoding='utf8') as fp:
        raw_req_spec_descs = json.load(fp)

    if 'templates' not in raw_req_spec_descs:
        raise KeyError('Specifications base has not mandatory attribute "templates"')

    if 'requirement specifications' not in raw_req_spec_descs:
        raise KeyError('Specifications base has not mandatory attribute "requirement specifications"')

    tmpl_descs = raw_req_spec_descs['templates']
    _extract_template_plugin_descs(logger, tmpl_descs)

    def exist_tmpl(tmpl_id, cur_req_id):
        if tmpl_id and tmpl_id not in tmpl_descs:
            raise KeyError('Template "{0}" for "{1}" is not described'.format(tmpl_id, cur_req_id))

    # Get identifiers, template identifiers and plugin options for all requirement specifications.
    def get_req_spec_descs(cur_req_spec_descs, cur_req_id, parent_tmpl_id):
        # Requirement specifications are described as a tree where leaves correspond to individual requirement
        # specifications while intermediate nodes hold common parts of requirement specification identifiers, optional
        # template identifiers and optional descriptions.
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
        else:
            # Template can be specified for all requirement specifications.
            root_tmpl_id = cur_req_spec_descs.get('template')
            exist_tmpl(root_tmpl_id, cur_req_id)
            if 'children' in cur_req_spec_descs:
                return get_req_spec_descs(cur_req_spec_descs['children'], '', root_tmpl_id)
            else:
                raise KeyError('Specifications base does not describe any requirement specifications')

    req_spec_descs = get_req_spec_descs(raw_req_spec_descs['requirement specifications'], '', None)

    # Get requirement specifications to be checked.
    check_req_spec_ids = set()
    matched_req_spec_id_patterns = set()
    for req_spec_id in req_spec_descs:
        for req_spec_id_pattern in conf['requirement specifications']:
            if re.search(r'^{0}$'.format(req_spec_id_pattern), req_spec_id):
                matched_req_spec_id_patterns.add(req_spec_id_pattern)
                check_req_spec_ids.add(req_spec_id)
                break

    check_req_spec_ids = sorted(check_req_spec_ids)

    logger.debug('Following requirement specifications will be checked "{0}"'.format(', '.join(check_req_spec_ids)))

    unmatched_req_spec_id_patterns = set(conf['requirement specifications']).difference(matched_req_spec_id_patterns)
    if unmatched_req_spec_id_patterns:
        # TODO: make this warning more visible (note).
        logger.warning('Following requirement specification identifier patters were not matched: "{0}'
                       .format(', '.join(unmatched_req_spec_id_patterns)))

    # Complete descriptions of requirement specifications to be checked by adding plugin options specific for
    # requirement specifications to common template ones.
    check_req_spec_descs = []
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
        check_req_spec_descs.append({
            'identifier': check_req_spec_id,
            'plugins': tmpl_plugin_descs
        })

    if conf['keep intermediate files']:
        logger.debug('Create file "{0}" with descriptions of requirement specifications to be checked'
                     .format('checked requirement specifications.json'))
        with open('checked requirement specifications.json', 'w', encoding='utf8') as fp:
            json.dump(check_req_spec_descs, fp, ensure_ascii=False, sort_keys=True, indent=4)

    return check_req_spec_descs


def _classify_req_spec_descs(logger, req_spec_descs):
    # Determine requirement specification classes.
    req_spec_classes = {}
    for req_desc in req_spec_descs:
        hashes = dict()
        for plugin in (p for p in req_desc['plugins'] if p['name'] in ['SA', 'EMG']):
            hashes[plugin['name']] = plugin['options']

        if len(hashes) > 0:
            opt_cache = hashlib.sha224(str(hashes).encode('UTF8')).hexdigest()
            if opt_cache in req_spec_classes:
                req_spec_classes[opt_cache].append(req_desc)
            else:
                req_spec_classes[opt_cache] = [req_desc]
        else:
            req_spec_classes[req_desc['identifier']] = [req_desc]

    logger.info("Generated {} requirement classes from given descriptions".format(len(req_spec_classes)))

    return req_spec_classes


_req_spec_descs = None
_req_spec_classes = None


@core.components.propogate_callbacks
def collect_plugin_callbacks(conf, logger):
    logger.info('Get VTG plugin callbacks')

    global _req_spec_descs, _req_spec_classes
    _req_spec_descs = _extract_req_spec_descs(conf, logger)
    _req_spec_classes = _classify_req_spec_descs(logger, _req_spec_descs)
    plugins = []

    # Find appropriate classes for plugins if so.
    for req_spec_desc in _req_spec_descs:
        for plugin_desc in req_spec_desc['plugins']:
            logger.info('Load plugin "{0}"'.format(plugin_desc['name']))
            try:
                plugin = getattr(importlib.import_module('.{0}'.format(plugin_desc['name'].lower()), 'core.vtg'),
                                 plugin_desc['name'])
                # Remember found class to create its instance during main operation.
                plugin_desc['plugin'] = plugin
                if plugin not in plugins:
                    plugins.append(plugin)
            except ImportError:
                raise NotImplementedError('Plugin {0} is not supported'.format(plugin_desc['name']))

    return core.components.get_component_callbacks(logger, plugins, conf)


def resolve_req_spec_class(name):
    global _req_spec_classes

    if len(_req_spec_classes) > 0:
        rc = [identifier for identifier in _req_spec_classes if name in
              [r['identifier'] for r in _req_spec_classes[identifier]]][0]
    else:
        rc = None

    return rc


class VTG(core.components.Component):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False):
        super(VTG, self).__init__(conf, logger, parent_id, callbacks, mqs, vals, id, work_dir, attrs,
                                  separate_from_parent, include_child_resources)
        self.model_headers = {}
        self.req_spec_descs = None

    def generate_verification_tasks(self):
        self.req_spec_descs = _req_spec_descs
        core.utils.report(self.logger,
                          'patch',
                          {
                              'identifier': self.id,
                              'attrs': self.__get_common_prj_attrs()
                          },
                          self.mqs['report files'],
                          self.vals['report id'],
                          self.conf['main working directory'])

        # Start plugins
        if not self.conf['keep intermediate files']:
            self.mqs['delete dir'] = multiprocessing.Queue()
        subcomponents = [('AAVTDG', self.__generate_all_abstract_verification_task_descs), VTGWL]
        self.launch_subcomponents(False, *subcomponents)

        self.clean_dir = True

        self.mqs['pending tasks'].put(None)
        self.mqs['pending tasks'].close()

    main = generate_verification_tasks

    def __generate_all_abstract_verification_task_descs(self):
        self.logger.info('Generate all abstract verification task decriptions')

        # Fetch fragment
        pf_file = self.mqs['program fragment desc files'].get()
        pf_file = os.path.join(self.conf['main working directory'], pf_file)
        self.mqs['program fragment desc files'].close()

        if os.path.isfile(pf_file):
            with open(pf_file, 'r', encoding='utf8') as fp:
                program_fragment_desc_files = \
                    [os.path.join(self.conf['main working directory'], pf_file.strip()) for pf_file in fp.readlines()]
            if not self.conf['keep intermediate files']:
                os.remove(pf_file)
        else:
            raise FileNotFoundError

        # Drop a line to a progress watcher
        total_pf_descs = len(program_fragment_desc_files)
        self.mqs['total tasks'].put([self.conf['sub-job identifier'],
                                     int(total_pf_descs * len(self.req_spec_descs))])

        pf_descriptions = dict()
        initial = dict()

        # Fetch fragment
        for program_fragment_desc_file in program_fragment_desc_files:
            with open(os.path.join(self.conf['main working directory'], program_fragment_desc_file),
                      encoding='utf8') as fp:
                program_fragment_desc = json.load(fp)

            if not self.conf['keep intermediate files']:
                os.remove(os.path.join(self.conf['main working directory'], program_fragment_desc_file))

            if len(self.req_spec_descs) == 0:
                self.logger.warning('Program fragment {0} will not be verified since requirement specifications'
                                    ' are not specified'.format(program_fragment_desc['id']))
            else:
                pf_descriptions[program_fragment_desc['id']] = program_fragment_desc
                initial[program_fragment_desc['id']] = list(_req_spec_classes.keys())

        processing_status = dict()
        delete_ready = dict()
        balancer = Balancer(self.conf, self.logger, processing_status)

        def submit_task(pf, rlcl, rlda, rescheduling=False):
            resource_limitations = balancer.resource_limitations(pf['id'], rlcl, rlda['identifier'])
            self.mqs['prepare program fragments'].put((pf, rlda, resource_limitations, rescheduling))

        max_tasks = int(self.conf['max solving tasks per sub-job'])
        active_tasks = 0
        while True:
            # Fetch pilot statuses
            pilot_statuses = []
            # This queue will not inform about the end of tasks generation
            core.utils.drain_queue(pilot_statuses, self.mqs['prepared verification tasks'])
            # Process them
            for status in pilot_statuses:
                program_fragment_id, req_spec_id= status
                self.logger.info(
                    "Pilot verification task for program fragment {!r} and requirements specification {!r} is prepared".
                    format(program_fragment_id, req_spec_id))
                req_spec_class = resolve_req_spec_class(req_spec_id)
                if req_spec_class:
                    if program_fragment_id in processing_status and \
                            req_spec_class in processing_status[program_fragment_id] and \
                            req_spec_id in processing_status[program_fragment_id][req_spec_class]:
                        processing_status[program_fragment_id][req_spec_class][req_spec_id] = False
                else:
                    self.logger.warning("Do nothing with {} since there is no requirement specifications to check"
                                        .format(program_fragment_id))

            # Fetch solutions
            solutions = []
            # This queue will not inform about the end of tasks generation
            core.utils.drain_queue(solutions, self.mqs['processed tasks'])

            if not self.conf['keep intermediate files']:
                ready = []
                core.utils.drain_queue(ready, self.mqs['delete dir'])
                while len(ready) > 0:
                    pf, req_spec_desc = ready.pop()
                    if pf not in delete_ready:
                        delete_ready[pf] = {req_spec_desc}
                    else:
                        delete_ready[pf].add(req_spec_desc)

            # Process them
            for solution in solutions:
                program_fragment_id, req_spec_id, status_info = solution
                self.logger.info("Verification task for program fragment {!r} and requirements specification {!r}"
                                 " is either finished or failed".format(program_fragment_id, req_spec_id))
                req_spec_class = resolve_req_spec_class(req_spec_id)
                if req_spec_class:
                    final = balancer.add_solution(program_fragment_id, req_spec_class, req_spec_id, status_info)
                    if final:
                        self.logger.debug('Confirm that task {!r}:{!r} is {!r}'.
                                          format(program_fragment_id, req_spec_id, status_info[0]))
                        self.mqs['finished and failed tasks'].put([self.conf['sub-job identifier'], 'finished'
                                                                  if status_info[0] == 'finished' else 'failed'])
                        processing_status[program_fragment_id][req_spec_class][req_spec_id] = True
                    active_tasks -= 1

            # Submit initial fragments
            for pf in list(initial.keys()):
                while len(initial[pf]) > 0:
                    if active_tasks < max_tasks:
                        req_spec_class = initial[pf].pop()
                        program_fragment_id = pf_descriptions[pf]
                        req_spec_id = _req_spec_classes[req_spec_class][0]['identifier']
                        self.logger.info("Prepare initial verification tasks for program fragement {!r} and"
                                         " requirements specification {!r}".format(pf, req_spec_id))
                        submit_task(program_fragment_id, req_spec_class, _req_spec_classes[req_spec_class][0])

                        # Set status
                        if pf not in processing_status:
                            processing_status[pf] = {}
                        processing_status[pf][req_spec_class] = {req_spec_id: None}
                        active_tasks += 1
                    else:
                        break
                else:
                    self.logger.info("Triggered all initial tasks for program fragment {!r}".format(pf))
                    del initial[pf]

            # Check statuses
            for program_fragment_id in list(processing_status.keys()):
                for req_spec_class in list(processing_status[program_fragment_id].keys()):
                    # Check readiness for further tasks generation
                    pilot_task_status = processing_status[program_fragment_id][req_spec_class][_req_spec_classes[
                        req_spec_class][0]['identifier']]
                    if (pilot_task_status is False or pilot_task_status is True) and active_tasks < max_tasks:
                        for req_spec_desc in [req_spec_desc for req_spec_desc in _req_spec_classes[req_spec_class][1:]
                                              if req_spec_desc['identifier'] not in
                                                 processing_status[program_fragment_id][req_spec_class]]:
                            if active_tasks < max_tasks:
                                self.logger.info("Submit next verification task after having cached plugin results for "
                                                 "program fragment {!r} and requirements specification {!r}".
                                                 format(program_fragment_id, req_spec_desc['identifier']))
                                submit_task(pf_descriptions[program_fragment_id], req_spec_class, req_spec_desc)
                                processing_status[program_fragment_id][req_spec_class][
                                    req_spec_desc['identifier']] = None
                                active_tasks += 1
                            else:
                                break

                    # Check that we should reschedule tasks
                    for req_spec_desc in (r for r in _req_spec_classes[req_spec_class] if
                                          r['identifier'] in processing_status[program_fragment_id][req_spec_class] and
                                          not processing_status[program_fragment_id][req_spec_class][r['identifier']] and
                                          balancer.is_there(program_fragment_id, req_spec_class, r['identifier'])):
                        if active_tasks < max_tasks:
                            attempt = balancer.do_rescheduling(program_fragment_id, req_spec_class,
                                                               req_spec_desc['identifier'])
                            if attempt:
                                self.logger.info("Submit task {}:{} to solve it again".
                                                 format(program_fragment_id, req_spec_desc['id']))
                                submit_task(pf_descriptions[program_fragment_id], req_spec_class, req_spec_desc,
                                            rescheduling=attempt)
                                active_tasks += 1
                            elif not balancer.need_rescheduling(program_fragment_id, req_spec_class,
                                                                req_spec_desc['identifier']):
                                self.logger.info("Mark task {}:{} as solved".format(program_fragment_id,
                                                                                    req_spec_desc['identifier']))
                                self.mqs['finished and failed tasks'].put([self.conf['sub-job identifier'], 'finished'])
                                processing_status[program_fragment_id][req_spec_class][
                                    req_spec_desc['identifier']] = True

                    # Number of solved tasks
                    solved = sum((1 if processing_status[program_fragment_id][req_spec_class].get(r['identifier'])
                                  else 0 for r in _req_spec_classes[req_spec_class]))
                    # Number of requirements which are ready to delete
                    deletable = len([r for r in processing_status[program_fragment_id][req_spec_class]
                                     if program_fragment_id in delete_ready and r in delete_ready[program_fragment_id]])
                    # Total tasks for requirements
                    total = len(_req_spec_classes[req_spec_class])

                    if solved == total and (self.conf['keep intermediate files'] or
                                            (program_fragment_id in delete_ready and solved == deletable)):
                        self.logger.debug("Solved {} tasks for program fragment {!r}"
                                          .format(solved, program_fragment_id))
                        if not self.conf['keep intermediate files']:
                            for req_spec_desc in processing_status[program_fragment_id][req_spec_class]:
                                deldir = os.path.join(program_fragment_id, req_spec_desc)
                                core.utils.reliable_rmtree(self.logger, deldir)
                        del processing_status[program_fragment_id][req_spec_class]

                if len(processing_status[program_fragment_id]) == 0 and program_fragment_id not in initial:
                    self.logger.info("All tasks for program fragment {!r} are either solved or failed".
                                     format(program_fragment_id))
                    # Program fragments is lastly processed
                    del processing_status[program_fragment_id]
                    del pf_descriptions[program_fragment_id]
                    if program_fragment_id in delete_ready:
                        del delete_ready[program_fragment_id]

            if active_tasks == 0 and len(pf_descriptions) == 0 and len(initial) == 0:
                self.mqs['prepare program fragments'].put(None)
                self.mqs['prepared verification tasks'].close()
                if not self.conf['keep intermediate files']:
                    self.mqs['delete dir'].close()
                break
            else:
                self.logger.debug("There are {} initial tasks to be generated, {} active tasks, {} program fragment "
                                  "descriptions".format(len(initial), active_tasks, len(pf_descriptions)))

            time.sleep(3)

        self.logger.info("Stop generating verification tasks")

    def __get_common_prj_attrs(self):
        self.logger.info('Get common project atributes')
        common_prj_attrs = self.mqs['VTG common prj attrs'].get()
        self.mqs['VTG common prj attrs'].close()
        return common_prj_attrs


class VTGWL(core.components.Component):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False):
        super(VTGWL, self).__init__(conf, logger, parent_id, callbacks, mqs, vals, id, work_dir, attrs,
                                    separate_from_parent, include_child_resources)

    def task_generating_loop(self):
        self.logger.info("Start VTGL worker")
        number = core.utils.get_parallel_threads_num(self.logger, self.conf, 'Tasks generation')
        core.components.launch_queue_workers(self.logger, self.mqs['prepare program fragments'],
                                             self.vtgw_constructor, number, True)
        self.logger.info("Terminate VTGL worker")

    def vtgw_constructor(self, element):
        program_fragment_id = element[0]['id']
        req_spec_id = element[1]['identifier']

        attrs = None
        if element[3]:
            identifier = "{}/{}/{}/VTGW".format(program_fragment_id, req_spec_id, element[3])
            workdir = os.path.join(program_fragment_id, req_spec_id, str(element[3]))
            attrs = [{
                "name": "Rescheduling attempt",
                "value": str(element[3]),
                "compare": False,
                "associate": False
            }]
        else:
            identifier = "{}/{}/VTGW".format(program_fragment_id, req_spec_id)
            workdir = os.path.join(program_fragment_id, req_spec_id)

        return VTGW(self.conf, self.logger, self.parent_id, self.callbacks, self.mqs,
                    self.vals, identifier, workdir,
                    attrs=attrs, separate_from_parent=True, program_fragment_desc=element[0], req_spec_desc=element[1],
                    resource_limits=element[2], rerun=element[3])

    main = task_generating_loop


class VTGW(core.components.Component):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False, program_fragment_desc=None,
                 req_spec_desc=None, resource_limits=None, rerun=False):
        super(VTGW, self).__init__(conf, logger, parent_id, callbacks, mqs, vals, id, work_dir, attrs,
                                   separate_from_parent, include_child_resources)
        self.program_fragment_desc = program_fragment_desc
        self.program_fragment_id = program_fragment_desc['id']
        self.req_spec_desc = req_spec_desc
        self.req_spec_id = req_spec_desc['identifier']
        self.abstract_task_desc_file = None
        self.override_limits = resource_limits
        self.rerun = rerun
        self.session = core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])

    def tasks_generator_worker(self):
        files_list_file = 'files list.txt'
        with open(files_list_file, 'w', encoding='utf8') as fp:
            fp.writelines('\n'.join(sorted(f for grp in self.program_fragment_desc['grps'] for f in grp['files'])))
        core.utils.report(self.logger,
                          'patch',
                          {
                              'identifier': self.id,
                              'attrs': [
                                  {
                                      "name": "Program fragment",
                                      "value": self.program_fragment_id,
                                      "data": files_list_file
                                  },
                                  {
                                      "name": "Requirements specification",
                                      "value": self.req_spec_id
                                  },
                                  {
                                      "name": "Size",
                                      "value": self.program_fragment_desc['size']
                                  }
                              ]
                          },
                          self.mqs['report files'],
                          self.vals['report id'],
                          self.conf['main working directory'],
                          data_files=[files_list_file])

        try:
            self.generate_abstact_verification_task_desc(self.program_fragment_desc, self.req_spec_desc)
            if not self.vals['task solving flag'].value:
                with self.vals['task solving flag'].get_lock():
                    self.vals['task solving flag'].value = 1
        except Exception:
            self.plugin_fail_processing()
            raise
        finally:
            self.session.sign_out()

    main = tasks_generator_worker

    def generate_abstact_verification_task_desc(self, program_fragment_desc, req_spec_desc):
        """Has a callback!"""
        self.logger.info("Start generating tasks for program fragment {!r} and requirements specification {!r}".
                         format(self.program_fragment_id, self.req_spec_id))

        # Prepare pilot workdirs if it will be possible to reuse data
        req_spec_class = resolve_req_spec_class(self.req_spec_id)
        pilot_req_spec_id = _req_spec_classes[req_spec_class][0]['identifier']
        pilot_plugins_work_dir = os.path.join(os.path.pardir, pilot_req_spec_id)

        # Initial abstract verification task looks like corresponding program fragment.
        initial_abstract_task_desc = copy.deepcopy(program_fragment_desc)
        initial_abstract_task_desc['id'] = '{0}/{1}'.format(self.program_fragment_id, self.req_spec_id)
        initial_abstract_task_desc['attrs'] = ()

        initial_abstract_task_desc_file = 'initial abstract task.json'
        self.logger.debug(
            'Put initial abstract verification task description to file "{0}"'.format(
                initial_abstract_task_desc_file))
        with open(initial_abstract_task_desc_file, 'w', encoding='utf8') as fp:
            core.utils.json_dump(initial_abstract_task_desc, fp, self.conf['keep intermediate files'])

        # Invoke all plugins one by one.
        cur_abstract_task_desc_file = initial_abstract_task_desc_file
        out_abstract_task_desc_file = None
        if self.rerun:
            # Get only the last, and note that the last one prepares tasks and otherwise rerun should not be set
            plugins = [req_spec_desc['plugins'][-1]]
        else:
            plugins = req_spec_desc['plugins']

        for plugin_desc in plugins:
            # Here plugin will put modified abstract verification task description.
            plugin_work_dir = plugin_desc['name'].lower()
            out_abstract_task_desc_file = '{0} abstract task.json'.format(plugin_desc['name'].lower())
            if self.rerun:
                self.logger.info("Instead of running the {!r} plugin for requirements pecification {!r} obtain "
                                 "results for the original run".format(plugin_desc['name'], self.req_spec_id))
                cur_abstract_task_desc_file = os.path.join(os.pardir, out_abstract_task_desc_file)
                os.symlink(os.path.relpath(cur_abstract_task_desc_file, os.path.curdir),
                           out_abstract_task_desc_file)

            if self.req_spec_id not in [c[0]['identifier'] for c in _req_spec_classes.values()] and \
                    plugin_desc['name'] in ['SA', 'EMG']:
                # Expect that there is a work directory which has all prepared
                # Make symlinks to the pilot requirement work dir
                self.logger.info("Instead of running the {!r} plugin for the {!r} requirement lets use already obtained"
                                 " results for the {!r} requirement".format(plugin_desc['name'], self.req_spec_id,
                                                                            pilot_req_spec_id))
                pilot_plugin_work_dir = os.path.join(pilot_plugins_work_dir, plugin_desc['name'].lower())
                pilot_abstract_task_desc_file = os.path.join(
                    pilot_plugins_work_dir, '{0} abstract task.json'.format(plugin_desc['name'].lower()))
                os.symlink(os.path.relpath(pilot_abstract_task_desc_file, os.path.curdir),
                           out_abstract_task_desc_file)
                os.symlink(os.path.relpath(pilot_plugin_work_dir, os.path.curdir), plugin_work_dir)
            else:
                self.logger.info('Launch plugin {0}'.format(plugin_desc['name']))

                # Get plugin configuration on the basis of common configuration, plugin options specific for requirement
                # specification and information on requirement itself. In addition put either initial or
                # current description of abstract verification task into plugin configuration.
                plugin_conf = copy.deepcopy(self.conf)
                if 'options' in plugin_desc:
                    plugin_conf.update(plugin_desc['options'])
                plugin_conf['in abstract task desc file'] = os.path.relpath(cur_abstract_task_desc_file,
                                                                            self.conf[
                                                                                'main working directory'])
                plugin_conf['out abstract task desc file'] = os.path.relpath(out_abstract_task_desc_file,
                                                                             self.conf[
                                                                                 'main working directory'])
                plugin_conf['solution class'] = self.req_spec_id
                plugin_conf['override resource limits'] = self.override_limits

                plugin_conf_file = '{0} conf.json'.format(plugin_desc['name'].lower())
                self.logger.debug(
                    'Put configuration of plugin "{0}" to file "{1}"'.format(plugin_desc['name'],
                                                                             plugin_conf_file))
                with open(plugin_conf_file, 'w', encoding='utf8') as fp:
                    core.utils.json_dump(plugin_conf, fp, self.conf['keep intermediate files'])

                try:
                    p = plugin_desc['plugin'](plugin_conf, self.logger, self.id, self.callbacks, self.mqs,
                                              self.vals, plugin_desc['name'],
                                              plugin_work_dir, separate_from_parent=True,
                                              include_child_resources=True)
                    p.start()
                    p.join()
                except core.components.ComponentError:
                    self.plugin_fail_processing()
                    break

                if self.req_spec_id in [c[0]['identifier'] for c in _req_spec_classes.values()] and \
                        plugin_desc['name'] == 'EMG':
                    self.logger.debug("Signal to VTG that cache prepared for requirements specifications {!r} is ready"
                                      " for further use".format(pilot_req_spec_id))
                    self.mqs['prepared verification tasks'].put((self.program_fragment_id, self.req_spec_id))

            cur_abstract_task_desc_file = out_abstract_task_desc_file
        else:
            final_abstract_task_desc_file = 'final abstract task.json'
            if not self.rerun:
                self.logger.debug(
                    'Put final abstract verification task description to file "{0}"'.format(
                        final_abstract_task_desc_file))
                # Final abstract verification task description equals to abstract verification task description received
                # from last plugin.
                os.symlink(os.path.relpath(out_abstract_task_desc_file, os.path.curdir),
                           final_abstract_task_desc_file)

            # VTG will consume this abstract verification task description file.
            self.abstract_task_desc_file = out_abstract_task_desc_file

            if os.path.isfile(os.path.join(plugin_work_dir, 'task.json')) and \
               os.path.isfile(os.path.join(plugin_work_dir, 'task files.zip')):
                task_id = self.session.schedule_task(os.path.join(plugin_work_dir, 'task.json'),
                                                     os.path.join(plugin_work_dir, 'task files.zip'))
                with open(self.abstract_task_desc_file, 'r', encoding='utf8') as fp:
                    final_task_data = json.load(fp)

                # Plan for checking status
                self.mqs['pending tasks'].put([
                    [str(task_id), final_task_data["result processing"], self.program_fragment_desc,
                     self.req_spec_id, final_task_data['verifier'], final_task_data['additional sources']],
                    self.rerun
                ])
                self.logger.info("Submitted successfully verification task {} for solution".
                                 format(os.path.join(plugin_work_dir, 'task.json')))
            else:
                self.logger.warning("There is no verification task generated by the last plugin, expect {}".
                                    format(os.path.join(plugin_work_dir, 'task.json')))
                self.mqs['processed tasks'].put((self.program_fragment_id, self.req_spec_id, [None, None, None]))

    def plugin_fail_processing(self):
        """The function has a callback in sub-job processing!"""
        self.logger.debug("VTGW that processed {!r}, {!r} failed".
                          format(self.program_fragment_desc['id'], self.req_spec_id))
        self.mqs['processed tasks'].put((self.program_fragment_desc['id'], self.req_spec_id, [None, None, None]))

    def join(self, timeout=None, stopped=False):
        try:
            ret = super(VTGW, self).join(timeout, stopped)
        finally:
            if not self.conf['keep intermediate files'] and not self.is_alive():
                self.logger.debug("Indicate that the working directory can be deleted for: {!r}, {!r}".
                                  format(self.program_fragment_desc['id'], self.req_spec_id))
                self.mqs['delete dir'].put([self.program_fragment_desc['id'], self.req_spec_id])
        return ret
