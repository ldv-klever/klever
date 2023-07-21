# Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
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

import os

from klever.cli.utils import execute_cmd
from klever.cli.build.program import Program


class MakeProgram(Program):
    def _configure(self, *args):
        self.logger.info('Configure program')
        execute_cmd(self.logger, './configure', *args, cwd=self.work_src_tree)

    def _build(self, *target):
        self.logger.info('Build program')
        self._make(*target, intercept_build_cmds=True)

    def _clean(self):
        self.logger.info('Clean working source tree')
        self._make('clean')

    def _make(self, *target, opts=None, env=None, intercept_build_cmds=False, get_output=False):
        if opts is None:
            opts = []

        cmd = ['make', '-j', str(os.cpu_count())] + opts + list(target)

        if intercept_build_cmds:
            self.logger.info('Execute command "{0}" intercepting build commands'.format(' '.join(cmd)))
            # TODO: Add support of passing custom environment and capturing stdout with stderr
            r = self.clade.intercept(cmd, append=True, cwd=self.work_src_tree)

            if r:
                raise RuntimeError('Build failed')

            return r

        return execute_cmd(self.logger, *(cmd), cwd=self.work_src_tree, env=env, get_output=get_output)

    @Program.build_wrapper
    def build(self):
        self._prepare_work_src_tree()

        if self.version:
            self.logger.info(f'Program version is "{self.version}"')

        self._clean()
        self._configure()

        if self.configuration:
            self.logger.info(f'C program configuration is "{self.configuration}"')

        self._build()
        self._run_clade()
