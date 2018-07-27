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
import subprocess
import tarfile
import urllib.parse


def fetch_work_src_tree(logger, src, work_src_tree, git_repo, use_orig_src_tree):
    logger.info('Fetch source code from "{0}" to working source tree "{1}"'.format(src, work_src_tree))

    o = urllib.parse.urlparse(src)
    if o[0] in ('http', 'https', 'ftp'):
        raise NotImplementedError('Source code is provided in unsupported form of remote archive')
    elif o[0] == 'git':
        raise NotImplementedError('Source code is provided in unsupported form of remote Git repository')
    elif o[0]:
        raise ValueError('Source code is provided in unsupported form "{0}"'.format(o[0]))

    if os.path.isdir(src):
        if use_orig_src_tree:
            logger.info('Use original source tree "{0}" rather than fetch it to working source tree "{1}"'
                         .format(src, work_src_tree))
            work_src_tree = os.path.realpath(src)
        else:
            shutil.copytree(src, work_src_tree, symlinks=True)

        if os.path.isdir(os.path.join(src, '.git')):
            logger.debug("Source code is provided in form of Git repository")
        else:
            logger.debug("Source code is provided in form of source tree")

        # TODO: do not allow to checkout both branch and commit and to checkout branch or commit for source tree.
        if git_repo:
            for commit_or_branch in ('commit', 'branch'):
                if commit_or_branch in git_repo:
                    logger.info('Checkout Git repository {0} "{1}"'.
                                 format(commit_or_branch,
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
    elif os.path.isfile(src):
        logger.debug('Source code is provided in form of archive')
        with tarfile.open(src, encoding='utf8') as TarFile:
            TarFile.extractall(work_src_tree)

    return work_src_tree
