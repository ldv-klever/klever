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

import getpass
import os
import subprocess
import sys
import tarfile
import tempfile


def execute_cmd(logger, *args, get_output=False):
    logger.info('Execute command "{0}"'.format(' '.join(args)))
    if get_output:
        return subprocess.check_output(args).decode('utf8')
    else:
        subprocess.check_call(args)


def get_password(logger, prompt):
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    else:
        logger.warning('Password will be echoed')
        print(prompt, end='', flush=True)
        return sys.stdin.readline().rstrip()


def install_extra_dep_or_program(logger, name, deploy_dir, deploy_conf, prev_deploy_info, cmd_fn, install_fn):
    if name not in deploy_conf:
        raise KeyError('Entity "{0}" is not described'.format(name))

    desc = deploy_conf[name]

    if 'version' not in desc:
        raise KeyError('Version is not specified for entity "{0}"'.format(name))

    version = desc['version']

    if 'path' not in desc:
        raise KeyError('Path is not specified for entity "{0}"'.format(name))

    path = desc['path'] if os.path.isabs(desc['path']) \
        else os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir, desc['path'])

    if not os.path.exists(path):
        raise ValueError('Path "{0}" does not exist'.format(path))

    is_git_repo = False

    # Use commit hash to uniquely identify entity version if it is provided as Git repository.
    if os.path.isdir(path) and os.path.isdir(os.path.join(path, '.git')):
        is_git_repo = True
        version = execute_cmd(logger, 'git', '-C', path, 'rev-list', '-n', '1', version, get_output=True).rstrip()

    prev_version = prev_deploy_info[name]['version'] if name in prev_deploy_info else None

    if version == prev_version:
        logger.info('Entity "{0}" is up to date (version: "{1}")'.format(name, version))
        return False

    if prev_version:
        logger.info('Update "{0}" from version "{1}" to version "{2}"'.format(name, prev_version, version))
    else:
        logger.info('Install "{0}" (version: "{1}")'.format(name, version))

    # Remove previous version of entity if so.
    if prev_version:
        cmd_fn(logger, 'rm', '-rf', deploy_dir)
        # ssh.execute_cmd('sudo rm -rf ' + instance_path)

    if is_git_repo:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = os.path.join(tmpdir, os.path.basename(os.path.realpath(path)))
            execute_cmd(logger, 'git', 'clone', '-q', path, tmp_path)
            execute_cmd(logger, 'git', '-C', tmp_path, 'checkout', '-q', version)
            # TODO: this makes imposible to detect Klever Core version.
            # shutil.rmtree(os.path.join(tmp_host_path, '.git'))
            install_fn(logger, tmp_path, deploy_dir)
            # ssh.sftp_put(tmp_host_path, instance_path)
    elif os.path.isfile(path) and tarfile.is_tarfile(path):
        cmd_fn(logger, 'mkdir', '-p', '{0}'.format(deploy_dir))
        archive = os.path.join(deploy_dir, os.pardir, os.path.basename(path))
        install_fn(logger, path, archive)
        cmd_fn(logger, 'tar', '-C', '{0}'.format(deploy_dir), '-xf', '{0}'.format(archive))
        cmd_fn(logger, 'rm', '-rf', '{0}'.format(archive))
        # ssh.sftp.put(host_path, instance_archive)
        # ssh.execute_cmd('mkdir -p "{0}"'.format(instance_path))
        # ssh.execute_cmd('tar -C "{0}" -xf "{1}"'.format(instance_path, instance_archive))
        # ssh.execute_cmd('rm -rf "{0}"'.format(instance_archive))
    elif os.path.isfile(path) or os.path.isdir(path):
        cmd_fn(logger, 'mkdir', '-p', '"{0}"'.format(deploy_dir))
        install_fn(logger, path, deploy_dir)
        # ssh.sftp_put(host_path, instance_path)
    else:
        raise NotImplementedError

    # Remember what extra dependencies were installed just if everything went well.
    prev_deploy_info[name] = {
        'version': version,
        'directory': deploy_dir
    }
    for attr in ('name', 'executable path'):
        if attr in desc:
            prev_deploy_info[name][attr] = desc[attr]

    return True


def install_extra_deps(logger, deploy_dir, deploy_conf, prev_deploy_info, cmd_fn, install_fn):
    is_update_controller_and_schedulers = False
    is_update_verification_backends = False
    
    if 'Klever Addons' in deploy_conf:
        deploy_addons_conf = deploy_conf['Klever Addons']

        if 'Klever Addons' not in prev_deploy_info:
            prev_deploy_info['Klever Addons'] = {}

        prev_deploy_addons_conf = prev_deploy_info['Klever Addons']

        for addon in deploy_addons_conf.keys():
            if addon == 'Verification Backends':
                if 'Verification Backends' not in prev_deploy_addons_conf:
                    prev_deploy_addons_conf['Verification Backends'] = {}

                for verification_backend in deploy_addons_conf['Verification Backends'].keys():
                    is_update_verification_backends |= \
                        install_extra_dep_or_program(logger, verification_backend,
                                                     os.path.join(deploy_dir, 'klever-addons', 'verification-backends',
                                                                  verification_backend),
                                                     deploy_addons_conf['Verification Backends'],
                                                     prev_deploy_addons_conf['Verification Backends'],
                                                     cmd_fn, install_fn)
            elif install_extra_dep_or_program(logger, addon, os.path.join(deploy_dir, 'klever-addons', addon),
                                              deploy_addons_conf, prev_deploy_addons_conf, cmd_fn, install_fn) \
                    and addon in ('BenchExec', 'CIF', 'CIL', 'Consul', 'VerifierCloud Client'):
                is_update_controller_and_schedulers = True

    return is_update_controller_and_schedulers, is_update_verification_backends


def install_programs(logger, username, group, deploy_dir, deploy_conf, prev_deploy_info, cmd_fn, install_fn):
    if 'Programs' in deploy_conf:
        deploy_programs_conf = deploy_conf['Programs']

        if 'Programs' not in prev_deploy_info:
            prev_deploy_info['Programs'] = {}

        prev_deploy_programs_conf = prev_deploy_info['Programs']

        for program in deploy_programs_conf.keys():
            deploy_dir = os.path.join(deploy_dir, 'klever-programs', program)
            if install_extra_dep_or_program(logger, program, deploy_dir, deploy_programs_conf,
                                            prev_deploy_programs_conf, cmd_fn, install_fn):
                cmd_fn(logger, 'chown', '-LR', '{0}:{1}'.format(username, group), deploy_dir)
