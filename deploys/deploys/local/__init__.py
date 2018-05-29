#
# Copyright (c) 2018 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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
import logging
import os
import sys

from deploys.local.local import KleverDevelopment, KleverProduction, KleverTesting


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'update'], help='Action to be executed.')
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
    # Do not suggest information on current user since it will be root rather than normal one.
    parser.add_argument('--username', required=True, help='Klever username.')
    parser.add_argument('--update-packages', default=False, action='store_true',
                        help='Update packages for action "update" (default: "%(default)s"). ' +
                             'This option has no effect for action "install".')
    parser.add_argument('--update-python3-packages', default=False, action='store_true',
                        help='Update Python3 packages for action "update" (default: "%(default)s"). ' +
                             'This option has no effect for action "install".')
    args = parser.parse_args()

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s (%(filename)s:%(lineno)03d) %(levelname)s> %(message)s',
                                  "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    logger.info('{0} Klever for {1}'.format(args.action.capitalize(), args.mode))

    if args.mode == 'development':
        getattr(KleverDevelopment(args, logger), args.action)()
    elif args.mode == 'production':
        getattr(KleverProduction(args, logger), args.action)()
    elif args.mode == 'testing':
        getattr(KleverTesting(args, logger), args.action)()
    else:
        raise NotImplementedError('Mode "{0}" is not supported'.format(args.mode))
