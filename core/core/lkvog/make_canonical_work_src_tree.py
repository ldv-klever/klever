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


def make_canonical_work_src_tree(logger, work_src_tree):
    logger.info('Make canonical working source tree "{0}"'.format(work_src_tree))

    work_src_tree_root = None
    for dirpath, _, filenames in os.walk(work_src_tree):
        if _is_src_tree_root(filenames):
            work_src_tree_root = dirpath
            break

    if not work_src_tree_root:
        raise ValueError('Could not find Makefile in working source tree "{0}"'.format(work_src_tree))

    if os.path.samefile(work_src_tree_root, work_src_tree):
        return

    logger.debug('Move contents of "{0}" to "{1}"'.format(work_src_tree_root, work_src_tree))
    for path in os.listdir(work_src_tree_root):
        shutil.move(os.path.join(work_src_tree_root, path), work_src_tree)
    trash_dir = work_src_tree_root
    while True:
        parent_dir = os.path.join(trash_dir, os.path.pardir)
        if os.path.samefile(parent_dir, work_src_tree):
            break
        trash_dir = parent_dir
    logger.debug('Remove "{0}"'.format(trash_dir))
    shutil.rmtree(os.path.realpath(trash_dir))


def _is_src_tree_root(filenames):
    for filename in filenames:
        if filename == 'Makefile':
            return True

    return False
