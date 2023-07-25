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
import subprocess
import sys
import pkg_resources


def execute_cmd(logger, *args, stdin=None, stderr=None, get_output=False, username=None, keep_stdout=False,
                hide_errors=False):
    logger.debug('Execute command "{0}"'.format(' '.join(args)))

    # Do not print output by default.
    stdout = None
    if not keep_stdout and logger.level >= logging.INFO:
        stdout = subprocess.PIPE

    # stdout argument is not allowed in check_output().
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

    try:
        if get_output:
            return subprocess.check_output(args, **kwargs).decode('utf-8')

        subprocess.check_call(args, stdout=stdout, **kwargs)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        if not hide_errors:
            raise e


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


def get_logger(name, level='INFO'):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    formatter = logging.Formatter('%(asctime)s (%(filename)s:%(lineno)03d) %(levelname)s> %(message)s',
                                  "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


def get_password(logger, prompt):
    if sys.stdin.isatty():
        return getpass.getpass(prompt)

    logger.warning('Password will be echoed')
    print(prompt, end='', flush=True)
    return sys.stdin.readline().rstrip()


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
    logger.info(f'Start and enable services: {", ".join(services)}')
    for service in services:
        execute_cmd(logger, 'service', service, 'start')
        execute_cmd(logger, 'systemctl', 'enable', service)


def stop_services(logger, services, ignore_errors=False):
    logger.info(f'Stop services: {", ".join(services)}')
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
    elif 'nginx' in user_names:
        media_user = 'nginx'
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
    if os.path.exists('/sys/fs/cgroup/freezer'):
        return 'v1'

    return 'v2'


def get_klever_version():
    return pkg_resources.get_distribution("klever").version
