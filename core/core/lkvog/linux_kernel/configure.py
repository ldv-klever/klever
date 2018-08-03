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

import hashlib
import os
import shutil

from core.lkvog.linux_kernel.make import make_linux_kernel


def configure_linux_kernel(logger, work_src_tree, jobs, arch, conf):
    logger.info('Configure Linux kernel')

    # Linux kernel configuration can be specified by means of configuration file or configuration target.
    if os.path.isfile(conf):
        logger.debug('Linux kernel configuration file is "{0}"'.format(conf))

        # Use configuration file SHA1 digest as Linux kernel configuration hash.
        with open(conf, 'rb') as fp:
            conf_hash = hashlib.sha1(fp.read()).hexdigest()[:7]

        logger.debug('Linux kernel configuration file SHA1 digest is "{0}"'.format(conf_hash))

        shutil.copy(conf, work_src_tree)

        target = ['oldconfig', 'KCONFIG_CONFIG={0}'.format(os.path.basename(conf))]
    else:
        logger.debug('Linux kernel configuration target is "{0}"'.format(conf))

        # Use configuration target as Linux kernel configuration hash.
        conf_hash = conf

        target = [conf]

    make_linux_kernel(logger, work_src_tree, jobs, arch, target)

    return conf_hash
