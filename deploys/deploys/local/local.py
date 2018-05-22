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
import shutil

from deploys.configure_controller_and_schedulers import configure_controller_and_schedulers, \
                                                        configure_native_scheduler_task_worker
from deploys.install_deps import install_deps
from deploys.install_klever_bridge import install_klever_bridge
from deploys.prepare_env import prepare_env
from deploys.utils import execute_cmd, get_password, install_extra_dep_or_program, install_extra_deps, install_programs


class NotImplementedKleverMode(NotImplementedError):
    pass


class Klever:
    def __init__(self, args, logger):
        self.args = args
        self.logger = logger

        self.is_update = {
            'Klever': False,
            'Controller & Schedulers': False,
            'Verification Backends': False
        }

        with open(self.args.deployment_configuration_file) as fp:
            self.deploy_conf = json.load(fp)

        os.makedirs(self.args.deployment_directory, exist_ok=True)

        self.prev_deploy_info_file = os.path.join(self.args.deployment_directory, 'klever.json')
        if os.path.exists(self.prev_deploy_info_file):
            with open(self.prev_deploy_info_file) as fp:
                self.prev_deploy_info = json.load(fp)
        else:
            self.prev_deploy_info = {}

    def __getattr__(self, name):
        raise NotImplementedKleverMode('You can not {0} Klever for "{1}"'.format(name, self.args.mode))

    def _dump_cur_deploy_info(self):
        with open(self.prev_deploy_info_file, 'w') as fp:
            json.dump(self.prev_deploy_info, fp, sort_keys=True, indent=4)

    def _pre_do_install_or_update(self):
        install_deps(self.deploy_conf, self.prev_deploy_info, self.args.non_interactive)
        self._dump_cur_deploy_info()

        def cmd_fn(logger, *args):
            execute_cmd(logger, *args)

        def install_fn(logger, src, dst):
            logger.info('Install "{0}" to "{1}"'.format(src, dst))

            os.makedirs(dst if os.path.isdir(dst) else os.path.dirname(dst), exist_ok=True)

            if os.path.isdir(src):
                shutil.copytree(src, dst, symlinks=True)
            else:
                shutil.copy(src, dst)

        self.is_update['Klever'] = install_extra_dep_or_program(self.logger, 'Klever',
                                                                os.path.join(self.args.deployment_directory, 'klever'),
                                                                self.deploy_conf, self.prev_deploy_info,
                                                                cmd_fn, install_fn)
        try:
            self.is_update['Controller & Schedulers'], self.is_update['Verification Backends'] = \
                install_extra_deps(self.logger, self.args.deployment_directory, self.deploy_conf, self.prev_deploy_info,
                                   cmd_fn, install_fn)
        # Without this we won't store information on successfully installed/updated extra dependencies and following
        # installation/update will fail.
        finally:
            self._dump_cur_deploy_info()

        try:
            install_programs(self.logger, self.args.username, self.args.deployment_directory, self.deploy_conf,
                             self.prev_deploy_info, cmd_fn, install_fn)
        # Like above.
        finally:
            self._dump_cur_deploy_info()

    def _pre_install(self):
        if self.prev_deploy_info:
            raise ValueError(
                'There is information on previous deployment (perhaps you try to install Klever second time)')

        self._pre_do_install_or_update()

    def _pre_update(self):
        if not self.prev_deploy_info:
            raise ValueError('There is not information on previous deployment ({0})'
                             .format('perhaps you try to update Klever without previous installation'))

        self._pre_do_install_or_update()

    def _install(self):
        psql_user_passwd = get_password(self.logger, 'PostgreSQL user password (it will be stored as plaintext!): ')
        self.prev_deploy_info['PostgreSQL user password'] = psql_user_passwd
        self._dump_cur_deploy_info()

        prepare_env(self.args.mode, self.args.username, self.args.deployment_directory, psql_user_passwd)

        self.logger.info('Install init.d scripts')
        for dirpath, _, filenames in os.walk(os.path.join(os.path.dirname(__file__),  os.path.pardir, os.path.pardir,
                                                          'init.d')):
            for filename in filenames:
                shutil.copy(os.path.join(dirpath, filename), os.path.join('/etc/init.d', filename))
                execute_cmd(self.logger, 'update-rc.d', filename, 'defaults')

        with open('/etc/default/klever', 'w') as fp:
            fp.write('KLEVER_DEPLOYMENT_DIRECTORY={0}\nKLEVER_USERNAME={1}\n'
                     .format(os.path.realpath(self.args.deployment_directory), self.args.username))

    def _post_do_install_or_update(self):
        if self.is_update['Klever']:
            install_klever_bridge(self.args.action, self.args.mode, self.args.deployment_directory,
                                  self.prev_deploy_info['PostgreSQL user password'])

        if self.is_update['Klever'] or self.is_update['Controller & Schedulers']:
            configure_controller_and_schedulers(self.args.mode, self.args.deployment_directory, self.prev_deploy_info)

        if self.is_update['Verification Backends'] and not self.is_update['Klever'] \
                and not self.is_update['Controller & Schedulers']:
            # It is enough to reconfigure controller and schedulers since they automatically reread
            # configuration files holding changes of verification backends.
            configure_native_scheduler_task_worker(self.args.mode, self.args.deployment_directory,
                                                   self.prev_deploy_info)

    def _post_install(self):
        self._post_do_install_or_update()

    def _post_update(self):
        self._post_do_install_or_update()


class KleverDevelopment(Klever):
    def __init__(self, args, logger):
        super().__init__(args, logger)

    def install(self):
        self._pre_install()
        self._install()
        self._post_install()

    def update(self):
        self._pre_update()
        self._post_update()


class KleverProduction(Klever):
    def __init__(self, args, logger):
        super().__init__(args, logger)

    def install(self):
        self._pre_install()
        self._install()
        self._post_install()

    def update(self):
        self._pre_update()
        self._post_update()


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
