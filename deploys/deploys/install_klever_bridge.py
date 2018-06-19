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

import json
import os
import shutil

from deploys.utils import Cd, execute_cmd, get_logger, start_services, stop_services


# This function includes common actions for both development and production Klever Bridge.
def _install_klever_bridge(logger):
    logger.info('Configure Klever Bridge')
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

    logger.info('Populate databace')
    execute_cmd(logger, './manage.py', 'PopulateUsers', '--exist-ok',
                '--admin', '{"username": "admin", "password": "admin"}',
                '--manager', '{"username": "manager", "password": "manager"}',
                '--service', '{"username": "service", "password": "service"}')
    execute_cmd(logger, './manage.py', 'Population')


def install_klever_bridge_development(logger, deploy_dir):
    logger.info('Install/update development Klever Bridge')

    services = ('klever-bridge-development',)
    stop_services(logger, services)

    # Do not overwrite directory "media" from sumbolically linked Git repository. Otherwise it will notice changes.
    if not os.path.islink(os.path.join(deploy_dir, 'klever')):
        logger.info('Prepare media directory')
        media = os.path.join(deploy_dir, 'klever/bridge/media')
        media_real = os.path.join(os.path.realpath(deploy_dir), 'media')
        shutil.rmtree(media)
        execute_cmd(logger, 'mkdir', '-p', media_real)
        execute_cmd(logger, 'ln', '-s', '-T', media_real, media)

    with Cd(os.path.join(deploy_dir, 'klever/bridge')):
        with open('bridge/settings.py', 'w') as fp:
            fp.write('from bridge.{0} import *\n'.format('development'))

        _install_klever_bridge(logger)

    start_services(logger, services)


def install_klever_bridge_production(logger, deploy_dir):
    logger.info('Install/update production Klever Bridge')

    services = ('nginx', 'klever-bridge')
    stop_services(logger, services)

    logger.info('Copy Klever Bridge configuration file for NGINX')
    shutil.copy(os.path.join(deploy_dir, 'klever/bridge/conf/debian-nginx'),
                '/etc/nginx/sites-enabled/klever-bridge')

    logger.info('Update Klever Bridge source/binary code')
    shutil.rmtree('/var/www/klever-bridge', ignore_errors=True)
    shutil.copytree(os.path.join(deploy_dir, 'klever/bridge'), '/var/www/klever-bridge', symlinks=True)

    logger.info('Prepare media directory')
    media = '/var/www/klever-bridge/media'
    media_real = os.path.join(os.path.realpath(deploy_dir), 'media')
    shutil.rmtree(media)
    execute_cmd(logger, 'mkdir', '-p', media_real)
    execute_cmd(logger, 'ln', '-s', '-T', media_real, media)

    with Cd('/var/www/klever-bridge'):
        with open('bridge/settings.py', 'w') as fp:
            fp.write('from bridge.{0} import *\n'.format('production'))

        _install_klever_bridge(logger)

        logger.info('Collect static files')
        execute_cmd(logger, './manage.py', 'collectstatic', '--noinput')

    # Make available data from media for its actual user.
    execute_cmd(logger, 'chown', '-R', 'www-data:www-data', media_real)

    start_services(logger, services)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--development', default=False, action='store_true')
    parser.add_argument('--deployment-directory', default='klever-inst')
    args = parser.parse_args()

    install_klever_bridge = install_klever_bridge_development if args.development else install_klever_bridge_production
    install_klever_bridge(get_logger(__name__), args.deployment_directory)


if __name__ == '__main__':
    main()
