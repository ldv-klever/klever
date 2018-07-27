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

import subprocess


# TODO: this extension will be redundant if all commented code will be removed.
def clean_linux_kernel_work_src_tree(logger, work_src_tree):
    logger.info('Clean Linux kernel working source tree')

    # TODO: I hope that we won't build external modules within Linux kernel working source tree anymore.
    # if os.path.isdir(os.path.join(work_src_tree, 'ext-modules')):
    #     shutil.rmtree(os.path.join(work_src_tree, 'ext-modules'))

    # TODO: this optimization shouldn't be needed.
    # if self.linux_kernel['prepared to build ext modules']:
    #     return

    # TODO: this command can fail but most likely this shouldn't be an issue.
    subprocess.check_call(('make', 'mrproper'), cwd=work_src_tree)

    # TODO: I am almost sure that we don't need this anymore.
    # Remove intermediate files and directories that could be created during previous run.
    # if self.ext_conf.get('use original source tree'):
    #     for dirpath, dirnames, filenames in os.walk(work_src_tree):
    #         for filename in filenames:
    #             if re.search(r'\.json$', filename):
    #                 os.remove(os.path.join(dirpath, filename))
    #         for dirname in dirnames:
    #             if re.search(r'\.task$', dirname):
    #                 shutil.rmtree(os.path.join(dirpath, dirname))
