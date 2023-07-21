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
import shutil
import subprocess
import urllib.parse

from clade import Clade

from klever.cli.utils import execute_cmd


class Program:
    _CLADE_CONF = {}
    _CLADE_PRESET = "base"

    def __init__(self, logger, target_program_desc):
        self.logger = logger
        self.target_program_desc = target_program_desc

        # Main working source tree where various build and auxiliary actions will be performed.
        self.work_src_tree = self.target_program_desc['source code']

        # Program attributes. We expect that architecture is always specified in the target program description while
        # configuration and version can be either obtained during build somehow or remained unspecified.
        self.architecture = self.target_program_desc['architecture']
        self.configuration = None
        self.version = self.target_program_desc.get('version')

        # Working source trees are directories to be trimmed from file names.
        self.work_src_trees = []
        # Temporary directories that should be removed at the end of work.
        self.tmp_dirs = []

        # Path to the Clade cmds.txt file with intercepted commands
        self.cmds_file = os.path.realpath(os.path.join(self.work_src_tree, 'cmds.txt'))

        # Clade API object
        clade_conf = dict(self._CLADE_CONF)
        clade_conf.update(self.target_program_desc.get('extra Clade options', {}))
        # Testing and validation build bases are pretty small, so we can request Clade to generate graphs for them.
        clade_conf.update({
            'CmdGraph.as_picture': True,
            'PidGraph.as_picture': True
        })
        self.clade = Clade(work_dir=self.target_program_desc['build base'],
                           cmds_file=self.cmds_file,
                           conf=clade_conf,
                           preset=self._CLADE_PRESET)

    def _prepare_work_src_tree(self):
        o = urllib.parse.urlparse(self.work_src_tree)
        if o[0] in ('http', 'https', 'ftp'):
            raise NotImplementedError('Source code is provided in unsupported form of a remote archive')
        if o[0] == 'git':
            raise NotImplementedError('Source code is provided in unsupported form of a remote Git repository')
        if o[0]:
            raise ValueError('Source code is provided in unsupported form "{0}"'.format(o[0]))

        if os.path.isfile(self.work_src_tree):
            raise NotImplementedError('Source code is provided in unsupported form of an archive')

        # Local git repository
        if os.path.isdir(os.path.join(self.work_src_tree, '.git')):
            self.logger.debug("Source code is provided in form of a Git repository")
            self.__prepare_git_work_src_tree()

        self.work_src_trees.append(os.path.realpath(self.work_src_tree))

    def __prepare_git_work_src_tree(self):
        if 'git repository version' not in self.target_program_desc:
            return

        checkout = self.target_program_desc['git repository version']
        self.logger.info(f'Checkout Git repository "{checkout}"')

        # Repository lock file may remain from some previous crashed git command
        git_index_lock = os.path.join(self.work_src_tree, '.git', 'index.lock')
        if os.path.isfile(git_index_lock):
            os.remove(git_index_lock)

        # In case of dirty Git working directory checkout may fail so clean up it first.
        execute_cmd(self.logger, 'git', 'clean', '-f', '-d', cwd=self.work_src_tree)
        execute_cmd(self.logger, 'git', 'reset', '--hard', cwd=self.work_src_tree)
        execute_cmd(self.logger, 'git', 'checkout', '-f', checkout, cwd=self.work_src_tree)

        try:
            # Use Git describe to properly identify program version
            stdout = execute_cmd(self.logger, 'git', 'describe', cwd=self.work_src_tree, get_output=True)
            self.version = stdout[0]
        except subprocess.CalledProcessError:
            # Use Git repository version from target program description if Git describe failed
            self.version = checkout

    def _run_clade(self):
        if os.path.isdir(self.target_program_desc['build base']):
            shutil.rmtree(self.target_program_desc['build base'])

        self.clade.parse_list(self.clade.conf['extensions'])

        self.logger.info('Save project attributes, working source trees and target program description to build base')
        attrs = [
            {
                'name': 'name',
                'value': type(self).__name__
            },
            {
                'name': 'architecture',
                'value': self.architecture
            },
            {
                'name': 'version',
                'value': self.version
            }
        ]
        if self.configuration:
            attrs.append({
                'name': 'configuration',
                'value': self.configuration
            })
        self.clade.add_meta_by_key('project attrs', [{
            'name': 'project',
            'value': attrs
        }])
        self.clade.add_meta_by_key('working source trees', self.work_src_trees)
        self.clade.add_meta_by_key('target program description', self.target_program_desc)

        # Keep file with intercepted build commands within generated build base.
        if os.path.exists(self.cmds_file):
            shutil.move(self.cmds_file, self.target_program_desc['build base'])

    @staticmethod
    def build_wrapper(build):
        '''Wrapper for build() method'''
        def wrapper(self, *args, **kwargs):
            try:
                return build(self, *args, **kwargs)
            finally:
                for tmp_dir in self.tmp_dirs:
                    self.logger.info(f'Remove temporary directory "{tmp_dir}"')
                    shutil.rmtree(tmp_dir)

                if os.path.exists(self.cmds_file):
                    os.remove(self.cmds_file)

        return wrapper

    def build(self):
        ...
