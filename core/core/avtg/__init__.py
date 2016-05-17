#!/usr/bin/python3

import copy
import importlib
import json
import multiprocessing
import os
import queue

import core.components
import core.utils


def before_launch_sub_job_components(context):
    context.mqs['AVTG common prj attrs'] = multiprocessing.Queue()
    context.mqs['verification obj descs'] = multiprocessing.Queue()
    context.mqs['AVTG src tree root'] = multiprocessing.Queue()
    context.mqs['hdr arch'] = multiprocessing.Queue()


def after_set_common_prj_attrs(context):
    context.mqs['AVTG common prj attrs'].put(context.common_prj_attrs)


def after_set_src_tree_root(context):
    context.mqs['AVTG src tree root'].put(context.src_tree_root)


def after_set_hdr_arch(context):
    context.mqs['hdr arch'].put(context.hdr_arch)


def after_generate_verification_obj_desc(context):
    # We need to copy verification object description since it may be accidently overwritten by LKVOG.
    context.mqs['verification obj descs'].put(copy.deepcopy(context.verification_obj_desc))


def after_generate_all_verification_obj_descs(context):
    context.logger.info('Terminate verification object descriptions message queue')
    context.mqs['verification obj descs'].put(None)


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

    if 'rule specifications' not in conf:
        logger.warning('Nothing will be verified since rule specifications are not specified')
        return []

    # Read rule specification descriprions DB.
    with open(core.utils.find_file_or_dir(logger, conf['main working directory'], conf['rule specifications DB']),
              encoding='ascii') as fp:
        descs = json.load(fp)

    rule_spec_descs = []

    for rule_spec_id in conf['rule specifications']:
        logger.info('Extract description for rule specification "{0}"'.format(rule_spec_id))

        # Get raw rule specification description.
        if 'rule specifications' not in descs or rule_spec_id not in descs['rule specifications']:
            is_alias_found = False
            for potential_rule_spec_id, potential_rule_spec_desc in descs['rule specifications'].items():
                if 'aliases' in potential_rule_spec_desc:
                    for alias in potential_rule_spec_desc['aliases']:
                        if rule_spec_id == alias:
                            is_alias_found = True
                            logger.debug(
                                'Rule specification "{0}" was found by alias "{1}"'.format(potential_rule_spec_id,
                                                                                           rule_spec_id))
                            # Use true rule specification ID rather than its alias further.
                            rule_spec_id = potential_rule_spec_id
                            break
                if is_alias_found:
                    rule_spec_desc = potential_rule_spec_desc
                    break

            if not is_alias_found:
                raise ValueError(
                    'Specified rule specification "{0}" could not be found in rule specifications DB'.format(
                        rule_spec_id))
        else:
            rule_spec_desc = descs['rule specifications'][rule_spec_id]

        rule_spec_desc['id'] = rule_spec_id

        # Get rid of useless information.
        for attr in ('aliases', 'description'):
            if attr in rule_spec_desc:
                del (rule_spec_desc[attr])

        # Get rule specification template which it is based on.
        if 'template' not in rule_spec_desc:
            raise ValueError(
                'Rule specification "{0}" has not mandatory attribute "template"'.format(rule_spec_id))
        tmpl_id = rule_spec_desc['template']
        # This information won't be used any more.
        del (rule_spec_desc['template'])
        logger.debug('Rule specification "{0}" template is "{1}"'.format(rule_spec_id, tmpl_id))
        if 'templates' not in descs or tmpl_id not in descs['templates']:
            raise ValueError(
                'Template "{0}" of rule specification "{1}" could not be found in rule specifications DB'.format(
                    tmpl_id, rule_spec_id))
        tmpl_desc = descs['templates'][tmpl_id]

        # Get options for plugins specified in template.
        plugin_descs = _extract_plugin_descs(logger, tmpl_id, tmpl_desc)

        # Get options for plugins specified in base template and merge them with the ones extracted above.
        if 'template' in tmpl_desc:
            if tmpl_desc['template'] not in descs['templates']:
                raise ValueError('Template "{0}" of template "{1}" could not be found in rule specifications DB'.format(
                    tmpl_desc['template'], tmpl_id))

            logger.debug('Template "{0}" template is "{1}"'.format(tmpl_id, tmpl_desc['template']))

            base_tmpl_plugin_descs = _extract_plugin_descs(logger, tmpl_desc['template'],
                                                           descs['templates'][tmpl_desc['template']])

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
            if attr not in ('id', 'bug kinds'):
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
                            'Plugin "{0}" options specific for rule specification "{1}" are "{2}"'.format(plugin_name,
                                                                                                          rule_spec_id,
                                                                                                          rule_spec_desc[
                                                                                                              plugin_name]))
                        break

                if not is_plugin_specified:
                    raise ValueError(
                        'Rule specification "{0}" plugin "{1}" is not specified in template "{2}"'.format(
                            rule_spec_id, plugin_name, tmpl_id))
        # We don't need to keep plugin options specific for rule specification in such the form any more.
        for plugin_name in rule_spec_plugin_names:
            del (rule_spec_desc[plugin_name])
        rule_spec_desc['plugins'] = plugin_descs

        rule_spec_descs.append(rule_spec_desc)

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
        self.plugins_work_dir = None
        self.abstract_task_desc = None
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
        self.get_src_tree_root()
        self.get_hdr_arch()
        self.rule_spec_descs = _rule_spec_descs
        self.generate_all_abstract_verification_task_descs()

    main = generate_abstract_verification_tasks

    def get_common_prj_attrs(self):
        self.logger.info('Get common project atributes')

        self.common_prj_attrs = self.mqs['AVTG common prj attrs'].get()

        self.mqs['AVTG common prj attrs'].close()

    def get_hdr_arch(self):
        self.logger.info('Get architecture name to search for architecture specific header files')

        self.conf['header architecture'] = self.mqs['hdr arch'].get()

        self.mqs['hdr arch'].close()

        self.logger.debug('Architecture name to search for architecture specific header files is "{0}"'.format(
            self.conf['header architecture']))

    def get_src_tree_root(self):
        self.logger.info('Get source tree root')

        self.conf['source tree root'] = self.mqs['AVTG src tree root'].get()

        self.mqs['AVTG src tree root'].close()

        self.logger.debug('Source tree root is "{0}"'.format(self.conf['source tree root']))

    def generate_all_abstract_verification_task_descs(self):
        self.logger.info('Generate all abstract verification task decriptions')

        while True:
            verification_obj_desc = self.mqs['verification obj descs'].get()

            if verification_obj_desc is None:
                self.logger.debug('Verification object descriptions message queue was terminated')
                self.mqs['verification obj descs'].close()
                break

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

        self.plugins_work_dir = os.path.join(os.path.basename(self.conf['source tree root']),
                                             verification_obj_desc['id'], rule_spec_desc['id'])
        os.makedirs(self.plugins_work_dir, exist_ok=True)
        self.logger.debug('Plugins working directory is "{0}"'.format(self.plugins_work_dir))

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
        if self.conf['keep intermediate files']:
            initial_abstract_task_desc_file = os.path.join(self.plugins_work_dir, 'initial abstract task.json')
            if os.path.isfile(initial_abstract_task_desc_file):
                raise FileExistsError('Initial abstract verification task description file "{0}" already exists'.format(
                    initial_abstract_task_desc_file))
            self.logger.debug('Create initial abstract verification task description file "{0}"'.format(
                initial_abstract_task_desc_file))
            with open(initial_abstract_task_desc_file, 'w', encoding='ascii') as fp:
                json.dump(initial_abstract_task_desc, fp, sort_keys=True, indent=4)

        # Invoke all plugins one by one.
        cur_abstract_task_desc = initial_abstract_task_desc
        plugin_mqs = self.mqs
        plugin_mqs.update({'abstract task description': multiprocessing.Queue()})
        try:
            for plugin_desc in rule_spec_desc['plugins']:
                self.logger.info('Launch plugin {0}'.format(plugin_desc['name']))

                # Put either initial or current description of abstract verification task.
                plugin_mqs['abstract task description'].put(cur_abstract_task_desc)

                # Get plugin configuration on the basis of common configuration, plugin options specific for rule
                # specification and information on rule specification itself.
                plugin_conf = copy.deepcopy(self.conf)
                if 'options' in plugin_desc:
                    plugin_conf.update(plugin_desc['options'])
                plugin_conf.update({'rule spec id': rule_spec_desc['id']})
                if 'bug kinds' in rule_spec_desc:
                    plugin_conf.update({'bug kinds': rule_spec_desc['bug kinds']})

                p = plugin_desc['plugin'](plugin_conf, self.logger, self.id, self.callbacks, plugin_mqs, self.locks,
                                          '{0}/{1}/{2}'.format(*list(initial_attr_vals) + [plugin_desc['name']]),
                                          os.path.join(self.plugins_work_dir, plugin_desc['name'].lower()),
                                          initial_attrs, True, True)

                p.start()
                # See "Joining processes that use queues" in multiprocessing documentation.
                while True:
                    p.join(0.5)
                    try:
                        cur_abstract_task_desc = plugin_mqs['abstract task description'].get_nowait()
                        break
                    except queue.Empty:
                        # Complain just if plugin returns well.
                        if p.exitcode == 0:
                            raise RuntimeError(
                                '{0} did not put abstract verification task description back to queue on termination'.format(
                                    plugin_desc['name']))
                # Wait for plugin after it put abstract verification task description back to queue, in particular catch
                # exceptions that may happen.
                p.join()

                # Plugin working directory is created just if plugin starts successfully (above). So we can't dump
                # anything before.
                if self.conf['keep intermediate files']:
                    plugin_conf_file = os.path.join(self.plugins_work_dir, plugin_desc['name'].lower(), 'conf.json')
                    if os.path.isfile(plugin_conf_file):
                        raise FileExistsError('Plugins configuration file "{0}" already exists'.format(
                            plugin_conf_file))
                    self.logger.debug('Create plugins configuration file "{0}"'.format(plugin_conf_file))
                    with open(plugin_conf_file, 'w', encoding='ascii') as fp:
                        json.dump(plugin_conf, fp, sort_keys=True, indent=4)

                    cur_abstract_task_desc_file = os.path.join(self.plugins_work_dir, plugin_desc['name'].lower(),
                                                               'abstract task.json')
                    if os.path.isfile(cur_abstract_task_desc_file):
                        raise FileExistsError(
                            'Current abstract verification task description file "{0}" already exists'.format(
                                cur_abstract_task_desc_file))
                    self.logger.debug('Create current abstract verification task description file "{0}"'.format(
                        cur_abstract_task_desc_file))
                    with open(cur_abstract_task_desc_file, 'w', encoding='ascii') as fp:
                        json.dump(cur_abstract_task_desc, fp, sort_keys=True, indent=4)

            # Dump final abstract verification task description that equals to abstract verification task description
            # received from last plugin. But corresponding file will be put not to plugin working directory - it will
            # be put near initial abstract verification task description.
            if self.conf['keep intermediate files']:
                final_abstract_task_desc_file = os.path.join(self.plugins_work_dir,
                                                             'final abstract task.json')
                if os.path.isfile(final_abstract_task_desc_file):
                    raise FileExistsError(
                        'Final abstract verification task description file "{0}" already exists'.format(
                            final_abstract_task_desc_file))
                self.logger.debug('Create final abstract verification task description file "{0}"'.format(
                    final_abstract_task_desc_file))
                with open(final_abstract_task_desc_file, 'w', encoding='ascii') as fp:
                    json.dump(cur_abstract_task_desc, fp, sort_keys=True, indent=4)

            # VTG will consume this abstract verification task description.
            self.abstract_task_desc = cur_abstract_task_desc

            # Count the number of successfully generated abstract verification task descriptions.
            self.abstract_task_desc_num += 1
        # Failures in plugins aren't treated as the critical ones. We just warn and proceed to other
        # verification objects or/and rule specifications.
        except core.components.ComponentError:
            self.abstract_task_desc = None
        finally:
            plugin_mqs['abstract task description'].close()
