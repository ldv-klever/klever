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
import pathlib
import pwd
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import zipfile

from clade import Clade

from klever.deploys.configure_controller_and_schedulers import configure_controller_and_schedulers
from klever.deploys.install_deps import install_deps
from klever.deploys.install_klever_bridge import install_klever_bridge_development, install_klever_bridge_production
from klever.deploys.prepare_env import prepare_env
from klever.deploys.utils import execute_cmd, need_verifiercloud_scheduler, start_services, stop_services, \
    get_media_user, replace_media_user, make_canonical_path, get_klever_version


class Klever:
    def __init__(self, args, logger):
        self.args = args
        self.logger = logger

        self.version_file = os.path.join(self.args.deployment_directory, 'version')
        self.prev_deploy_info_file = os.path.join(self.args.deployment_directory, 'klever.json')
        if os.path.exists(self.prev_deploy_info_file):
            with open(self.prev_deploy_info_file) as fp:
                self.prev_deploy_info = json.load(fp)
        else:
            self.prev_deploy_info = {"mode": self.args.mode}

        # Do not remove addons and build bases during reinstall action.
        self.keep_addons_and_build_bases = False

    def get_deployment_mode(self):
        return self.prev_deploy_info.get("mode", self.args.mode)

    def __getattr__(self, name):
        self.logger.error('Action "{0}" is not supported for Klever "{1}"'.format(name, self.args.mode))
        sys.exit(errno.ENOSYS)

    def _cmd_fn(self, *args):
        execute_cmd(self.logger, *args)

    def _install_fn(self, src, dst, allow_symlink=False, ignore=None):
        if ignore and allow_symlink:
            self.logger.error('You can not both use symbolic links and ignore some directories')
            sys.exit(errno.EINVAL)

        self.logger.info(f'Install "{src}" to "{dst}"')

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
        self._install_klever_addons(self.args.source_directory, self.args.deployment_directory)
        self._install_klever_build_bases(self.args.source_directory, self.args.deployment_directory)

        # (Re)set environment variable JAVA to point out absolute path to Java executable to be used for executing Java
        # programs within Klever. At the moment the same Java will be used for all Java programs but that may be changed
        # in future.
        with open('/etc/default/klever') as fp:
            klever_defaults = fp.readlines()

        with open('/etc/default/klever', 'w') as fp:
            for line in klever_defaults:
                if not line.startswith('JAVA'):
                    fp.write(line)

            fp.write("JAVA={}\n".format(
                os.path.join(os.path.realpath(self.args.deployment_directory), 'klever-addons', 'JRE',
                             self.prev_deploy_info['Klever Addons']['JRE']['executable path'], 'java')))

        try:
            version = get_klever_version()
        except Exception:
            self.logger.exception('Could not get Klever version')
            version = ''

        with open(self.version_file, 'w') as fp:
            fp.write(version)

    def _install_klever_addons(self, src_dir, deploy_dir):
        deploy_addons_conf = self.deploy_conf['Klever Addons']

        if 'Klever Addons' not in self.prev_deploy_info:
            self.prev_deploy_info['Klever Addons'] = {}

        prev_deploy_addons_conf = self.prev_deploy_info['Klever Addons']

        for addon in deploy_addons_conf:
            if addon == 'Verification Backends':
                if 'Verification Backends' not in prev_deploy_addons_conf:
                    prev_deploy_addons_conf['Verification Backends'] = {}

                for verification_backend in deploy_addons_conf['Verification Backends']:
                    backend_deploy_dir = os.path.join(deploy_dir, 'klever-addons', 'verification-backends',
                                                      verification_backend)
                    if self._install_entity(verification_backend, src_dir, backend_deploy_dir,
                                            deploy_addons_conf['Verification Backends'],
                                            prev_deploy_addons_conf['Verification Backends']):
                        self._dump_cur_deploy_info(self.prev_deploy_info)
            else:
                addon_deploy_dir = os.path.join(deploy_dir, 'klever-addons', addon)
                if self._install_entity(addon, src_dir, addon_deploy_dir, deploy_addons_conf,
                                        prev_deploy_addons_conf):
                    self._dump_cur_deploy_info(self.prev_deploy_info)

    def _install_klever_build_bases(self, src_dir, deploy_dir):
        for klever_build_base in self.deploy_conf['Klever Build Bases']:
            base_deploy_dir = os.path.join(deploy_dir, 'build bases', klever_build_base)

            # _install_entity method expects configuration in a specific format
            deploy_bases_conf = self.deploy_conf['Klever Build Bases']
            deploy_bases_conf[klever_build_base]['version'] = self.__get_build_base_version(klever_build_base)

            if 'Klever Build Bases' not in self.prev_deploy_info:
                self.prev_deploy_info['Klever Build Bases'] = {}

            prev_deploy_bases_conf = self.prev_deploy_info['Klever Build Bases']

            if self._install_entity(klever_build_base, src_dir, base_deploy_dir,
                                    deploy_bases_conf, prev_deploy_bases_conf, build_base=True):
                build_base_path = self.__find_build_base(base_deploy_dir)

                if build_base_path != base_deploy_dir:
                    paths_to_remove = [os.path.join(base_deploy_dir, i) for i in os.listdir(base_deploy_dir)]

                    self.logger.debug(f'Move "{klever_build_base}" from {build_base_path} to {base_deploy_dir}')
                    for i in os.listdir(build_base_path):
                        # In theory, it is possible to get "shutil.Error: Destination path already exists" here.
                        # But, it can only happen if the top-level directory inside the archive with the build base
                        # was named as some directory from the Clade build base (CC, LD, CrossRef, ...)
                        shutil.move(os.path.join(build_base_path, i), base_deploy_dir)

                    for path in paths_to_remove:
                        shutil.rmtree(path)

                self._dump_cur_deploy_info(self.prev_deploy_info)

    def _install_entity(self, name, src_dir, deploy_dir, deploy_conf, prev_deploy_info, build_base=False):
        if name not in deploy_conf:
            self.logger.error(f'"{name}" is not described')
            sys.exit(errno.EINVAL)

        deploy_dir = os.path.normpath(deploy_dir)

        desc = deploy_conf[name]

        if 'version' not in desc:
            self.logger.error(f'Version is not specified for "{name}"')
            sys.exit(errno.EINVAL)

        version = desc['version']

        if 'path' not in desc:
            self.logger.error(f'Path is not specified for "{name}"')
            sys.exit(errno.EINVAL)

        path = desc['path']
        o = urllib.parse.urlparse(path)
        if not o[0]:
            path = make_canonical_path(src_dir, path)

        refs = {}
        try:
            ref_strs = execute_cmd(self.logger, 'git', 'ls-remote', '--refs', path, stderr=subprocess.DEVNULL,
                                   get_output=True).rstrip().split('\n')
            is_git_repo = True
            for ref_str in ref_strs:
                commit, ref = ref_str.split('\t')
                refs[ref] = commit
        except subprocess.CalledProcessError:
            is_git_repo = False

        if is_git_repo and version != 'CURRENT':
            # Version can be either some reference or commit hash. In the former case we need to get corresponding
            # commit hash since it can differ from the previous one installed before for the same reference. In the
            # latter case we will fail below one day if commit hash isn't valid.
            # Note that here we can use just Git commands working with remote repositories since we didn't clone them
            # yet and we don't want do this if update isn't necessary.
            for prefix in ('refs/heads/', 'refs/tags/'):
                if prefix + version in refs:
                    version = refs[prefix + version]
                    break

        prev_version = prev_deploy_info[name]['version'] if name in prev_deploy_info else None

        if version == prev_version and version != 'CURRENT':
            self.logger.info(f'"{name}" is up to date (version: "{version}")')
            return False

        entity_kind = "Klever build base" if build_base else "Klever addon"

        if prev_version:
            self.logger.info(f'Update {entity_kind} "{name}" from version "{prev_version}" to version "{version}"')
        else:
            self.logger.info(f'Install {entity_kind} "{name}" (version: "{version}")')

        # Remove previous version of entity if so. Do not make this in depend on previous version since it can be unset
        # while entity is deployed. For instance, this can be the case when entity deployment fails somewhere in the
        # middle.
        self._cmd_fn('rm', '-rf', deploy_dir)

        # Install new version of entity.
        tmp_file = None
        tmp_dir = None
        try:
            instance_path = os.path.join(deploy_dir, os.path.basename(path))

            # Clone remote Git repository.
            if (o[0] == 'git' or is_git_repo) and not os.path.exists(path):
                tmp_dir = tempfile.mkdtemp()
                execute_cmd(self.logger, 'git', 'clone', '-q', '--recursive', path, tmp_dir)
                path = tmp_dir
            # Download remote file.
            elif o[0] in ('http', 'https', 'ftp'):
                _, tmp_file = tempfile.mkstemp()
                execute_cmd(self.logger, 'wget', '-O', tmp_file, '-q', path)
                path = tmp_file
            elif o[0]:
                self.logger.error(f'"{name}" is provided in unsupported form "{o[0]}"')
                sys.exit(errno.EINVAL)
            elif not os.path.exists(path):
                self.logger.error(f'Path "{path}" does not exist')
                sys.exit(errno.ENOENT)

            if is_git_repo:
                if version == 'CURRENT':
                    self._install_fn(path, deploy_dir, allow_symlink=True)
                else:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        # Checkout specified version within local Git repository if this is allowed or clone local Git
                        # repository to temporary directory and checkout specified version there.
                        if desc.get('allow use local Git repository'):
                            tmp_path = path
                            execute_cmd(self.logger, 'git', '-C', tmp_path, 'checkout', '-fq', version)
                            execute_cmd(self.logger, 'git', '-C', tmp_path, 'clean', '-xfdq')
                        else:
                            tmp_path = os.path.join(tmpdir, os.path.basename(os.path.realpath(path)))
                            execute_cmd(self.logger, 'git', 'clone', '-q', path, tmp_path)
                            execute_cmd(self.logger, 'git', '-C', tmp_path, 'checkout', '-q', version)

                        # Directory .git can be quite large so ignore it during installing except one needs it.
                        self._install_fn(tmp_path, deploy_dir,
                                         ignore=None if desc.get('copy .git directory') else ['.git'])
            elif os.path.isfile(path) and (tarfile.is_tarfile(path) or zipfile.is_zipfile(path)):
                os.makedirs(deploy_dir, exist_ok=True)

                if tarfile.is_tarfile(path):
                    self._cmd_fn('tar', '--warning', 'no-unknown-keyword', '-C', '{0}'.format(deploy_dir), '-xf', path)
                else:
                    self._cmd_fn('unzip', '-u', '-d', '{0}'.format(deploy_dir), path)
            elif os.path.isfile(path):
                self._install_fn(path, instance_path, allow_symlink=True)
            elif os.path.isdir(path):
                self._install_fn(path, deploy_dir, allow_symlink=True)
            else:
                self.logger.error(f'Could not install "{name}" since it is provided in the unsupported format')
                sys.exit(errno.ENOSYS)

            # Remember what entity was installed just if everything went well.
            prev_deploy_info[name] = {
                'version': version,
                'directory': deploy_dir
            }
            for attr in ('name', 'executable path', 'python path'):
                if attr in desc:
                    prev_deploy_info[name][attr] = desc[attr]

            return True
        finally:
            if tmp_file:
                os.unlink(tmp_file)
            if tmp_dir:
                shutil.rmtree(tmp_dir)

    def _install_or_update_deps(self):
        install_deps(self.logger, self.deploy_conf, self.prev_deploy_info, self.args.non_interactive,
                     self.args.update_packages)
        self._dump_cur_deploy_info(self.prev_deploy_info)

    def _pre_install(self):
        if os.path.exists(self.prev_deploy_info_file) and not self.keep_addons_and_build_bases:
            self.logger.error(
                'There is information on previous deployment (perhaps you try to install Klever second time)')
            sys.exit(errno.EINVAL)

        with open('/etc/default/klever', 'w') as fp:
            fp.write('KLEVER_SOURCE_DIRECTORY="{0}"\n'.format(os.path.realpath(self.args.source_directory)))
            fp.write('KLEVER_DEPLOYMENT_DIRECTORY="{0}"\n'.format(os.path.realpath(self.args.deployment_directory)))
            fp.write('KLEVER_DATA_DIR="{0}"\n'
                     .format(os.path.realpath(self.args.data_directory)
                             if self.args.data_directory
                             else os.path.join(os.path.realpath(self.args.deployment_directory), 'build bases')))
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
        if not os.path.exists(self.prev_deploy_info_file):
            self.logger.error('There is no information on previous deployment ({0})'
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
                    self.logger.debug('Remove "{0}"'.format(service))
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
        paths_to_remove = [
            'klever',
            'klever-conf',
            'klever-work',
            'klever-media',
            'version'
        ]

        if not self.keep_addons_and_build_bases:
            paths_to_remove.extend([
                'klever-addons',
                'build bases',
                'klever.json'
            ])

        self.logger.info(f'Remove files inside deployment directory "{self.args.deployment_directory}"')
        for path in paths_to_remove:
            path = os.path.join(self.args.deployment_directory, path)
            if os.path.exists(path) or os.path.islink(path):
                self.logger.debug('Remove "{0}"'.format(path))
                if os.path.islink(path) or os.path.isfile(path):
                    os.remove(path)
                else:
                    shutil.rmtree(path)

        # Remove deployment directory if it is empty
        if os.path.exists(self.args.deployment_directory) and not os.listdir(self.args.deployment_directory):
            self.logger.info('Remove "{0}"'.format(self.args.deployment_directory))
            os.rmdir(self.args.deployment_directory)

        # Remove Klever Bridge NGINX configuration if so.
        for klever_bridge_nginx_conf_file in ('/etc/nginx/sites-enabled/klever-bridge.conf',
                                              '/etc/nginx/conf.d/klever-bridge.conf'):
            if os.path.exists(klever_bridge_nginx_conf_file):
                self.logger.info('Remove "{0}"'.format(klever_bridge_nginx_conf_file))
                os.remove(klever_bridge_nginx_conf_file)
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

        # Try to remove httpd_t from the list of permissive domains.
        try:
            execute_cmd(self.logger, 'semanage', 'permissive', '-d', 'httpd_t', stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _post_install_or_update(self, is_dev=False):
        configure_controller_and_schedulers(self.logger, is_dev, self.args.source_directory,
                                            self.args.deployment_directory, self.prev_deploy_info)

    def __get_build_base_version(self, klever_build_base):
        version = self.deploy_conf['Klever Build Bases'][klever_build_base].get('version')

        if version:
            return version

        klever_build_base_path = self.deploy_conf['Klever Build Bases'][klever_build_base]['path']

        if os.path.isfile(klever_build_base_path):
            # Use md5 checksum of the archive as version
            output = execute_cmd(self.logger, 'md5sum', klever_build_base_path, stderr=subprocess.DEVNULL,
                                 get_output=True).rstrip()
            version = output.split(' ')[0]
        elif os.path.isdir(klever_build_base_path):
            # Use unique identifier of the build base as version
            try:
                version = Clade(klever_build_base_path).get_uuid()
            except RuntimeError:
                self.logger.error(f'"{klever_build_base}" is not a valid Clade build base')
                sys.exit(errno.EINVAL)
        else:
            # Otherwise build base is probably a link to the remote file
            # Our build bases are mostly stored at redmine, which has unique links
            # Here we use this link as version
            version = klever_build_base_path

        return version

    def __find_build_base(self, deploy_dir):
        build_bases = self.__find_build_bases_recursive(deploy_dir)

        if len(build_bases) == 0:
            self.logger.error(f'No build bases were found in "{deploy_dir}"')
            sys.exit(errno.ENOENT)
        elif len(build_bases) > 1:
            self.logger.error(f'Multiple build bases were found in "{deploy_dir}"')
            sys.exit(errno.ENOENT)

        return str(build_bases[0].resolve())

    def __find_build_bases_recursive(self, deploy_dir):
        deploy_dir = pathlib.Path(deploy_dir)

        build_bases = []

        if Clade(deploy_dir).work_dir_ok():
            return [deploy_dir]

        for file in deploy_dir.glob("*"):
            if not file.is_dir():
                continue

            if Clade(file).work_dir_ok():
                build_bases.append(file)
            else:
                build_bases.extend(self.__find_build_bases_recursive(file))

        return build_bases

    def reinstall(self):
        self.keep_addons_and_build_bases = True
        self.uninstall()
        self.install()


class KleverDevelopment(Klever):
    def __init__(self, args, logger):
        super().__init__(args, logger)

    def install(self):
        with open(self.args.deployment_configuration_file) as fp:
            self.deploy_conf = json.load(fp)

        self.logger.info('Create deployment directory')
        os.makedirs(self.args.deployment_directory, exist_ok=True)

        if self.args.install_only_klever_addons:
            with open('/etc/default/klever', 'w') as fp:
                fp.write('KLEVER_DEPLOYMENT_DIRECTORY="{0}"\n'.format(os.path.realpath(self.args.deployment_directory)))

            self._install_klever_addons(self.args.source_directory, self.args.deployment_directory)
        else:
            self._pre_install()
            install_klever_bridge_development(self.logger, self.args.source_directory)
            self._post_install_or_update(is_dev=True)

    def update(self):
        self._pre_update()
        install_klever_bridge_development(self.logger, self.args.source_directory, update=True)
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

    def install(self):
        self._pre_install()
        execute_cmd(self.logger, 'systemd-tmpfiles', '--create')
        install_klever_bridge_production(self.logger, self.args.source_directory, self.args.deployment_directory,
                                         not self._IS_DEV)
        self._post_install_or_update(self._IS_DEV)

    def update(self):
        self._pre_update()
        install_klever_bridge_production(self.logger, self.args.source_directory, self.args.deployment_directory,
                                         not self._IS_DEV, update=True)
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
