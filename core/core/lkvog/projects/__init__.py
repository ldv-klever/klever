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

import os
import shutil
import tarfile
import importlib
import subprocess
import urllib.parse

import core.utils


def get_source_adapter(project_kind):
    project_kind = '.lkvog.projects.{}'.format(project_kind.capitalize())
    project_representation = importlib.import_module(project_kind, 'core')
    return project_representation


class Project:
    """This class to implement if necessary building and extraction of information from particular projects"""

    def __init__(self, logger, conf):
        self.logger = logger
        self.conf = conf
        self.configuration = None
        self.version = None
        self.arch = self.conf['project']['source'].get('architecture') or self.conf['architecture']
        self.workers = str(core.utils.get_parallel_threads_num(self.logger, self.conf, 'Build'))
        self._prepare_working_directory()

    @property
    def attributes(self):
        raise NotImplementedError

    def configure(self):
        if 'configuration' in self.conf['project']:
            try:
                self.configuration = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                                 self.conf['project']['configuration'])
            except FileNotFoundError:
                # Linux kernel configuration is not provided in form of file.
                self.configuration = self.conf['project']['configuration']

    def build(self, modules_to_build, model_headers, complete_build=False):
        raise NotImplementedError

    def cleanup(self):
        pass

    def _make(self, target, opts=None, env=None, intercept_build_cmds=False, collect_all_stdout=False):
        return core.utils.execute(self.logger, (['clade-intercept'] if intercept_build_cmds else []) +
                                  ['make', '-j', self.workers] + opts + target,
                                  cwd=self.work_src_tree, env=env, collect_all_stdout=collect_all_stdout)

    def _prepare_working_directory(self):
        try:
            src = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                              self.conf['build']['source'])
        except FileNotFoundError:
            # source code is not provided in form of file or directory.
            src = self.conf['project']['source']
        self.work_src_tree, self.version = \
            self._fetch_work_src_tree(src, 'source', self.conf['project'].get('Git repository'),
                                      self.conf['allow local source directories use'])
        self._make_canonical_work_src_tree()
        self.cleanup()

    def _fetch_work_src_tree(self, src, work_src_tree, git_repo, use_orig_src_tree):
        self.logger.info('Fetch source code from "{0}" to working source tree "{1}"'.format(src, work_src_tree))
        o = urllib.parse.urlparse(src)
        if o[0] in ('http', 'https', 'ftp'):
            raise NotImplementedError('Source code is provided in unsupported form of remote archive')
        elif o[0] == 'git':
            raise NotImplementedError('Source code is provided in unsupported form of remote Git repository')
        elif o[0]:
            raise ValueError('Source code is provided in unsupported form "{0}"'.format(o[0]))

        git_commit_hash = None
        if os.path.isdir(src):
            if use_orig_src_tree:
                self.logger.info('Use original source tree "{0}" rather than fetch it to working source tree "{1}"'
                                 .format(src, work_src_tree))
                work_src_tree = os.path.realpath(src)
            else:
                shutil.copytree(src, work_src_tree, symlinks=True)

            if os.path.isdir(os.path.join(src, '.git')):
                self.logger.debug("Source code is provided in form of Git repository")
            else:
                self.logger.debug("Source code is provided in form of source tree")

            # TODO: do not allow to checkout both branch and commit and to checkout branch or commit for source tree.
            if git_repo:
                for commit_or_branch in ('commit', 'branch'):
                    if commit_or_branch in git_repo:
                        self.logger.info('Checkout Git repository {0} "{1}"'.format(commit_or_branch,
                                                                                    git_repo[commit_or_branch]))
                        # Always remove Git repository lock file .git/index.lock if it exists since it can remain after
                        # some previous Git commands crashed. Isolating several instances of Klever Core working with
                        # the same Linux kernel source code should be done somehow else in a more generic way.
                        git_index_lock = os.path.join(work_src_tree, '.git', 'index.lock')
                        if os.path.isfile(git_index_lock):
                            os.remove(git_index_lock)
                        # In case of dirty Git working directory checkout may fail so clean up it first.
                        subprocess.check_call(('git', 'clean', '-f', '-d'), cwd=work_src_tree)
                        subprocess.check_call(('git', 'reset', '--hard'), cwd=work_src_tree)
                        subprocess.check_call(('git', 'checkout', '-f', git_repo[commit_or_branch]), cwd=work_src_tree)

                        # Use 12 first symbols of current commit hash to properly identify Linux kernel version.
                        stdout = core.utils.execute(self.logger, ('git', 'rev-parse', 'HEAD'), cwd=work_src_tree,
                                                    collect_all_stdout=True)
                        git_commit_hash = stdout[0][0:12]
        elif os.path.isfile(src):
            self.logger.debug('Source code is provided in form of archive')
            with tarfile.open(src, encoding='utf8') as TarFile:
                TarFile.extractall(work_src_tree)

        self.version = git_commit_hash
        return work_src_tree

    def _make_canonical_work_src_tree(self):
        def _is_src_tree_root(fnames):
            for filename in fnames:
                if filename == 'Makefile':
                    return True

            return False

        self.logger.info('Make canonical working source tree "{0}"'.format(self.work_src_tree))

        work_src_tree_root = None
        for dirpath, _, filenames in os.walk(self.work_src_tree):
            if _is_src_tree_root(filenames):
                work_src_tree_root = dirpath
                break

        if not work_src_tree_root:
            raise ValueError('Could not find Makefile in working source tree "{0}"'.format(self.work_src_tree))

        if os.path.samefile(work_src_tree_root, self.work_src_tree):
            return

        self.logger.debug('Move contents of "{0}" to "{1}"'.format(work_src_tree_root, self.work_src_tree))
        for path in os.listdir(work_src_tree_root):
            shutil.move(os.path.join(work_src_tree_root, path), self.work_src_tree)
        trash_dir = work_src_tree_root
        while True:
            parent_dir = os.path.join(trash_dir, os.path.pardir)
            if os.path.samefile(parent_dir, self.work_src_tree):
                break
            trash_dir = parent_dir
        self.logger.debug('Remove "{0}"'.format(trash_dir))
        shutil.rmtree(os.path.realpath(trash_dir))
