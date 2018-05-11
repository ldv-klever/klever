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

        with open(self.args.deployment_configuration_file) as fp:
            self.deploy_conf = json.load(fp)

        self.new_deploy_info_file = prev_deploy_info_file = os.path.join(self.args.deployment_directory, 'klever.json')
        if os.path.exists(prev_deploy_info_file):
            with open(prev_deploy_info_file) as fp:
                self.prev_deploy_info = json.load(fp)
        else:
            self.prev_deploy_info = None

        self.new_deploy_info = {}

    def __getattr__(self, name):
        raise NotImplementedKleverMode('You can not {0} Klever for "{1}"'.format(name, self.mode))

    def _dump_cur_deploy_info(self):
        os.makedirs(self.args.deployment_directory, exist_ok=True)

        with open(self.new_deploy_info_file, 'w') as fp:
            json.dump(self.new_deploy_info, fp, sort_keys=True, indent=4)

    def _pre_install(self):
        if self.prev_deploy_info:
            raise ValueError(
                'There is information on previous deployment (perhaps you try to install Klever second time)')

        self.new_deploy_info.update(install_deps(self.deploy_conf, self.prev_deploy_info, self.args.non_interactive))
        self._dump_cur_deploy_info()

    def _post_install(self):
        pass

    def _pre_update(self):
        if not self.prev_deploy_info:
            raise ValueError('There is not information on previous deployment ({0})'
                             .format('perhaps you try to update Klever without previous installation'))

        self.new_deploy_info.update(install_deps(self.deploy_conf, self.prev_deploy_info, self.args.non_interactive))
        self._dump_cur_deploy_info()


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

