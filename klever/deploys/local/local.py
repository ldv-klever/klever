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

import errno
import json
import os
import pwd
import shutil
import subprocess
import sys

from klever.deploys.configure_controller_and_schedulers import configure_controller_and_schedulers
from klever.deploys.install_deps import install_deps
from klever.deploys.install_klever_bridge import install_klever_bridge_development, install_klever_bridge_production
from klever.deploys.prepare_env import prepare_env
from klever.deploys.utils import execute_cmd, install_klever_addons, install_klever_build_bases, \
    need_verifiercloud_scheduler, start_services, stop_services, get_media_user, replace_media_user


class Klever:
    def __init__(self, args, logger):
        self.args = args
        self.logger = logger

        self.prev_deploy_info_file = os.path.join(self.args.deployment_directory, 'klever.json')
        if os.path.exists(self.prev_deploy_info_file):
            with open(self.prev_deploy_info_file) as fp:
                self.prev_deploy_info = json.load(fp)
        else:
            self.prev_deploy_info = {}

    def __getattr__(self, name):
        self.logger.error('Action "{0}" is not supported for Klever "{1}"'.format(name, self.args.mode))
        sys.exit(errno.ENOSYS)

    def _cmd_fn(self, *args):
        execute_cmd(self.logger, *args)

    def _install_fn(self, src, dst, allow_symlink=False, ignore=None):
        if ignore and allow_symlink:
            self.logger.error('You can not both use symbolic links and ignore some directories')
            sys.exit(errno.EINVAL)

        self.logger.info('Install "{0}" to "{1}"'.format(src, dst))

        os.makedirs(dst if os.path.isdir(dst) else os.path.dirname(dst), exist_ok=True)

        if allow_symlink and self.args.allow_symbolic_links:
            execute_cmd(self.logger, 'ln', '-s', src, dst)
        else:
            if os.path.isdir(src):
                shutil.copytree(src, dst, symlinks=True, ignore=lambda source, names: ignore or [])
            else:
                shutil.copy(src, dst)

    def _dump_cur_deploy_info(self, cur_deploy_info):
        with open(self.prev_deploy_info_file, 'w') as fp:
            json.dump(cur_deploy_info, fp, sort_keys=True, indent=4)

    def _pre_install_or_update(self):
        install_klever_addons(self.logger, self.args.source_directory, self.args.deployment_directory, self.deploy_conf,
                              self.prev_deploy_info, self._cmd_fn, self._install_fn, self._dump_cur_deploy_info)
        install_klever_build_bases(self.logger, self.args.source_directory,
                                   os.path.join(self.args.deployment_directory, 'klever'),
                                   self.deploy_conf, self._cmd_fn, self._install_fn)

    def _install_or_update_deps(self):
        install_deps(self.logger, self.deploy_conf, self.prev_deploy_info, self.args.non_interactive,
                     self.args.update_packages)
        self._dump_cur_deploy_info(self.prev_deploy_info)

    def _pre_install(self):
        if self.prev_deploy_info:
            self.logger.error(
                'There is information on previous deployment (perhaps you try to install Klever second time)')
            sys.exit(errno.EINVAL)

        with open(self.args.deployment_configuration_file) as fp:
            self.deploy_conf = json.load(fp)

        self.logger.info('Create deployment directory')
        os.makedirs(self.args.deployment_directory, exist_ok=True)

        with open('/etc/default/klever', 'w') as fp:
            fp.write('KLEVER_SOURCE_DIRECTORY="{0}"\n'.format(os.path.realpath(self.args.source_directory)))
            fp.write('KLEVER_DEPLOYMENT_DIRECTORY="{0}"\n'.format(os.path.realpath(self.args.deployment_directory)))
            fp.write('KLEVER_DATA_DIR="{0}"\n'
                     .format(os.path.join(os.path.realpath(self.args.deployment_directory), 'klever', 'build bases')
                             if len(self.deploy_conf['Klever Build Bases'])
                             else os.path.join(os.path.realpath(self.args.source_directory), 'build bases')))
            fp.write("KLEVER_WORKERS={}\n".format(os.cpu_count() + 1))
            fp.write("KLEVER_PYTHON_BIN_DIR={}\n".format(os.path.dirname(sys.executable)))
            fp.write("KLEVER_PYTHON={}\n".format(sys.executable))

        media_user = get_media_user(self.logger)

        self.logger.info('Install systemd configuration files and services')
        execute_cmd(self.logger, 'mkdir', '-p', '/etc/conf.d')
        for dirpath, _, filenames in os.walk(os.path.join(os.path.dirname(__file__), os.path.pardir,
                                                          'systemd', 'conf.d')):
            for filename in filenames:
                shutil.copy(os.path.join(dirpath, filename), os.path.join('/etc/conf.d', filename))

        for dirpath, _, filenames in os.walk(os.path.join(os.path.dirname(__file__), os.path.pardir,
                                                          'systemd', 'tmpfiles.d')):
            for filename in filenames:
                shutil.copy(os.path.join(dirpath, filename), os.path.join('/etc/tmpfiles.d', filename))
                replace_media_user(os.path.join('/etc/tmpfiles.d', filename), media_user)

        for dirpath, _, filenames in os.walk(os.path.join(os.path.dirname(__file__), os.path.pardir,
                                                          'systemd', 'system')):
            for filename in filenames:
                shutil.copy(os.path.join(dirpath, filename), os.path.join('/etc/systemd/system', filename))
                replace_media_user(os.path.join('/etc/systemd/system', filename), media_user)

        self._install_or_update_deps()
        prepare_env(self.logger, self.args.deployment_directory)
        self._pre_install_or_update()

    def _pre_update(self):
        if not self.prev_deploy_info:
            self.logger.error('There is not information on previous deployment ({0})'
                              .format('perhaps you try to update Klever without previous installation'))
            sys.exit(errno.EINVAL)

        with open(self.args.deployment_configuration_file) as fp:
            self.deploy_conf = json.load(fp)

        self._install_or_update_deps()
        self._pre_install_or_update()

    def _pre_uninstall(self, mode_services):
        services = list(mode_services)
        services.extend(('klever-controller', 'klever-native-scheduler', 'klever-cgroup'))

        if need_verifiercloud_scheduler(self.prev_deploy_info):
            services.append('klever-verifiercloud-scheduler')

        stop_services(self.logger, services, ignore_errors=True)

        self.logger.info('Uninstall systemd services')
        for dirpath, _, filenames in os.walk('/etc/systemd/system'):
            for filename in filenames:
                if filename.startswith('klever'):
                    service = os.path.join(dirpath, filename)
                    self.logger.info('Remove "{0}"'.format(service))
                    os.remove(service)

        klever_env_file = '/etc/default/klever'
        if os.path.exists(klever_env_file):
            self.logger.info('Remove "{0}"'.format(klever_env_file))
            os.remove(klever_env_file)

        # Remove bridge files
        bridge_path = os.path.join(self.args.deployment_directory, 'klever/bridge/bridge')
        for path in ('settings.py', 'db.json', 'rmq.json'):
            path = os.path.join(bridge_path, path)

            if os.path.exists(path):
                self.logger.info('Remove "{0}"'.format(path))
                os.remove(path)

        # Removing individual directories and files rather than the whole deployment directory allows to use standard
        # locations like "/", "/usr" or "/usr/local" for deploying Klever.
        for path in (
                'klever',
                'klever-addons',
                'klever-conf',
                'klever-work',
                'klever-media',
                'klever.json'
        ):
            path = os.path.join(self.args.deployment_directory, path)
            if os.path.exists(path) or os.path.islink(path):
                self.logger.info('Remove "{0}"'.format(path))
                if os.path.islink(path) or os.path.isfile(path):
                    os.remove(path)
                else:
                    shutil.rmtree(path)

        # Remove deployment directory if it is empty
        if os.path.exists(self.args.deployment_directory) and not os.listdir(self.args.deployment_directory):
            self.logger.info('Remove "{0}"'.format(self.args.deployment_directory))
            os.rmdir(self.args.deployment_directory)

        # Remove Klever Bridge NGINX configuration if so.
        if os.path.exists('/etc/nginx/sites-enabled/klever-bridge.conf'):
            os.remove('/etc/nginx/sites-enabled/klever-bridge.conf')
        elif os.path.exists('/etc/nginx/conf.d/klever-bridge.conf'):
            os.remove('/etc/nginx/conf.d/klever-bridge.conf')
        stop_services(self.logger, ('nginx',))
        start_services(self.logger, ('nginx',))

        try:
            pwd.getpwnam('postgres')
        except KeyError:
            # Do nothing if user "postgres" does not exist.
            pass
        else:
            self.logger.info('Delete PostgreSQL database')
            execute_cmd(self.logger, 'dropdb', '--if-exists', 'klever', username='postgres')

            self.logger.info('Delete PostgreSQL user')
            execute_cmd(self.logger, 'psql', '-c', "DROP USER IF EXISTS klever", username='postgres')

        try:
            pwd.getpwnam('klever')
        except KeyError:
            # Do nothing if user "klever" does not exist.
            pass
        else:
            self.logger.info('Delete user "klever"')
            execute_cmd(self.logger, 'userdel', 'klever')

        try:
            self.logger.info('Delete RabbitMQ user')
            execute_cmd(self.logger, 'rabbitmqctl', 'delete_user', 'service')
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

    def _post_install_or_update(self, is_dev=False):
        configure_controller_and_schedulers(self.logger, is_dev, self.args.source_directory,
                                            self.args.deployment_directory, self.prev_deploy_info)


class KleverDevelopment(Klever):
    def __init__(self, args, logger):
        super().__init__(args, logger)

    def _install_or_update(self):
        install_klever_bridge_development(self.logger, self.args.source_directory)

    def install(self):
        self._pre_install()
        self._install_or_update()
        self._post_install_or_update(is_dev=True)

    def update(self):
        self._pre_update()
        self._install_or_update()
        self._post_install_or_update(is_dev=True)

    def uninstall(self):
        self._pre_uninstall((
            'klever-bridge-development',
            'klever-celery-development',
            'klever-celerybeat-development'
        ))


class KleverProduction(Klever):
    # This allows to install development version of schedulers within deploys.local.local.KleverTesting without
    # redefining methods.
    _IS_DEV = False

    def __init__(self, args, logger):
        super().__init__(args, logger)

    def _install_or_update(self):
        install_klever_bridge_production(self.logger, self.args.source_directory, self.args.deployment_directory,
                                         not self._IS_DEV)

    def install(self):
        self._pre_install()
        execute_cmd(self.logger, 'systemd-tmpfiles', '--create')
        self._install_or_update()
        self._post_install_or_update(self._IS_DEV)

    def update(self):
        self._pre_update()
        self._install_or_update()
        self._post_install_or_update(self._IS_DEV)

    def uninstall(self):
        self._pre_uninstall(('nginx', 'klever-bridge', 'klever-celery', 'klever-celerybeat'))

        for nginx_bridge_conf_file in ('/etc/nginx/sites-enabled/klever-bridge', '/etc/nginx/conf.d/klever-bridge'):
            if os.path.exists(nginx_bridge_conf_file):
                self.logger.info('Remove Klever Bridge configuration file for NGINX')
                os.remove(nginx_bridge_conf_file)

        klever_bridge_dir = '/var/www/klever-bridge'
        if os.path.exists(klever_bridge_dir):
            self.logger.info('Remove Klever Bridge source/binary code')
            shutil.rmtree(klever_bridge_dir)


class KleverTesting(KleverProduction):
    _IS_DEV = True

    def __init__(self, args, logger):
        super().__init__(args, logger)

        # Always install/update Klever for testing non-interactively.
        args.non_interactive = True
