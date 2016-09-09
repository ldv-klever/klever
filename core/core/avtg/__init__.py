#!/usr/bin/python3

import copy
import importlib
import json
import multiprocessing
import os
import string
import re

import core.components
import core.utils


default_name = 'sequential combination'

def before_launch_sub_job_components(context):
    context.mqs['AVTG common prj attrs'] = multiprocessing.Queue()
    context.mqs['verification obj desc files'] = multiprocessing.Queue()
    context.mqs['shadow src tree'] = multiprocessing.Queue()
    context.mqs['hdr arch'] = multiprocessing.Queue()


def after_set_common_prj_attrs(context):
    context.mqs['AVTG common prj attrs'].put(context.common_prj_attrs)


def after_set_hdr_arch(context):
    context.mqs['hdr arch'].put(context.hdr_arch)


def after_set_shadow_src_tree(context):
    context.mqs['shadow src tree'].put(context.shadow_src_tree)


def after_generate_verification_obj_desc(context):
    if context.verification_obj_desc:
        context.mqs['verification obj desc files'].put(
            os.path.relpath(context.verification_obj_desc_file, context.conf['main working directory']))


def after_generate_all_verification_obj_descs(context):
    context.logger.info('Terminate verification object description files message queue')
    context.mqs['verification obj desc files'].put(None)


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


def _extract_rule_spec_desc(logger, raw_rule_spec_descs, rule_spec_id):
    logger.info('Extract description for rule specification "{0}"'.format(rule_spec_id))

    # Get raw rule specification description.
    if rule_spec_id in raw_rule_spec_descs['rule specifications']:
        rule_spec_desc = raw_rule_spec_descs['rule specifications'][rule_spec_id]
    else:
        raise ValueError(
            'Specified rule specification "{0}" could not be found in rule specifications DB'.format(rule_spec_id))

    # Get rid of useless information.
    if 'description' in rule_spec_desc:
        del (rule_spec_desc['description'])

    # Get rule specification template which it is based on.
    if 'template' not in rule_spec_desc:
        raise ValueError(
            'Rule specification "{0}" has not mandatory attribute "template"'.format(rule_spec_id))
    tmpl_id = rule_spec_desc['template']
    # This information won't be used any more.
    del (rule_spec_desc['template'])
    logger.debug('Rule specification "{0}" template is "{1}"'.format(rule_spec_id, tmpl_id))
    if 'templates' not in raw_rule_spec_descs or tmpl_id not in raw_rule_spec_descs['templates']:
        raise ValueError(
            'Template "{0}" of rule specification "{1}" could not be found in rule specifications DB'.format(
                tmpl_id, rule_spec_id))
    tmpl_desc = raw_rule_spec_descs['templates'][tmpl_id]

    # Get options for plugins specified in template.
    plugin_descs = _extract_plugin_descs(logger, tmpl_id, tmpl_desc)

    # Get options for plugins specified in base template and merge them with the ones extracted above.
    if 'template' in tmpl_desc:
        if tmpl_desc['template'] not in raw_rule_spec_descs['templates']:
            raise ValueError('Template "{0}" of template "{1}" could not be found in rule specifications DB'.format(
                tmpl_desc['template'], tmpl_id))

        logger.debug('Template "{0}" template is "{1}"'.format(tmpl_id, tmpl_desc['template']))

        base_tmpl_plugin_descs = _extract_plugin_descs(logger, tmpl_desc['template'],
                                                       raw_rule_spec_descs['templates'][tmpl_desc['template']])

        for plugin_desc in plugin_descs:
            for base_tmpl_plugin_desc in base_tmpl_plugin_descs:
                if plugin_desc['name'] == base_tmpl_plugin_desc['name']:
                    if 'options' in base_tmpl_plugin_desc:
                        if 'options' in plugin_desc:
                            plugin_desc['options'] = core.utils.merge_confs(base_tmpl_plugin_desc['options'],
                                                                            plugin_desc['options'])
                        else:
                            plugin_desc['options'] = base_tmpl_plugin_desc['options']

    # Add plugin options specific for rule specification.
    rule_spec_plugin_names = []
    for attr in rule_spec_desc:
        # Names of all other attributes are considered as plugin names, values - as corresponding plugin options.
        if attr == 'rule specifications':
            continue

        plugin_name = attr
        rule_spec_plugin_names.append(plugin_name)
        is_plugin_specified = False

        for plugin_desc in plugin_descs:
            if plugin_name == plugin_desc['name']:
                is_plugin_specified = True
                if 'options' not in plugin_desc:
                    plugin_desc['options'] = {}
                plugin_desc['options'].update(rule_spec_desc[plugin_name])
                logger.debug(
                    'Plugin "{0}" options specific for rule specification "{1}" are "{2}"'.format(
                        plugin_name, rule_spec_id, rule_spec_desc[plugin_name]))
                break

        if not is_plugin_specified:
            raise ValueError(
                'Rule specification "{0}" plugin "{1}" is not specified in template "{2}"'.format(
                    rule_spec_id, plugin_name, tmpl_id))

    # We don't need to keep plugin options specific for rule specification in such the form any more.
    for plugin_name in rule_spec_plugin_names:
        del (rule_spec_desc[plugin_name])

    if 'rule specifications' in rule_spec_desc:
        # Merge plugin options specific for constituent rule specifications.
        for constituent_rule_spec_id in rule_spec_desc['rule specifications']:
            for constituent_rule_spec_plugin_desc in _extract_rule_spec_desc(logger, raw_rule_spec_descs, constituent_rule_spec_id)['plugins']:
                for plugin_desc in plugin_descs:
                    if constituent_rule_spec_plugin_desc['name'] == plugin_desc['name']:
                        # Specify constituent rule specification identifier for RSG models. It will be used to generate
                        # unique variable and function names.
                        if constituent_rule_spec_plugin_desc['name'] == 'RSG' \
                           and 'options' in constituent_rule_spec_plugin_desc \
                           and 'models' in constituent_rule_spec_plugin_desc['options']:
                            rsg_models = constituent_rule_spec_plugin_desc['options']['models']
                            for model in rsg_models:
                                rsg_models[model]['rule specification identifier'] = constituent_rule_spec_id
                        if 'options' in plugin_desc and 'options' in constituent_rule_spec_plugin_desc:
                            core.utils.merge_confs(plugin_desc['options'], constituent_rule_spec_plugin_desc['options'])
                        elif 'options' in constituent_rule_spec_plugin_desc:
                            plugin_desc['options'] = constituent_rule_spec_plugin_desc['options']
                        break
        del (rule_spec_desc['rule specifications'])

    rule_spec_desc['plugins'] = plugin_descs

    # Add rule specification identifier to its description after all. Do this so late to avoid treating of "id" as
    # plugin name above.
    rule_spec_desc['id'] = rule_spec_id

    return rule_spec_desc


# This function automatically untites all rule specifications and creates new rule specification.
def _unite_rule_specifications(conf, logger, raw_rule_spec_descs):
    logger.info('Unite all rule specifications')

    rule_specifications = conf['rule specifications']
    prefix = os.path.commonprefix(rule_specifications)
    new_rule_name_id = prefix + ":" + 'united'
    logger.info('United rule specification was given the following name "{0}"'.format(new_rule_name_id))

    template = 'Linux kernel modules'

    for rule_specification in rule_specifications:
        model = raw_rule_spec_descs['rule specifications'][rule_specification]
        if model['template'] == 'Argument signatures for Linux kernel modules':
            template = 'Argument signatures for Linux kernel modules'
            break

    raw_rule_spec_descs['rule specifications'][new_rule_name_id] = {
        'template': template,
        'rule specifications': rule_specifications
    }

    conf['rule specifications'] = [new_rule_name_id]


def parse_bug_kind(bug_kind):
        match = re.search(r'(.+)::(.*)', bug_kind)
        if match:
            return match.groups()[0]
        else:
            return ''

# This function is invoked to collect plugin callbacks.
def _extract_rule_spec_descs(conf, logger):
    logger.info('Extract rule specificaction decriptions')

    if 'bug kinds' in conf:
        if 'rule specifications' in conf:
            raise KeyError('Specified both rule specifications and bug kinds')
        logger.info('Checking bug kinds')
    else:
        if 'rule specifications' not in conf:
            logger.warning('Nothing will be verified since rule specifications are not specified')
            return []

    # Read rule specification descriptions DB.
    with open(core.utils.find_file_or_dir(logger, conf['main working directory'], conf['rule specifications DB']),
              encoding='utf8') as fp:
        raw_rule_spec_descs = json.load(fp)

    if 'rule specifications' not in raw_rule_spec_descs:
        raise KeyError('Rule specifications DB has not mandatory attribute "rule specifications"')

    if 'bug kinds' in conf:
        bug_kinds = []
        rules = set()
        for bug_kind in conf['bug kinds']:
            rule = parse_bug_kind(bug_kind)
            rules.add(rule)
            bug_kinds.append(bug_kind)
        conf['rule specifications'] = list(rules)
        for rule, desc in raw_rule_spec_descs['rule specifications'].items():
            if rule in rules:
                for model, attrs in desc['RSG']['models'].items():
                    for attr, val in attrs.items():
                        if attr == 'bug kinds':
                            tmp_bug_kinds = val.copy()
                            for bug_kind in tmp_bug_kinds:
                                if bug_kind not in bug_kinds:
                                    val.remove(bug_kind)

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

    # Default strategy (SC).
    if conf['VTG strategy']['name'] == default_name and len(conf['rule specifications']) > 1:
        logger.info('Using default strategy for verifying several rules')
        conf['unite rule specifications'] = True
        conf['RSG strategy'] = 'all'
        conf['common aspect'] = 'linux/common.aspect'
    if 'unite rule specifications' in conf and conf['unite rule specifications']:
        _unite_rule_specifications(conf, logger, raw_rule_spec_descs)

    rule_spec_descs = []

    for rule_spec_id in conf['rule specifications']:
        rule_spec_descs.append(_extract_rule_spec_desc(logger, raw_rule_spec_descs, rule_spec_id))

    if conf['keep intermediate files']:
        #if os.path.isfile('rule spec descs.json'):
        #    raise FileExistsError('Rule specification descriptions file "rule spec descs.json" already exists')
        logger.debug('Create rule specification descriptions file "rule spec descs.json"')
        with open('rule spec descs.json', 'w', encoding='ascii') as fp:
            json.dump(rule_spec_descs, fp, sort_keys=True, indent=4)

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
                plugin = getattr(importlib.import_module('.{0}'.format(plugin_desc['name'].lower()), 'core.avtg'),
                                 plugin_desc['name'])
                # Remember found class to create its instance during main operation.
                plugin_desc['plugin'] = plugin
                if plugin not in plugins:
                    plugins.append(plugin)
            except ImportError:
                raise NotImplementedError('Plugin {0} is not supported'.format(plugin_desc['name']))

    return core.utils.get_component_callbacks(logger, plugins, conf)


class AVTG(core.components.Component):
    def generate_abstract_verification_tasks(self):
        # TODO: get rid of these variables.
        self.common_prj_attrs = {}
        self.abstract_task_desc_file = None
        self.abstract_task_desc_num = 0

        # TODO: combine extracting and reporting of attributes.
        self.get_common_prj_attrs()
        core.utils.report(self.logger,
                          'attrs',
                          {
                              'id': self.id,
                              'attrs': self.common_prj_attrs
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'])
        self.get_shadow_src_tree()
        self.get_hdr_arch()
        # Rule specification descriptions were already extracted when getting AVTG callbacks.
        self.rule_spec_descs = _rule_spec_descs
        self.set_model_cc_opts_and_headers()
        self.generate_all_abstract_verification_task_descs()

    main = generate_abstract_verification_tasks

    def get_common_prj_attrs(self):
        self.logger.info('Get common project atributes')

        self.common_prj_attrs = self.mqs['AVTG common prj attrs'].get()

        self.mqs['AVTG common prj attrs'].close()

    def set_model_cc_opts_and_headers(self):
        self.logger.info('Set model CC options and headers')

        self.model_cc_opts_and_headers = {}

        for rule_spec_desc in self.rule_spec_descs:
            self.logger.debug('Set headers of rule specification "{0}"'.format(rule_spec_desc['id']))
            for plugin_desc in rule_spec_desc['plugins']:
                if plugin_desc['name'] == 'RSG' \
                        and 'model CC options' in plugin_desc['options'] \
                        and ('common models' in plugin_desc['options'] or 'models' in plugin_desc['options']):
                    for models in ('common models', 'models'):
                        if models in plugin_desc['options']:
                            for model_c_file, model in plugin_desc['options'][models].items():
                                self.logger.debug('Set headers of model with C file "{0}"'.format(model_c_file))
                                if 'headers' in model:
                                    self.model_cc_opts_and_headers[model_c_file] = {
                                        'CC options': [
                                            string.Template(opt).substitute(hdr_arch=self.conf['header architecture'])
                                            for opt in plugin_desc['options']['model CC options']
                                        ],
                                        'headers': []
                                    }
                                    self.logger.debug('Set model CC options "{0}"'.format(
                                        self.model_cc_opts_and_headers[model_c_file]['CC options']))
                                    for header in model['headers']:
                                        self.model_cc_opts_and_headers[model_c_file]['headers'].append(
                                            string.Template(header).substitute(
                                                hdr_arch=self.conf['header architecture']))
                                    self.logger.debug('Set headers "{0}"'.format(
                                        self.model_cc_opts_and_headers[model_c_file]['headers']))

    def get_hdr_arch(self):
        self.logger.info('Get architecture name to search for architecture specific header files')

        self.conf['header architecture'] = self.mqs['hdr arch'].get()

        self.mqs['hdr arch'].close()

        self.logger.debug('Architecture name to search for architecture specific header files is "{0}"'.format(
            self.conf['header architecture']))

    def get_shadow_src_tree(self):
        self.logger.info('Get shadow source tree')

        self.conf['shadow source tree'] = self.mqs['shadow src tree'].get()

        self.mqs['shadow src tree'].close()

        self.logger.debug('Shadow source tree "{0}"'.format(self.conf['shadow source tree']))

    def generate_all_abstract_verification_task_descs(self):
        self.logger.info('Generate all abstract verification task decriptions')

        while True:
            verification_obj_desc_file = self.mqs['verification obj desc files'].get()

            if verification_obj_desc_file is None:
                self.logger.debug('Verification object descriptions message queue was terminated')
                self.mqs['verification obj desc files'].close()
                break

            with open(os.path.join(self.conf['main working directory'], verification_obj_desc_file),
                      encoding='ascii') as fp:
                verification_obj_desc = json.load(fp)

            if not self.rule_spec_descs:
                self.logger.warning(
                    'Verification object {0} will not be verified since rule specifications are not specified'.format(
                        verification_obj_desc['id']))

            # TODO: specification requires to do this in parallel...
            for rule_spec_desc in self.rule_spec_descs:
                self.generate_abstact_verification_task_desc(verification_obj_desc, rule_spec_desc)

    def generate_abstact_verification_task_desc(self, verification_obj_desc, rule_spec_desc):
        initial_attrs = (
            {'verification object': verification_obj_desc['id']},
            {'rule specification': rule_spec_desc['id']}
        )
        initial_attr_vals = tuple(attr[name] for attr in initial_attrs for name in attr)

        # TODO: print progress: n + 1/N, where n/N is the number of already generated/all to be generated verification tasks.
        self.logger.info(
            'Generate abstract verification task description for {0}'.format(
                'verification object "{0}" and rule specification "{1}"'.format(*initial_attr_vals)))

        plugins_work_dir = os.path.join(verification_obj_desc['id'], rule_spec_desc['id'])
        os.makedirs(plugins_work_dir, exist_ok=True)
        self.logger.debug('Plugins working directory is "{0}"'.format(plugins_work_dir))

        # Initial abstract verification task looks like corresponding verification object.
        initial_abstract_task_desc = copy.deepcopy(verification_obj_desc)
        initial_abstract_task_desc['id'] = '{0}/{1}'.format(*initial_attr_vals)
        initial_abstract_task_desc['attrs'] = initial_attrs
        for grp in initial_abstract_task_desc['grps']:
            grp['cc extra full desc files'] = []
            for cc_full_desc_file in grp['cc full desc files']:
                with open(os.path.join(self.conf['main working directory'], cc_full_desc_file), encoding='ascii') as fh:
                    command = json.load(fh)
                in_file = command['in files'][0]
                grp['cc extra full desc files'].append({'cc full desc file': cc_full_desc_file, "in file": in_file})
            del (grp['cc full desc files'])
        initial_abstract_task_desc_file = os.path.join(plugins_work_dir, 'initial abstract task.json')
        self.logger.debug(
            'Put initial abstract verification task description to file "{0}"'.format(initial_abstract_task_desc_file))
        with open(initial_abstract_task_desc_file, 'w', encoding='ascii') as fp:
            json.dump(initial_abstract_task_desc, fp, sort_keys=True, indent=4)

        # Invoke all plugins one by one.
        try:
            cur_abstract_task_desc_file = initial_abstract_task_desc_file
            out_abstract_task_desc_file = None
            for plugin_desc in rule_spec_desc['plugins']:
                self.logger.info('Launch plugin {0}'.format(plugin_desc['name']))

                # Here plugin will put modified abstract verification task description.
                out_abstract_task_desc_file = os.path.join(plugins_work_dir,
                                                           '{0} abstract task.json'.format(plugin_desc['name'].lower()))

                # Get plugin configuration on the basis of common configuration, plugin options specific for rule
                # specification and information on rule specification itself. In addition put either initial or current
                # description of abstract verification task into plugin configuration.
                plugin_conf = copy.deepcopy(self.conf)
                if plugin_desc['name'] != 'RSG':
                    del plugin_conf['shadow source tree']
                if 'options' in plugin_desc:
                    plugin_conf.update(plugin_desc['options'])
                plugin_conf.update({'rule spec id': rule_spec_desc['id']})
                if 'bug kinds' in rule_spec_desc:
                    plugin_conf.update({'bug kinds': rule_spec_desc['bug kinds']})
                plugin_conf['in abstract task desc file'] = os.path.relpath(cur_abstract_task_desc_file,
                                                                            self.conf['main working directory'])
                plugin_conf['out abstract task desc file'] = os.path.relpath(out_abstract_task_desc_file,
                                                                             self.conf['main working directory'])

                if self.conf['keep intermediate files']:
                    plugin_conf_file = os.path.join(plugins_work_dir,
                                                    '{0} conf.json'.format(plugin_desc['name'].lower()))
                    self.logger.debug(
                        'Put configuration of plugin "{0}" to file "{1}"'.format(plugin_desc['name'], plugin_conf_file))
                    with open(plugin_conf_file, 'w', encoding='ascii') as fp:
                        json.dump(plugin_conf, fp, sort_keys=True, indent=4)

                p = plugin_desc['plugin'](plugin_conf, self.logger, self.id, self.callbacks, self.mqs, self.locks,
                                          '{0}/{1}/{2}'.format(*list(initial_attr_vals) + [plugin_desc['name']]),
                                          os.path.join(plugins_work_dir, plugin_desc['name'].lower()), initial_attrs,
                                          True, True)
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
            os.symlink(os.path.relpath(out_abstract_task_desc_file, plugins_work_dir), final_abstract_task_desc_file)

            # VTG will consume this abstract verification task description file.
            self.abstract_task_desc_file = out_abstract_task_desc_file

            # Count the number of successfully generated abstract verification task descriptions.
            self.abstract_task_desc_num += 1
        # Failures in plugins aren't treated as the critical ones. We just warn and proceed to other
        # verification objects or/and rule specifications.
        except core.components.ComponentError:
            self.abstract_task_desc_file = None
            self.verification_obj = verification_obj_desc['id']
            self.rule_spec = rule_spec_desc['id']
