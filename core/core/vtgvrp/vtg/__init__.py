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

import re
import importlib
import json
import multiprocessing
import os
import copy

import core.components
import core.utils


def before_launch_sub_job_components(context):
    context.mqs['verification obj desc files'] = multiprocessing.Queue()
    context.mqs['verification obj descs num'] = multiprocessing.Queue()
    context.mqs['shadow src tree'] = multiprocessing.Queue()
    context.mqs['model CC opts'] = multiprocessing.Queue()


def after_set_common_prj_attrs(context):
    context.mqs['VTGVRP common prj attrs'].put(context.common_prj_attrs)


def after_set_shadow_src_tree(context):
    context.mqs['shadow src tree'].put(context.shadow_src_tree)


def after_fixup_model_cc_opts(context):
    context.mqs['model CC opts'].put(context.model_cc_opts)


def after_generate_verification_obj_desc(context):
    if context.verification_obj_desc:
        context.mqs['verification obj desc files'].put(
            os.path.relpath(context.verification_obj_desc_file, context.conf['main working directory']))


def after_generate_all_verification_obj_descs(context):
    context.logger.info('Terminate verification object description files message queue')
    context.mqs['verification obj desc files'].put(None)
    # todo: fix or rewrite
    #context.mqs['verification obj descs num'].put(context.verification_obj_desc_num)


def _extract_plugin_descs(logger, tmpl_id, tmpl_desc):
    logger.info('Extract descriptions for plugins of template "{0}"'.format(tmpl_id))

    if 'plugins' not in tmpl_desc:
        raise ValueError(
            'Template "{0}" has not mandatory attribute "plugins"'.format(tmpl_id))

    # Copy plugin descriptions since we will overwrite them while the same template can be used by different rule
    # specifications
    plugin_descs = copy.deepcopy(tmpl_desc['plugins'])

    for idx, plugin_desc in enumerate(plugin_descs):
        if isinstance(plugin_desc, dict) \
                and (len(plugin_desc.keys()) > 1 or not isinstance(list(plugin_desc.keys())[0], str)) \
                and not isinstance(plugin_desc, str):
            raise ValueError(
                'Description of template "{0}" plugin "{1}" has incorrect format'.format(tmpl_id, idx))
        if isinstance(plugin_desc, dict):
            plugin_descs[idx] = {
                'name': list(plugin_desc.keys())[0],
                'options': plugin_desc[list(plugin_desc.keys())[0]]
            }
        else:
            plugin_descs[idx] = {'name': plugin_desc}

    logger.debug(
        'Template "{0}" plugins are "{1}"'.format(tmpl_id, [plugin_desc['name'] for plugin_desc in plugin_descs]))

    return plugin_descs


# This function is invoked to collect plugin callbacks.
def _extract_rule_spec_descs(conf, logger):
    logger.info('Extract rule specificaction decriptions')

    if 'rule specifications DB' not in conf:
        logger.warning('Nothing will be verified since rule specifications DB is not specified')
        return []

    if 'rule specifications' not in conf:
        logger.warning('Nothing will be verified since rule specifications are not specified')
        return []

    if 'specifications set' not in conf:
        logger.warning('Nothing will be verified since specifications set is not specified')
        return []

    # Read rule specification descriptions DB.
    with open(core.utils.find_file_or_dir(logger, conf['main working directory'], conf['rule specifications DB']),
              encoding='utf8') as fp:
        raw_rule_spec_descs = json.load(fp)

    if 'rule specifications' not in raw_rule_spec_descs:
        raise KeyError('Rule specifications DB has not mandatory attribute "rule specifications"')

    if 'all' in conf['rule specifications']:
        if not len(conf['rule specifications']) == 1:
            raise ValueError(
                'You can not specify "all" rule specifications together with some other rule specifications')

        # Add all rule specification identifiers from DB.
        conf['rule specifications'] = sorted(raw_rule_spec_descs['rule specifications'].keys())

        # Remove all empty rule specifications since they are intended for development.
        rule_specs = []
        for rule_spec_id in conf['rule specifications']:
            if rule_spec_id.find('empty') == -1 and rule_spec_id.find('test') == -1:
                rule_specs.append(rule_spec_id)
        conf['rule specifications'] = rule_specs
        logger.debug('Following rule specifications will be checked "{0}"'.format(conf['rule specifications']))

    rule_spec_descs = []

    for rule_spec_id in conf['rule specifications']:
        rule_spec_descs.append(_extract_rule_spec_desc(logger, raw_rule_spec_descs, rule_spec_id))

    if conf['keep intermediate files']:
        if os.path.isfile('rule spec descs.json'):
           raise FileExistsError('Rule specification descriptions file "rule spec descs.json" already exists')
        logger.debug('Create rule specification descriptions file "rule spec descs.json"')
        with open('rule spec descs.json', 'w', encoding='utf8') as fp:
            json.dump(rule_spec_descs, fp, ensure_ascii=False, sort_keys=True, indent=4)

    return rule_spec_descs


_rule_spec_descs = None


def get_subcomponent_callbacks(conf, logger):
    logger.info('Get AVTG plugin callbacks')

    global _rule_spec_descs
    _rule_spec_descs = _extract_rule_spec_descs(conf, logger)

    plugins = []

    # Find appropriate classes for plugins if so.
    for rule_spec_desc in _rule_spec_descs:
        for plugin_desc in rule_spec_desc['plugins']:
            try:
                plugin = getattr(importlib.import_module('.{0}'.format(plugin_desc['name'].lower()), 'core.vtgvrp'),
                                 plugin_desc['name'])
                # Remember found class to create its instance during main operation.
                plugin_desc['plugin'] = plugin
                if plugin not in plugins:
                    plugins.append(plugin)
            except ImportError:
                raise NotImplementedError('Plugin {0} is not supported'.format(plugin_desc['name']))

    return core.utils.get_component_callbacks(logger, plugins, conf)

###############################################################################
def before_launch_sub_job_components(context):
    context.mqs['VTG common prj attrs'] = multiprocessing.Queue()
    context.mqs['abstract task desc files'] = multiprocessing.Queue()
    context.mqs['num of abstract task descs to be generated'] = multiprocessing.Queue()


def after_set_common_prj_attrs(context):
    context.mqs['VTG common prj attrs'].put(context.common_prj_attrs)


def after_set_shadow_src_tree(context):
    context.mqs['shadow src tree'].put(context.shadow_src_tree)


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
        self.__set_model_headers()
        self.__get_shadow_src_tree()
        self.__get_model_cc_opts()
        # Rule specification descriptions were already extracted when getting AVTG callbacks.
        self.rule_spec_descs = _rule_spec_descs

    main = generate_verification_tasks

    def __set_model_headers(self):
        self.logger.info('Set model headers')

        self.model_headers = {}

        for rule_spec_desc in self.rule_spec_descs:
            self.logger.debug('Set headers of rule specification "{0}"'.format(rule_spec_desc['id']))
            for plugin_desc in rule_spec_desc['plugins']:
                if plugin_desc['name'] != 'RSG':
                    continue

                for models in ('common models', 'models'):
                    if models in plugin_desc['options']:
                        for model_c_file, model in plugin_desc['options'][models].items():
                            if 'headers' not in model:
                                continue

                            self.logger.debug('Set headers of model with C file "{0}"'.format(model_c_file))

                            if isinstance(model['headers'], dict):
                                # Find out base specifications set.
                                base_specs_set = None
                                for specs_set in model['headers']:
                                    if re.search(r'\(base\)', specs_set):
                                        base_specs_set = specs_set
                                        break
                                if not base_specs_set:
                                    raise KeyError('Could not find base specifications set')

                                # Always require all headers of base specifications set.
                                headers = model['headers'][base_specs_set]

                                specs_set = self.conf['specifications set']

                                # Add/exclude specific headers of specific specifications set.
                                if specs_set != base_specs_set and specs_set in model['headers']:
                                    if 'add' in model['headers'][specs_set]:
                                        for add_header in model['headers'][specs_set]['add']:
                                            headers.append(add_header)
                                    if 'exclude' in model['headers'][specs_set]:
                                        for exclude_header in model['headers'][specs_set]['exclude']:
                                            headers.remove(exclude_header)
                            else:
                                headers = model['headers']

                            self.model_headers[model_c_file] = headers

                            self.logger.debug('Set headers "{0}"'.format(headers))

    def __get_shadow_src_tree(self):
        self.logger.info('Get shadow source tree')

        self.conf['shadow source tree'] = self.mqs['shadow src tree'].get()

        self.mqs['shadow src tree'].close()

        self.logger.debug('Shadow source tree "{0}"'.format(self.conf['shadow source tree']))

    def __get_model_cc_opts(self):
        self.logger.info('Get model CC options')

        self.conf['model CC opts'] = self.mqs['model CC opts'].get()

        self.mqs['model CC opts'].close()

    def __generate_all_abstract_verification_task_descs(self):
        self.logger.info('Generate all abstract verification task decriptions')

        while True:
            verification_obj_desc_file = self.mqs['verification obj desc files'].get()

            if verification_obj_desc_file is None:
                self.logger.debug('Verification object descriptions message queue was terminated')
                self.mqs['verification obj desc files'].close()
                break

            with open(os.path.join(self.conf['main working directory'], verification_obj_desc_file),
                      encoding='utf8') as fp:
                verification_obj_desc = json.load(fp)

            if not self.rule_spec_descs:
                self.logger.warning(
                    'Verification object {0} will not be verified since rule specifications are not specified'.format(
                        verification_obj_desc['id']))

            # TODO: specification requires to do this in parallel...
            for rule_spec_desc in self.rule_spec_descs:
                self.__generate_abstact_verification_task_desc(verification_obj_desc, rule_spec_desc)

        # todo: fix or reimplement
        # if self.failed_abstract_task_desc_num.value:
        #     self.logger.info('Could not generate "{0}" abstract verification task descriptions'.format(
        #         self.failed_abstract_task_desc_num.value))

    def __generate_abstact_verification_task_desc(self, verification_obj_desc, rule_spec_desc):
        # todo: fix or reimplement
        # Count the number of generated abstract verification task descriptions.
        # self.abstract_task_desc_num += 1

        initial_attrs = (
            {'verification object': verification_obj_desc['id']},
            {'rule specification': rule_spec_desc['id']}
        )
        initial_attr_vals = tuple(attr[name] for attr in initial_attrs for name in attr)

        # todo: fix or reimplement
        # self.logger.info(
        #     'Generate abstract verification task description for {0} ({1}{2})'.format(
        #         'verification object "{0}" and rule specification "{1}"'.format(*initial_attr_vals),
        #         self.abstract_task_desc_num, '/{0}'.format(self.abstract_task_descs_num.value)
        #         if self.abstract_task_descs_num.value else ''))

        plugins_work_dir = os.path.join(verification_obj_desc['id'], rule_spec_desc['id'])
        os.makedirs(plugins_work_dir.encode('utf8'), exist_ok=True)
        self.logger.debug('Plugins working directory is "{0}"'.format(plugins_work_dir))

        # Initial abstract verification task looks like corresponding verification object.
        initial_abstract_task_desc = copy.deepcopy(verification_obj_desc)
        initial_abstract_task_desc['id'] = '{0}/{1}'.format(*initial_attr_vals)
        initial_abstract_task_desc['attrs'] = initial_attrs
        for grp in initial_abstract_task_desc['grps']:
            grp['cc extra full desc files'] = []
            for cc_full_desc_file in grp['cc full desc files']:
                with open(os.path.join(self.conf['main working directory'], cc_full_desc_file),
                          encoding='utf8') as fh:
                    command = json.load(fh)
                in_file = command['in files'][0]
                grp['cc extra full desc files'].append(
                    {'cc full desc file': cc_full_desc_file, "in file": in_file})
            del (grp['cc full desc files'])
        initial_abstract_task_desc_file = os.path.join(plugins_work_dir, 'initial abstract task.json')
        self.logger.debug(
            'Put initial abstract verification task description to file "{0}"'.format(
                initial_abstract_task_desc_file))
        with open(initial_abstract_task_desc_file, 'w', encoding='utf8') as fp:
            json.dump(initial_abstract_task_desc, fp, ensure_ascii=False, sort_keys=True, indent=4)

        # Invoke all plugins one by one.
        try:
            cur_abstract_task_desc_file = initial_abstract_task_desc_file
            out_abstract_task_desc_file = None
            for plugin_desc in rule_spec_desc['plugins']:
                self.logger.info('Launch plugin {0}'.format(plugin_desc['name']))

                # Here plugin will put modified abstract verification task description.
                out_abstract_task_desc_file = os.path.join(plugins_work_dir,
                                                           '{0} abstract task.json'.format(
                                                               plugin_desc['name'].lower()))

                # Get plugin configuration on the basis of common configuration, plugin options specific for rule
                # specification and information on rule specification itself. In addition put either initial or current
                # description of abstract verification task into plugin configuration.
                plugin_conf = copy.deepcopy(self.conf)
                if plugin_desc['name'] != 'RSG':
                    del plugin_conf['shadow source tree']
                if 'options' in plugin_desc:
                    plugin_conf.update(plugin_desc['options'])
                if 'bug kinds' in rule_spec_desc:
                    plugin_conf.update({'bug kinds': rule_spec_desc['bug kinds']})
                plugin_conf['in abstract task desc file'] = os.path.relpath(cur_abstract_task_desc_file,
                                                                            self.conf[
                                                                                'main working directory'])
                plugin_conf['out abstract task desc file'] = os.path.relpath(out_abstract_task_desc_file,
                                                                             self.conf[
                                                                                 'main working directory'])

                if self.conf['keep intermediate files']:
                    plugin_conf_file = os.path.join(plugins_work_dir,
                                                    '{0} conf.json'.format(plugin_desc['name'].lower()))
                    self.logger.debug(
                        'Put configuration of plugin "{0}" to file "{1}"'.format(plugin_desc['name'],
                                                                                 plugin_conf_file))
                    with open(plugin_conf_file, 'w', encoding='utf8') as fp:
                        json.dump(plugin_conf, fp, ensure_ascii=False, sort_keys=True, indent=4)

                p = plugin_desc['plugin'](plugin_conf, self.logger, self.id, self.callbacks, self.mqs,
                                          self.locks,
                                          '{0}/{1}/{2}'.format(
                                              *list(initial_attr_vals) + [plugin_desc['name']]),
                                          os.path.join(plugins_work_dir, plugin_desc['name'].lower()),
                                          attrs=initial_attrs, separate_from_parent=True,
                                          include_child_resources=True)
                p.start()
                p.join()

                if not self.conf['keep intermediate files']:
                    os.remove(cur_abstract_task_desc_file)

                cur_abstract_task_desc_file = out_abstract_task_desc_file

            final_abstract_task_desc_file = os.path.join(plugins_work_dir, 'final abstract task.json')
            self.logger.debug(
                'Put final abstract verification task description to file "{0}"'.format(
                    final_abstract_task_desc_file))
            # Final abstract verification task description equals to abstract verification task description received
            # from last plugin.
            os.symlink(os.path.relpath(out_abstract_task_desc_file, plugins_work_dir),
                       final_abstract_task_desc_file)

            # VTG will consume this abstract verification task description file.
            self.abstract_task_desc_file = out_abstract_task_desc_file
        # Failures in plugins aren't treated as the critical ones. We just warn and proceed to other
        # verification objects or/and rule specifications.
        except core.components.ComponentError:
            # todo: fix or rewrite
            # Count the number of abstract verification task descriptions that weren't generated successfully to print
            # it at the end of work. Note that the total number of abstract verification task descriptions to be
            # generated in ideal will be printed at least once already.
            # with self.failed_abstract_task_desc_num.get_lock():
            #    self.failed_abstract_task_desc_num.value += 1
            #    core.utils.report(self.logger,
            #                       'data',
            #                       {
            #                           'id': self.id,
            #                           'data': {
            #                               'faulty generated abstract verification task descriptions':
            #                                   self.failed_abstract_task_desc_num.value
            #                           }
            #                       },
            #                       self.mqs['report files'],
            #                       self.conf['main working directory'],
            #                       self.failed_abstract_task_desc_num.value)

            self.verification_obj = verification_obj_desc['id']
            self.rule_spec = rule_spec_desc['id']



########################################################################
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
        self.get_shadow_src_tree()
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

        try:
            self.strategy = getattr(importlib.import_module('.{0}'.format(self.strategy_name.lower()), 'core.vtg'),
                                    self.strategy_name.upper())
        except ImportError:
            raise NotImplementedError('Strategy "{0}" is not supported'.format(self.conf['VTG strategy']['name']))


    def get_common_prj_attrs(self):
        self.logger.info('Get common project atributes')

        self.common_prj_attrs = self.mqs['VTG common prj attrs'].get()

        self.mqs['VTG common prj attrs'].close()

    def get_shadow_src_tree(self):
        self.logger.info('Get shadow source tree')

        self.conf['shadow source tree'] = self.mqs['shadow src tree'].get()

        self.mqs['shadow src tree'].close()

        self.logger.debug('Shadow source tree "{0}"'.format(self.conf['shadow source tree']))

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
                                          'data': {
                                              'faulty processed abstract verification task descriptions':
                                                  self.faulty_processed_abstract_task_descs_num.value
                                          }
                                      },
                                      self.mqs['report files'],
                                      self.conf['main working directory'],
                                      self.faulty_processed_abstract_task_descs_num.value)
