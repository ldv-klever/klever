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
import getpass
import json
import logging
import os
import pwd
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import zipfile


class Cd:
    def __init__(self, path):
        self.new_path = path

    def __enter__(self):
        self.prev_path = os.getcwd()
        os.chdir(self.new_path)

    def __exit__(self, etype, value, traceback):
        os.chdir(self.prev_path)


def execute_cmd(logger, *args, stdin=None, stderr=None, get_output=False, username=None):
    logger.info('Execute command "{0}"'.format(' '.join(args)))

    kwargs = {
        'stdin': stdin,
        'stderr': stderr
    }

    def demote(uid, gid):
        def set_ids():
            os.setgid(gid)
            os.setuid(uid)

        return set_ids

    if username:
        pw_record = pwd.getpwnam(username)
        kwargs['preexec_fn'] = demote(pw_record.pw_uid, pw_record.pw_gid)

    if get_output:
        return subprocess.check_output(args, **kwargs).decode('utf8')
    else:
        subprocess.check_call(args, **kwargs)


def check_deployment_configuration_file(logger, deploy_conf_file):
    if not os.path.isfile(deploy_conf_file):
        logger.error('Deployment configuration file "{0}" does not exist'.format(deploy_conf_file))
        sys.exit(errno.ENOENT)

    with open(deploy_conf_file) as fp:
        try:
            deploy_conf = json.load(fp)
        except json.decoder.JSONDecodeError as err:
            logger.error('Deployment configuration file "{0}" is not a valid JSON file: "{1}"'
                         .format(deploy_conf_file, err))
            sys.exit(errno.ENOENT)

    unspecified_attrs = [attr for attr in (
        'Klever Addons',
        'Klever Build Bases'
    ) if attr not in deploy_conf]

    if unspecified_attrs:
        logger.error('Deployment configuration file "{0}" does not contain following attributes:\n  {1}'
                     .format(deploy_conf_file, '\n  '.join(unspecified_attrs)))
        sys.exit(errno.ENOENT)


def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s (%(filename)s:%(lineno)03d) %(levelname)s> %(message)s',
                                  "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


def get_password(logger, prompt):
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    else:
        logger.warning('Password will be echoed')
        print(prompt, end='', flush=True)
        return sys.stdin.readline().rstrip()


def install_entity(logger, name, src_dir, deploy_dir, deploy_conf, prev_deploy_info, cmd_fn, install_fn):
    if name not in deploy_conf:
        logger.error('"{0}" is not described'.format(name))
        sys.exit(errno.EINVAL)

    deploy_dir = os.path.normpath(deploy_dir)

    desc = deploy_conf[name]

    if 'version' not in desc:
        logger.error('Version is not specified for "{0}"'.format(name))
        sys.exit(errno.EINVAL)

    version = desc['version']

    if 'path' not in desc:
        logger.error('Path is not specified for "{0}"'.format(name))
        sys.exit(errno.EINVAL)

    path = desc['path']
    o = urllib.parse.urlparse(path)
    if not o[0]:
        path = make_canonical_path(src_dir, path)

    refs = {}
    try:
        ref_strs = execute_cmd(logger, 'git', 'ls-remote', '--refs', path, stderr=subprocess.DEVNULL,
                               get_output=True).rstrip().split('\n')
        is_git_repo = True
        for ref_str in ref_strs:
            commit, ref = ref_str.split('\t')
            refs[ref] = commit
    except subprocess.CalledProcessError:
        is_git_repo = False

    if is_git_repo and version != 'CURRENT':
        # Version can be either some reference or commit hash. In the former case we need to get corresponding commit
        # hash since it can differ from the previous one installed before for the same reference. In the latter case we
        # will fail below one day if commit hash isn't valid.
        # Note that here we can use just Git commands working with remote repositories since we didn't clone them yet
        # and we don't want do this if update isn't necessary.
        for prefix in ('refs/heads/', 'refs/tags/'):
            if prefix + version in refs:
                version = refs[prefix + version]
                break

    prev_version = prev_deploy_info[name]['version'] if name in prev_deploy_info else None

    if version == prev_version and version != 'CURRENT':
        logger.info('"{0}" is up to date (version: "{1}")'.format(name, version))
        return False

    if prev_version:
        logger.info('Update "{0}" from version "{1}" to version "{2}"'.format(name, prev_version, version))
    else:
        logger.info('Install "{0}" (version: "{1}")'.format(name, version))

    # Remove previous version of entity if so. Do not make this in depend on previous version since it can be unset
    # while entity is deployed. For instance, this can be the case when entity deployment fails somewhere in the middle.
    cmd_fn('rm', '-rf', deploy_dir)

    # Install new version of entity.
    tmp_file = None
    tmp_dir = None
    try:
        instance_path = os.path.join(deploy_dir, os.path.basename(path))

        # Clone remote Git repository.
        if (o[0] == 'git' or is_git_repo) and not os.path.exists(path):
            tmp_dir = tempfile.mkdtemp()
            execute_cmd(logger, 'git', 'clone', '-q', '--recursive', path, tmp_dir)
            path = tmp_dir
        # Download remote file.
        elif o[0] in ('http', 'https', 'ftp'):
            _, tmp_file = tempfile.mkstemp()
            execute_cmd(logger, 'wget', '-O', tmp_file, '-q', path)
            path = tmp_file
        elif o[0]:
            logger.error('"{0}" is provided in unsupported form "{1}"'.format(name, o[0]))
            sys.exit(errno.EINVAL)
        elif not os.path.exists(path):
            logger.error('Path "{0}" does not exist'.format(path))
            sys.exit(errno.ENOENT)

        if is_git_repo:
            if version == 'CURRENT':
                install_fn(path, deploy_dir, allow_symlink=True)
            else:
                with tempfile.TemporaryDirectory() as tmpdir:
                    # Checkout specified version within local Git repository if this is allowed or clone local Git
                    # repository to temporary directory and checkout specified version there.
                    if desc.get('allow use local Git repository'):
                        tmp_path = path
                        execute_cmd(logger, 'git', '-C', tmp_path, 'checkout', '-fq', version)
                        execute_cmd(logger, 'git', '-C', tmp_path, 'clean', '-xfdq')
                    else:
                        tmp_path = os.path.join(tmpdir, os.path.basename(os.path.realpath(path)))
                        execute_cmd(logger, 'git', 'clone', '-q', path, tmp_path)
                        execute_cmd(logger, 'git', '-C', tmp_path, 'checkout', '-q', version)

                    # Directory .git can be quite large so ignore it during installing except one needs it.
                    install_fn(tmp_path, deploy_dir, ignore=None if desc.get('copy .git directory') else ['.git'])
        elif os.path.isfile(path) and (tarfile.is_tarfile(path) or zipfile.is_zipfile(path)):
            install_fn(path, instance_path)

            if tarfile.is_tarfile(path):
                cmd_fn('tar', '--warning', 'no-unknown-keyword', '-C', '{0}'.format(deploy_dir), '-xf', instance_path)
            else:
                cmd_fn('unzip', '-d', '{0}'.format(deploy_dir), instance_path)

            cmd_fn('rm', '-rf', instance_path)
        elif os.path.isfile(path):
            install_fn(path, instance_path, allow_symlink=True)
        elif os.path.isdir(path):
            install_fn(path, deploy_dir, allow_symlink=True)
        else:
            logger.error('Could not install "{0}" since it is provided in the unsupported format'.format(name))
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


def install_klever_addons(logger, src_dir, deploy_dir, deploy_conf, prev_deploy_info, cmd_fn, install_fn,
                          dump_cur_deploy_info_fn):
    deploy_addons_conf = deploy_conf['Klever Addons']

    if 'Klever Addons' not in prev_deploy_info:
        prev_deploy_info['Klever Addons'] = {}

    prev_deploy_addons_conf = prev_deploy_info['Klever Addons']

    for addon in deploy_addons_conf.keys():
        if addon == 'Verification Backends':
            if 'Verification Backends' not in prev_deploy_addons_conf:
                prev_deploy_addons_conf['Verification Backends'] = {}

            for verification_backend in deploy_addons_conf['Verification Backends'].keys():
                if install_entity(logger, verification_backend, src_dir,
                                  os.path.join(deploy_dir, 'klever-addons', 'verification-backends',
                                               verification_backend),
                                  deploy_addons_conf['Verification Backends'],
                                  prev_deploy_addons_conf['Verification Backends'],
                                  cmd_fn, install_fn):
                    dump_cur_deploy_info_fn(prev_deploy_info)
        elif install_entity(logger, addon, src_dir, os.path.join(deploy_dir, 'klever-addons', addon),
                            deploy_addons_conf, prev_deploy_addons_conf, cmd_fn, install_fn):
            dump_cur_deploy_info_fn(prev_deploy_info)


def install_klever_build_bases(logger, src_dir, deploy_dir, deploy_conf, cmd_fn, install_fn):
    for klever_build_base in deploy_conf['Klever Build Bases']:
        logger.info('Install Klever build base "{0}"'.format(klever_build_base))

        # Very simplified deploys.utils.install_entity.
        tmp_file = None
        try:
            o = urllib.parse.urlparse(klever_build_base)
            if not o[0]:
                klever_build_base = make_canonical_path(src_dir, klever_build_base)

            instance_klever_build_base = os.path.join(deploy_dir, 'build bases',
                                                      os.path.basename(klever_build_base))

            if o[0] in ('http', 'https', 'ftp'):
                _, tmp_file = tempfile.mkstemp()
                execute_cmd(logger, 'wget', '-O', tmp_file, '-q', klever_build_base)
                klever_build_base = tmp_file
            elif o[0]:
                logger.error('Klever build base is provided in unsupported form {!r}'.format(o[0]))
                sys.exit(errno.EINVAL)
            elif not os.path.exists(klever_build_base):
                logger.error('Path "{0}" does not exist'.format(klever_build_base))
                sys.exit(errno.ENOENT)

            cmd_fn('rm', '-rf', instance_klever_build_base)
            install_fn(klever_build_base, instance_klever_build_base)

            # Below is special cheat for insalling the only test build base provided as remote archive in deployment
            # configuration file by default.
            if os.path.basename(instance_klever_build_base) == 'build-base-linux-3.14.79-x86_64-sample.tar.xz':
                real_instance_klever_build_base = os.path.join(deploy_dir,
                                                               'build bases/linux/loadable kernel modules sample')
                cmd_fn('rm', '-rf', real_instance_klever_build_base)
                cmd_fn('tar', '--warning', 'no-unknown-keyword', '-C', '{0}'
                       .format(os.path.join(deploy_dir, 'build bases')), '-xf', instance_klever_build_base)
                instance_klever_build_base = real_instance_klever_build_base

            # Always grant to everybody (including user "klever" who does need that) at least read permissions for
            # deployed Klever build base. Otherwise user "klever" will not be able to access them.
            cmd_fn('chmod', '-R', '+r', instance_klever_build_base)
        finally:
            if tmp_file:
                os.unlink(tmp_file)


def make_canonical_path(src_dir, path):
    if not os.path.isabs(path):
        path = os.path.join(src_dir, path)

    # Avoid paths as symbolic links for all further operations. Some of them deal with symbolic links as we need,
    # but other ones can perform unexpected things.
    path = os.path.realpath(path)

    return path


def need_verifiercloud_scheduler(prev_deploy_info):
    if 'Klever Addons' in prev_deploy_info:
        if 'VerifierCloud Client' in prev_deploy_info['Klever Addons']:
            return True

    return False


def start_services(logger, services):
    logger.info('Start and enable services')
    for service in services:
        execute_cmd(logger, 'service', service, 'start')
        execute_cmd(logger, 'systemctl', 'enable', service)


def stop_services(logger, services, ignore_errors=False):
    logger.info('Stop services')
    for service in services:
        try:
            execute_cmd(logger, 'service', service, 'stop')
        except subprocess.CalledProcessError:
            if ignore_errors:
                pass
            else:
                raise


def get_media_user(logger):
    user_names = [entry.pw_name for entry in pwd.getpwall()]

    if 'www-data' in user_names:
        media_user = 'www-data'
    elif 'apache' in user_names:
        media_user = 'apache'
    else:
        logger.error('Your Linux distribution is not supported')
        sys.exit(errno.EINVAL)

    return media_user


def replace_media_user(path, media_user):
    # Write correct media user to services
    if media_user == 'www-data':
        return

    with open(path) as fp:
        content = fp.readlines()

    with open(path, 'w') as fp:
        for line in content:
            line = line.replace('www-data', media_user)
            fp.write(line)


def get_cgroup_version():
    # I was not able to find a better way to detect cgroup version
    # TODO: improve detection of cgroup version
    if os.path.exists("/sys/fs/cgroup/freezer"):
        return "v1"
    else:
        return "v2"
