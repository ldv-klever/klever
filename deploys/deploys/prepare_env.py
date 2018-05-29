#!/usr/bin/env python3
#
# Copyright (c) 2017 ISPRAS (http://www.ispras.ru)
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

import glob
import os
import pwd

from deploys.utils import execute_cmd, get_logger


def prepare_env(logger, mode, username, deploy_dir):
    try:
        pwd.getpwnam(username)
    except KeyError:
        logger.info('Create user "{0}"'.format(username))
        execute_cmd(logger, 'useradd', username)

    logger.info('Prepare configurations directory')
    execute_cmd(logger, 'mkdir', os.path.join(deploy_dir, 'klever-conf'))

    logger.info('Prepare working directory')
    work_dir = os.path.join(deploy_dir, 'klever-work')
    execute_cmd(logger, 'mkdir', work_dir)
    execute_cmd(logger, 'chown', '-LR', username, work_dir)

    openssl_header = '/usr/include/openssl/opensslconf.h'
    if not os.path.exists(openssl_header):
        logger.info('Create soft links for libssl to build new versions of the Linux kernel')
        execute_cmd(logger, 'ln', '-s', '/usr/include/x86_64-linux-gnu/openssl/opensslconf.h', openssl_header)

    crts = glob.glob('/usr/lib/x86_64-linux-gnu/crt*.o')
    args = []
    for crt in crts:
        if not os.path.exists(os.path.join('/usr/lib', os.path.basename(crt))):
            args.append(crt)
    if args:
        logger.info('Prepare CIF environment')
        args.append('/usr/lib')
        execute_cmd(logger, 'ln', '-s', *args)

    logger.info('Create PostgreSQL user')
    execute_cmd(logger, 'psql', '-c', "CREATE USER klever WITH PASSWORD 'klever'", username='postgres')

    logger.info('Create PostgreSQL database')
    execute_cmd(logger, 'createdb', '-T', 'template0', '-E', 'utf8', 'klever', username='postgres')

    logger.info('Prepare Klever Bridge media directory')
    media = os.path.join(deploy_dir, 'media')
    execute_cmd(logger, 'mkdir', media)

    if mode != 'development':
        execute_cmd(logger, 'chown', '-R', 'www-data:www-data', media)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', required=True)
    parser.add_argument('--username', required=True)
    parser.add_argument('--deployment-directory', default='klever-inst')
    args = parser.parse_args()

    prepare_env(get_logger(__name__), args.mode, args.username, args.deployment_directory)


if __name__ == '__main__':
    main()
