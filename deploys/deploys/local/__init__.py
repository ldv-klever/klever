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

from deploys.local.local import KleverDevelopment, KleverProduction, KleverTesting
from deploys.utils import check_deployment_configuration_file, get_logger, update_python_path


def main():
    update_python_path()

    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'update', 'uninstall'], help='Action to be executed.')
    parser.add_argument('mode', choices=['development', 'production', 'testing'],
                        help='Mode for which action to be executed.')
    parser.add_argument('--non-interactive', default=False, action='store_true',
                        help='Install/update packages non-interactively (default: "%(default)s"). ' +
                             'This option has no effect for mode "testing".')
    parser.add_argument('--deployment-configuration-file',
                        default=os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir, 'conf',
                                             'klever.json'),
                        help='Path to Klever deployment configuration file (default: "%(default)s").')
    parser.add_argument('--deployment-directory', required=True, help='Path to Klever deployment directory.')
    parser.add_argument('--update-packages', default=False, action='store_true',
                        help='Update packages for action "update" (default: "%(default)s"). ' +
                             'This option has no effect for action "install".')
    parser.add_argument('--update-python3-packages', default=False, action='store_true',
                        help='Update Python3 packages for action "update" (default: "%(default)s"). ' +
                             'This option has no effect for action "install".')
    parser.add_argument('--allow-symbolic-links', default=False, action='store_true',
                        help='Use symbolic links to directories (Klever addons and programs) rather than copy them' +
                             ' (default: "%(default)s"). Please, use this option very carefully to avoid dangling' +
                             ' symbolic links as well as unexpected changes in their targets. Indeed this option is' +
                             ' intended to update Klever addons and programs silently without using deployment' +
                             ' scripts.')
    args = parser.parse_args()

    logger = get_logger(__name__)

    check_deployment_configuration_file(logger, args.deployment_configuration_file)

    logger.info('Start execution of action "{0}" for Klever "{1}"'.format(args.action, args.mode))

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
        logger.error('Could not execute action "{0}" for Klever "{1}" (analyze error messages above for details)'
                     .format(args.action, args.mode))
        raise

    logger.info('Finish execution of action "{0}" for Klever "{1}"'.format(args.action, args.mode))
