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

import errno
import json
import os
import shutil
import sys

from deploys.configure_controller_and_schedulers import configure_controller_and_schedulers, \
                                                        configure_native_scheduler_task_worker
from deploys.install_deps import install_deps
from deploys.install_klever_bridge import install_klever_bridge_development, install_klever_bridge_production
from deploys.prepare_env import prepare_env
from deploys.utils import execute_cmd, install_extra_dep_or_program, install_extra_deps, install_programs, \
                          need_verifiercloud_scheduler, stop_services


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

        self.prev_deploy_info_file = os.path.join(self.args.deployment_directory, 'klever.json')
        if os.path.exists(self.prev_deploy_info_file):
            with open(self.prev_deploy_info_file) as fp:
                self.prev_deploy_info = json.load(fp)
        else:
            self.prev_deploy_info = {}

    def __getattr__(self, name):
        self.logger.error('You can not {0} Klever for "{1}"'.format(name, self.args.mode))
        sys.exit(errno.ENOSYS)

    def _dump_cur_deploy_info(self):
        with open(self.prev_deploy_info_file, 'w') as fp:
            json.dump(self.prev_deploy_info, fp, sort_keys=True, indent=4)

    def _pre_do_install_or_update(self):
        def cmd_fn(*args):
            execute_cmd(self.logger, *args)

        def install_fn(src, dst, allow_symlink=False):
            self.logger.info('Install "{0}" to "{1}"'.format(src, dst))

            os.makedirs(dst if os.path.isdir(dst) else os.path.dirname(dst), exist_ok=True)

            if allow_symlink and self.args.allow_symbolic_links:
                execute_cmd(self.logger, 'ln', '-s', src, dst)
            else:
                if os.path.isdir(src):
                    shutil.copytree(src, dst, symlinks=True)
                else:
                    shutil.copy(src, dst)

        self.is_update['Klever'] = install_extra_dep_or_program(self.logger, 'Klever',
                                                                os.path.join(self.args.deployment_directory, 'klever'),
                                                                self.deploy_conf, self.prev_deploy_info,
                                                                cmd_fn, install_fn)
        if self.is_update['Klever']:
            self._dump_cur_deploy_info()

        try:
            self.is_update['Controller & Schedulers'], self.is_update['Verification Backends'] = \
                install_extra_deps(self.logger, self.args.deployment_directory, self.deploy_conf, self.prev_deploy_info,
                                   cmd_fn, install_fn)
        # Without this we won't store information on successfully installed/updated extra dependencies and following
        # installation/update will fail.
        finally:
            if self.is_update['Controller & Schedulers'] or self.is_update['Verification Backends']:
                self._dump_cur_deploy_info()

        is_update_programs = False
        try:
            is_update_programs = install_programs(self.logger, self.args.username, self.args.deployment_directory,
                                                  self.deploy_conf, self.prev_deploy_info, cmd_fn, install_fn)
        # Like above.
        finally:
            if is_update_programs:
                self._dump_cur_deploy_info()

    def _install_or_update_deps(self):
        install_deps(self.logger, self.deploy_conf, self.prev_deploy_info, self.args.non_interactive,
                     self.args.update_packages, self.args.update_python3_packages)
        self._dump_cur_deploy_info()

    def _pre_install(self):
        if os.path.exists(self.args.deployment_directory):
            self.logger.error('Deployment directory "{0}" already exists'.format(self.args.deployment_directory))
            sys.exit(errno.ENOTEMPTY)

        if self.prev_deploy_info:
            self.logger.error(
                'There is information on previous deployment (perhaps you try to install Klever second time)')
            sys.exit(errno.EINVAL)

        self.logger.info('Create deployment directory')
        os.makedirs(self.args.deployment_directory)

        self.logger.info('Install init.d scripts')
        for dirpath, _, filenames in os.walk(os.path.join(os.path.dirname(__file__),  os.path.pardir, os.path.pardir,
                                                          'init.d')):
            for filename in filenames:
                shutil.copy(os.path.join(dirpath, filename), os.path.join('/etc/init.d', filename))
                execute_cmd(self.logger, 'update-rc.d', filename, 'defaults')

        with open('/etc/default/klever', 'w') as fp:
            fp.write('KLEVER_DEPLOYMENT_DIRECTORY={0}\nKLEVER_USERNAME={1}\n'
                     .format(os.path.realpath(self.args.deployment_directory), self.args.username))

        self._install_or_update_deps()
        prepare_env(self.logger, self.args.username, self.args.deployment_directory)
        self._pre_do_install_or_update()

    def _pre_update(self):
        if not self.prev_deploy_info:
            self.logger.error('There is not information on previous deployment ({0})'
                              .format('perhaps you try to update Klever without previous installation'))
            sys.exit(errno.EINVAL)

        self._install_or_update_deps()
        self._pre_do_install_or_update()

    def _pre_uninstall(self, mode_services):
        services = list(mode_services)
        services.extend(('klever-controller', 'klever-native-scheduler'))

        if need_verifiercloud_scheduler(self.deploy_conf):
            services.append('klever-verifiercloud-scheduler')

        stop_services(self.logger, services, ignore_errors=True)

        self.logger.info('Uninstall init.d scripts')
        for dirpath, _, filenames in os.walk('/etc/init.d'):
            for filename in filenames:
                if filename.startswith('klever'):
                    execute_cmd(self.logger, 'update-rc.d', filename, 'disable')
                    os.unlink(os.path.join('/etc/init.d', filename))
        if os.path.exists('/etc/default/klever'):
            os.unlink('/etc/default/klever')

        if os.path.exists(self.args.deployment_directory):
            self.logger.info('Remove deployment directory')
            shutil.rmtree(self.args.deployment_directory)

        # TODO: do not do this if user "postgres" does not exist.
        self.logger.info('Drop PostgreSQL database')
        execute_cmd(self.logger, 'dropdb', '--if-exists', 'klever', username='postgres')

        self.logger.info('Drop PostgreSQL user')
        execute_cmd(self.logger, 'psql', '-c', "DROP USER IF EXISTS klever", username='postgres')

        # Do not remove user since this can result in bad consequences.

    def _post_install_or_update(self):
        if self.is_update['Klever'] or self.is_update['Controller & Schedulers']:
            configure_controller_and_schedulers(self.logger, self.args.mode, self.args.deployment_directory,
                                                self.prev_deploy_info)

        if self.is_update['Verification Backends'] and not self.is_update['Klever'] \
                and not self.is_update['Controller & Schedulers']:
            # It is enough to reconfigure controller and schedulers since they automatically reread
            # configuration files holding changes of verification backends.
            configure_native_scheduler_task_worker(self.logger, self.args.mode, self.args.deployment_directory,
                                                   self.prev_deploy_info)


class KleverDevelopment(Klever):
    def __init__(self, args, logger):
        super().__init__(args, logger)

    def _install_or_update(self):
        if self.is_update['Klever']:
            install_klever_bridge_development(self.logger, self.args.deployment_directory)

    def install(self):
        self._pre_install()
        self._install_or_update()
        self._post_install_or_update()

    def update(self):
        self._pre_update()
        self._install_or_update()
        self._post_install_or_update()

    def uninstall(self):
        self._pre_uninstall(('klever-bridge-development',))


class KleverProduction(Klever):
    def __init__(self, args, logger):
        super().__init__(args, logger)

    def _install_or_update(self):
        if self.is_update['Klever']:
            install_klever_bridge_production(self.logger, self.args.deployment_directory)

    def install(self):
        self._pre_install()
        self._install_or_update()
        self._post_install_or_update()

    def update(self):
        self._pre_update()
        self._install_or_update()
        self._post_install_or_update()

    def uninstall(self):
        self._pre_uninstall(('nginx', 'klever-bridge'))

        nginx_klever_bridge_conf_file = '/etc/nginx/sites-enabled/klever-bridge'
        if os.path.exists(nginx_klever_bridge_conf_file):
            self.logger.info('Remove Klever Bridge configuration file for NGINX')
            os.remove(nginx_klever_bridge_conf_file)

        klever_bridge_dir = '/var/www/klever-bridge'
        if os.path.exists(klever_bridge_dir):
            self.logger.info('Remove Klever Bridge source/binary code')
            shutil.rmtree(klever_bridge_dir)


class KleverTesting(KleverProduction):
    def __init__(self, args, logger):
        super().__init__(args, logger)

        # Always install/update Klever for testing non-interactively.
        args.non_interactive = False
