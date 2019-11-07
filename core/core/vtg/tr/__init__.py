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

import os

import jinja2

import core.vtg.plugins


class TR(core.vtg.plugins.Plugin):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False):
        super(TR, self).__init__(conf, logger, parent_id, callbacks, mqs, vals, id, work_dir, attrs,
                                 separate_from_parent, include_child_resources)

    def render_templates(self):
        if 'template context' not in self.abstract_task_desc:
            self.logger.warning('Template context is not specified (nothing to do)')
        elif not self.abstract_task_desc['template context']:
            self.logger.warning('Template context is empty (nothing to do)')
        elif not self.conf['templates']:
            self.logger.warning('Templates are not specified (nothing to do)')
        else:
            # Here files containing rendered templates will be stored.
            self.abstract_task_desc['files'] = []

            env = jinja2.Environment(
                # All templates reside in the same directory as specifications base.
                loader=jinja2.FileSystemLoader(os.path.dirname(self.conf['specifications base'])),
                # This allows to start template statements with the specified prefix rather than to put them inside
                # special "braces", e.g. in "{% ... %}" by default.
                # "//" is the beginning of one-line C/C++ comments, so editors will likely treat these lines as
                # comments if one will use C syntax highlighting.
                line_statement_prefix='//',
                # Remove excessive whitespaces. Users needn't know that they see on rendered templates.
                trim_blocks=True,
                lstrip_blocks=True,
                # Raise exception if some template value is undefined. This can happens if template or/and template
                # context is incorrect.
                undefined=jinja2.StrictUndefined
            )

            for tmpl in self.conf['templates']:
                self.logger.info('Render template "{0}"'.format(tmpl))

                # It is assumed that all templates have suffix ".tmpl" and some meaningful suffix before it, e.g. ".c"
                # or ".aspect". Rendered templates will be stored into files without suffix ".tmpl" and one will be able
                # to understand what are these files by inspecting remaining suffixes.
                file = os.path.splitext(tmpl)[0]

                # Rendered templates will be placed into files inside TR working directory.
                os.makedirs(os.path.dirname(file).encode('utf8'), exist_ok=True)
                with open(file, 'w', encoding='utf8') as fp:
                    fp.write(env.get_template(tmpl).render(
                        self.abstract_task_desc['template context'][os.path.splitext(os.path.basename(file))[0]]))

                self.abstract_task_desc['files'].append(
                    os.path.relpath(file, self.conf['main working directory']))

                self.logger.debug('Rendered template was stored into file "{0}"'.format(file))

            self.abstract_task_desc.pop('template context')

    main = render_templates
