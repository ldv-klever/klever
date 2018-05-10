#!/usr/bin/env python3
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
import json
import logging
import os
import sys

from deploys.install_deps import install_deps


class NotImplementedKleverMode(NotImplementedError):
    pass


class Klever:
    def __init__(self, args, logger):
        self.args = args
        self.logger = logger

        self.mode = args.mode
        self.build_conf_file = os.path.join(self.args.build_directory, 'klever.json')
        self.build_conf = None

    def __getattr__(self, name):
        raise NotImplementedKleverMode('You can not {0} Klever for "{1}"'.format(name, self.mode))

    def _pre_install(self):
        install_deps(self.args.build_configuration_file, self.build_conf_file, self.args.non_interactive)

    def _post_install(self):
        os.makedirs(os.path.dirname(self.build_conf_file), exist_ok=True)

        with open(self.build_conf_file, 'w') as fp:
            json.dump(self.build_conf, fp, sort_keys=True, indent=4)

    def _pre_update(self):
        if not os.path.isfile(self.build_conf_file):
            raise FileNotFoundError(
                'There is not build configuration file "{0}" ({1})'
                .format(self.build_conf_file, 'perhaps you try to update Klever without previous installation'))

        with open(self.build_conf_file) as fp:
            self.build_conf = json.load(fp)


class KleverDevelopment(Klever):
    def __init__(self, args, logger):
        super().__init__(args, logger)

    def install(self):
        self._pre_install()
        self._post_install()

    def update(self):
        self._pre_update()


class KleverProduction(Klever):
    def __init__(self, args, logger):
        super().__init__(args, logger)

    def install(self):
        self._pre_install()
        self._post_install()

    def update(self):
        self._pre_update()


class KleverTesting(Klever):
    def __init__(self, args, logger):
        super().__init__(args, logger)

        # Always install/update Klever for testing non-interactively.
        args.non_interactive = False

    def install(self):
        self._pre_install()
        self._post_install()

    def update(self):
        self._pre_update()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'update'], help='Action to be executed.')
    parser.add_argument('mode', choices=['development', 'production', 'testing'],
                        help='Mode for which action to be executed.')
    parser.add_argument('--non-interactive', default=False, action='store_true',
                        help='Install/update standard packages non-interactively (default: "%(default)s"). ' +
                             'This option has no effect for mode testing.')
    parser.add_argument('--build-configuration-file', default=os.path.join(os.path.dirname(__file__), os.path.pardir,
                                                                           'conf', 'klever.json'),
                        help='Path to Klever build configuration file (default: "%(default)s").')
    parser.add_argument('--build-directory', default=os.path.join(os.path.dirname(__file__), os.path.pardir, 'build'),
                        help='Path to Klever build directory (default: "%(default)s").')
    parser.add_argument('--aaa', required=True)
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
    elif args.entity == 'production':
        getattr(KleverProduction(args, logger), args.action)()
    elif args.entity == 'testing':
        getattr(KleverTesting(args, logger), args.action)()
    else:
        raise NotImplementedError('Mode "{0}" is not supported'.format(args.mode))
