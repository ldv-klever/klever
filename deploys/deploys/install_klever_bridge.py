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

import json
import os
import shutil

from deploys.utils import Cd, execute_cmd, get_logger


def install_klever_bridge(logger, mode, deploy_dir):
    logger.info('(Re)install Klever Bridge')

    services = ('klever-bridge-development',) if mode == 'development' else ('nginx', 'klever-bridge')

    logger.info('Stop services')
    for service in services:
        execute_cmd(logger, 'service', service, 'stop')

    media = None
    media_real = os.path.join(os.path.realpath(deploy_dir), 'media')

    if mode == 'development':
        media = os.path.join(deploy_dir, 'klever/bridge/media')
    else:
        logger.info('Copy Klever Bridge configuration file for NGINX')
        shutil.copy(os.path.join(deploy_dir, 'klever/bridge/conf/debian-nginx'),
                    '/etc/nginx/sites-enabled/klever-bridge')

        logger.info('Update Klever Bridge source/binary code')
        shutil.rmtree('/var/www/klever-bridge', ignore_errors=True)
        shutil.copytree(os.path.join(deploy_dir, 'klever/bridge'), '/var/www/klever-bridge', symlinks=True)

        media = '/var/www/klever-bridge/media'

    if media:
        shutil.rmtree(media)
        execute_cmd(logger, 'ln', '-s', '-T', media_real, media)

    with Cd(os.path.join(deploy_dir, 'klever/bridge') if mode == 'development' else '/var/www/klever-bridge'):
        logger.info('Configure Klever Bridge')
        with open('bridge/settings.py', 'w') as fp:
            fp.write('from bridge.{0} import *\n'.format('development' if mode == 'development' else 'production'))

        with open('bridge/db.json', 'w') as fp:
            json.dump({
                'ENGINE': 'django.db.backends.postgresql',
                'HOST': '127.0.0.1',
                'NAME': 'klever',
                'USER': 'klever',
                'PASSWORD': 'klever'
            }, fp, sort_keys=True, indent=4)

        logger.info('Update translations')
        execute_cmd(logger, './manage.py', 'compilemessages')

        logger.info('Migrate database')
        execute_cmd(logger, './manage.py', 'migrate')

        if mode != 'development':
            logger.info('Collect static files')
            execute_cmd(logger, './manage.py', 'collectstatic', '--noinput')

        logger.info('Populate databace')
        execute_cmd(logger, './manage.py', 'PopulateUsers', '--exist-ok',
                    '--admin', '{"username": "admin", "password": "admin"}',
                    '--manager', '{"username": "manager", "password": "manager"}',
                    '--service', '{"username": "service", "password": "service"}')
        execute_cmd(logger, './manage.py', 'Population')

    if mode != 'development':
        execute_cmd(logger, 'chown', '-R', 'www-data:www-data', media_real)

    logger.info('Start services')
    for service in services:
        execute_cmd(logger, 'service', service, 'start')


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', required=True)
    parser.add_argument('--deployment-directory', default='klever-inst')
    args = parser.parse_args()

    install_klever_bridge(get_logger(__name__), args.mode, args.deployment_directory)


if __name__ == '__main__':
    main()
