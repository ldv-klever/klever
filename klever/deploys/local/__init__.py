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

import argparse
import errno
import os
import sys

from klever.deploys.local.local import Klever, KleverDevelopment, KleverProduction, KleverTesting
from klever.deploys.utils import check_deployment_configuration_file, get_logger, get_cgroup_version


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'update', 'reinstall', 'uninstall'],
                        help='Action to be executed.')
    parser.add_argument('mode', choices=['development', 'production', 'testing'], nargs='?', default='production',
                        help='Mode for which action to be executed (default: "%(default)s").')
    parser.add_argument('--non-interactive', default=False, action='store_true',
                        help='Install/update packages non-interactively (default: "%(default)s"). ' +
                             'This option has no effect for mode "testing".')
    parser.add_argument('--deployment-configuration-file',
                        default=os.path.join(os.path.dirname(__file__), os.path.pardir, 'conf', 'klever.json'),
                        help='Path to Klever deployment configuration file (default: "%(default)s").')
    parser.add_argument('--source-directory', default=os.getcwd(),
                        help='Path to Klever source directory (default: "%(default)s").')
    parser.add_argument('--deployment-directory', required=True, help='Path to Klever deployment directory.')
    parser.add_argument('--data-directory', help='Path to directory where Klever will search for build bases. Please,' +
                                                 ' use this option carefully since it will abandon any deployed build' +
                                                 ' bases if so.')
    parser.add_argument('--update-packages', default=False, action='store_true',
                        help='Update packages for action "update" (default: "%(default)s"). ' +
                             'This option has no effect for action "install".')
    parser.add_argument('--update-python3-packages', default=False, action='store_true',
                        help='Update Python3 packages for action "update" (default: "%(default)s"). ' +
                             'This option has no effect for action "install".')
    parser.add_argument('--allow-symbolic-links', default=False, action='store_true',
                        help='Use symbolic links to directories (Klever addons and build bases) rather than copy them' +
                             ' (default: "%(default)s"). Please, use this option very carefully to avoid dangling' +
                             ' symbolic links as well as unexpected changes in their targets. Indeed this option is' +
                             ' intended to update Klever addons and build bases silently without using deployment' +
                             ' scripts.')
    parser.add_argument('--log-level', default='INFO', metavar='LEVEL',
                        help='Set logging level to LEVEL (INFO or DEBUG).')
    parser.add_argument('--install-only-klever-addons', default=False, action='store_true',
                        help='Install only Klever addons and skip most parts of deployment (default: "%(default)s"). ' +
                             'This option may be necessary for very specific conditions, e.g. for generating build' +
                             ' bases using Dockerfile.build-bases.')
    args = parser.parse_args()

    logger = get_logger(__name__, args.log_level)

    check_deployment_configuration_file(logger, args.deployment_configuration_file)

    if get_cgroup_version() != "v1":
        logger.error('It appears that you are using cgroup v2, which is not supported by Klever')
        logger.error('To revert the systemd configuration to use cgroup v1 run the following command and reboot:')
        logger.error('\tsudo grubby --update-kernel=ALL --args="systemd.unified_cgroup_hierarchy=0"')
        sys.exit(-1)

    # Returns either mode of previous deployment or unchanged value of args.mode
    args.mode = Klever(args, logger).get_deployment_mode()

    logger.info('Start execution of action "{0}" in "{1}" mode'.format(args.action, args.mode))

    try:
        if args.mode == 'development':
            getattr(KleverDevelopment(args, logger), args.action)()
        elif args.mode == 'production':
            getattr(KleverProduction(args, logger), args.action)()
        elif args.mode == 'testing':
            getattr(KleverTesting(args, logger), args.action)()
        else:
            logger.error('Mode "{0}" is not supported'.format(args.mode))
            sys.exit(errno.ENOSYS)
    except SystemExit:
        logger.error('Could not execute action "{0}" in "{1}" mode (analyze error messages above for details)'
                     .format(args.action, args.mode))
        raise

    logger.info('Finish execution of action "{0}" in "{1}" mode'.format(args.action, args.mode))
