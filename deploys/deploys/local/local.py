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

import json
import os

from deploys.install_deps import install_deps


class NotImplementedKleverMode(NotImplementedError):
    pass


class Klever:
    def __init__(self, args, logger):
        self.args = args
        self.logger = logger

        self.mode = args.mode
        self.prev_build_conf_file = os.path.join(self.args.build_directory, 'klever.json')
        self.build_conf = {}

    def __getattr__(self, name):
        raise NotImplementedKleverMode('You can not {0} Klever for "{1}"'.format(name, self.mode))

    def _pre_install(self):
        self.build_conf.update(install_deps(self.args.build_configuration_file, self.prev_build_conf_file,
                                            self.args.non_interactive))

    def _post_install(self):
        os.makedirs(os.path.dirname(self.prev_build_conf_file), exist_ok=True)

        with open(self.prev_build_conf_file, 'w') as fp:
            json.dump(self.build_conf, fp, sort_keys=True, indent=4)

    def _pre_update(self):
        if not os.path.isfile(self.prev_build_conf_file):
            raise FileNotFoundError(
                'There is not build configuration file "{0}" ({1})'
                .format(self.prev_build_conf_file, 'perhaps you try to update Klever without previous installation'))

        with open(self.prev_build_conf_file) as fp:
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

