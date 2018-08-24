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
import json
import shutil
import tarfile
import importlib
import subprocess
import urllib.parse
import clade.interface as clade_api

import core.utils


def get_source_adapter(project_kind):
    module_path = '.vog.source.{}'.format(project_kind.lower())
    project_package = importlib.import_module(module_path, 'core')
    cls = getattr(project_package, project_kind.capitalize())
    return cls


class Source:
    """This class to implement if necessary building and extraction of information from particular projects"""

    _CLADE_CONF = dict()
    _CMDS_FILE = 'cmds.txt'
    _ATTRS_FILE = 'source attrs.json'
    _SOURCE_PATH_FILE = 'source paths.json'

    def __init__(self, logger, conf):
        self.logger = logger
        self.conf = conf
        self.configuration = None
        self.version = None
        self.arch = self.conf['project'].get('architecture') or self.conf['architecture']
        self.workers = str(core.utils.get_parallel_threads_num(self.logger, self.conf, 'Build'))
        self.work_src_tree = None

        # For internal use
        self._source_paths = []
        self._model_headers_path = 'model-headers'
        self._clade_dir = self.conf['Clade']['base']
        self._build_flag = False
        self._clade = clade_api

        # This should be properly filles by an implementation
        self._subsystems = None
        self._targets = None

        # Add extra Clade options
        self._CLADE_CONF.update(self.conf['project'].get("extra Clade opts", dict()))

    @property
    def attributes(self):
        if not self._build_flag:
            return self._retrieve_attrs()
        else:
            attrs = [{'name': 'kind', 'value': type(self).__name__}]
            for att in ('arch', 'version', 'configuration'):
                if getattr(self, att):
                    attrs.append({"name": att, "value": getattr(self, att)})
            return [
                {
                    'name': 'project',
                    'value': attrs
                }
            ]

    @property
    def source_paths(self):
        if not self._build_flag:
            self._source_paths = self._retrieve_source_paths()
        return self._source_paths

    def check_target(self, candidate):
        if 'all' in self._subsystems:
            self._subsystems['all'] = True
            return True
        if 'all' in self._targets:
            self._targets['all'] = True
            return True
        return True

    def check_targets_consistency(self):
        for target in (t for t in self._targets if not self._targets[t]):
            raise ValueError("No verification objects generated for target {!r}: "
                             "check Clade base cache or job.json".format(target))
        for subsystem in (s for s in self._subsystems if not self._subsystems[s]):
            raise ValueError("No verification objects generated for directory {!r}: "
                             "check Clade base cache or job.json".format(subsystem))

    def configure(self):
        self.configuration = self.conf['project'].get('configuration')

    def build(self):
        if not self._build_flag:
            self._build_flag = True
        else:
            raise RuntimeError("Cannot build the program second time")
        self._build()
        clade_api.initialize_extensions(self._clade_dir, os.path.join(self.work_src_tree, 'cmds.txt'), self._CLADE_CONF)

        # Save properties to Clade storage
        storage = clade_api.FileStorage()
        for d, f in ((self.attributes, self._ATTRS_FILE), (self._source_paths, self._SOURCE_PATH_FILE)):
            with open(f, 'w', encoding='utf8') as fp:
                json.dump(d, fp)
            storage.save_file(f)

    def prepare_model_headers(self, model_headers):
        os.makedirs(self._model_headers_path)
        for c_file, headers in model_headers.items():
            self.logger.info('Copy headers for model with C file "{0}"'.format(c_file))
            model_headers_c_file = os.path.join(self._model_headers_path, os.path.basename(c_file))

            with open(model_headers_c_file, mode='w', encoding='utf8') as fp:
                for header in headers:
                    fp.write('#include <{0}>\n'.format(header))
        return None

    def _retrieve_attrs(self):
        clade_api.setup(self._clade_dir, self._CLADE_CONF)
        path = clade_api.FileStorage().convert_path(self._ATTRS_FILE)
        with open(path, 'r', encoding='utf8') as fp:
            attrs = json.load(fp)
        return attrs

    def _retrieve_source_paths(self):
        clade_api.setup(self._clade_dir, self._CLADE_CONF)
        path = clade_api.FileStorage().convert_path(self._SOURCE_PATH_FILE)
        with open(path, 'r', encoding='utf8') as fp:
            paths = json.load(fp)
        return paths

    def _build(self):
        raise NotImplementedError

    def _cleanup(self):
        cmds_file = os.path.join(self.work_src_tree, self._CMDS_FILE)
        if os.path.isfile(cmds_file):
            os.remove(cmds_file)

    def _make(self, target, opts=None, env=None, intercept_build_cmds=False, collect_all_stdout=False):
        return core.utils.execute(self.logger, (['clade-intercept'] if intercept_build_cmds else []) +
                                  ['make', '-j', self.workers] + opts + target,
                                  cwd=self.work_src_tree, env=env, collect_all_stdout=collect_all_stdout)

    def prepare_build_directory(self):
        try:
            src = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                              self.conf['project']['source'])
        except FileNotFoundError:
            # source code is not provided in form of file or directory.
            src = self.conf['project']['source']
        self.work_src_tree = self._fetch_work_src_tree(src, 'source', self.conf['project'].get('Git repository'),
                                                       self.conf['allow local source directories use'])
        self._source_paths.append(os.path.abspath(self.work_src_tree))
        self._make_canonical_work_src_tree()
        self._cleanup()

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
