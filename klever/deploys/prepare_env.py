#!/usr/bin/env python3
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

import argparse
import errno
import glob
import os
import subprocess
import sys

from klever.deploys.utils import execute_cmd, get_logger


def prepare_env(logger, deploy_dir):
    logger.info('Prepare environment')
    try:
        logger.debug('Try to create user "klever"')
        execute_cmd(logger, 'useradd', 'klever')
    except subprocess.CalledProcessError:
        logger.debug('User "klever" already exists')

    logger.debug('Obtain execute access to {!r} home directory'.format(os.getlogin()))
    execute_cmd(logger, 'chmod', 'o+x', os.path.join('/', 'home', os.getlogin()), hide_errors=True)

    logger.debug('Prepare configurations directory')
    execute_cmd(logger, 'mkdir', os.path.join(deploy_dir, 'klever-conf'))

    logger.debug('Prepare working directory')
    work_dir = os.path.join(deploy_dir, 'klever-work')
    execute_cmd(logger, 'mkdir', work_dir)
    execute_cmd(logger, 'chown', '-LR', 'klever', work_dir)

    openssl_header = '/usr/include/openssl/opensslconf.h'
    if not os.path.exists(openssl_header):
        logger.debug('Create soft links for libssl to build new versions of the Linux kernel')
        execute_cmd(logger, 'ln', '-s', '/usr/include/x86_64-linux-gnu/openssl/opensslconf.h', openssl_header)

    crts = glob.glob('/usr/lib/x86_64-linux-gnu/crt*.o')
    args = []
    for crt in crts:
        if not os.path.exists(os.path.join('/usr/lib', os.path.basename(crt))):
            args.append(crt)
    if args:
        logger.debug('Prepare CIF environment')
        args.append('/usr/lib')
        execute_cmd(logger, 'ln', '-s', *args)

    logger.debug('Try to initialise PostgreSQL')
    try:
        execute_cmd(logger, 'postgresql-setup', '--initdb', '--unit', 'postgresql')
    except FileNotFoundError:
        # postgresql-setup may not be present in the system. On some systems like openSUSE it is necessary to start the
        # PostgreSQL service at least once so that necessary initialization will be performed automatically.
        execute_cmd(logger, 'service', 'postgresql', 'restart')
    except subprocess.CalledProcessError:
        # postgresql-setup may fail if it was already executed before
        pass

    # Search for pg_hba.conf in all possible locations
    pg_hba_conf_file = None
    for path in ('/etc/postgresql', '/var/lib/pgsql/data'):
        try:
            pg_hba_conf_file = execute_cmd(logger, 'find', path, '-name', 'pg_hba.conf', get_output=True).rstrip()
        except subprocess.CalledProcessError:
            continue

        with open(pg_hba_conf_file) as fp:
            pg_hba_conf = fp.readlines()

        with open(pg_hba_conf_file, 'w') as fp:
            for line in pg_hba_conf:
                # change ident to md5
                if line.split() == ['host', 'all', 'all', '127.0.0.1/32', 'ident']:
                    line = 'host all all 127.0.0.1/32 md5\n'
                fp.write(line)

        execute_cmd(logger, 'service', 'postgresql', 'restart')

    if not pg_hba_conf_file:
        logger.error('Could not find PostgreSQL configuration file')
        sys.exit(errno.EINVAL)

    logger.debug('Start and enable PostgreSQL service')
    execute_cmd(logger, 'systemctl', 'start', 'postgresql')
    execute_cmd(logger, 'systemctl', 'enable', 'postgresql')

    logger.debug('Create PostgreSQL user')
    execute_cmd(logger, 'psql', '-c', "CREATE USER klever WITH CREATEDB PASSWORD 'klever'", username='postgres')

    logger.debug('Create PostgreSQL database')
    execute_cmd(logger, 'createdb', '-T', 'template0', '-E', 'utf-8', 'klever', username='postgres')

    logger.debug('Start and enable RabbitMQ server service')
    execute_cmd(logger, 'systemctl', 'start', 'rabbitmq-server.service')
    execute_cmd(logger, 'systemctl', 'enable', 'rabbitmq-server.service')

    logger.debug('Create RabbitMQ user')
    execute_cmd(logger, 'rabbitmqctl', 'add_user', 'service', 'service')
    execute_cmd(logger, 'rabbitmqctl', 'set_user_tags', 'service', 'administrator')
    execute_cmd(logger, 'rabbitmqctl', 'set_permissions', '-p', '/', 'service', '.*', '.*', '.*')


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('--deployment-directory', default='klever-inst')
    args = parser.parse_args()

    prepare_env(get_logger(__name__), args.deployment_directory)


if __name__ == '__main__':
    main()
