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
import os
import shutil
import sys

from klever.core.utils import Cd
from klever.deploys.utils import execute_cmd, get_logger, start_services, stop_services, get_media_user


# This function includes common actions for both development and production Klever Bridge.
def _install_klever_bridge(logger, update):
    logger.info('Update translations')
    execute_cmd(logger, sys.executable, './manage.py', 'compilemessages')

    logger.info('Migrate database')
    execute_cmd(logger, sys.executable, './manage.py', 'migrate')

    logger.info('Populate database')
    # We need to create users once. Otherwise this can overwrite their settings changed manually.
    if not update:
        execute_cmd(logger, sys.executable, './manage.py', 'createuser',
                    '--username', 'admin', '--password', 'admin',
                    '--staff', '--superuser')
        execute_cmd(logger, sys.executable, './manage.py', 'createuser',
                    '--username', 'manager', '--password', 'manager',
                    '--role', '2')
        execute_cmd(logger, sys.executable, './manage.py', 'createuser',
                    '--username', 'service', '--password', 'service',
                    '--role', '4')

    execute_cmd(logger, sys.executable, './manage.py', 'populate', '--all')


def install_klever_bridge_development(logger, src_dir, update=False):
    logger.info('Install/update development Klever Bridge')

    services = ('klever-bridge-development', 'klever-celery-development', 'klever-celerybeat-development')
    stop_services(logger, services)

    with Cd(os.path.join(src_dir, 'bridge')):
        _install_klever_bridge(logger, update)

    start_services(logger, services)


def install_klever_bridge_production(logger, src_dir, deploy_dir, populate_just_production_presets=True, update=False):
    logger.info('Install/update production Klever Bridge')

    services = ('nginx', 'klever-bridge', 'klever-celery', 'klever-celerybeat')
    stop_services(logger, services)

    logger.info('Copy Klever Bridge configuration file for NGINX')
    copy_from = os.path.join(src_dir, 'bridge/conf/nginx')

    if os.path.exists('/etc/nginx/sites-enabled'):
        shutil.copy(copy_from, '/etc/nginx/sites-enabled/klever-bridge.conf')
    else:
        shutil.copy(copy_from, '/etc/nginx/conf.d/klever-bridge.conf')

    logger.info('Install/update Klever Bridge source/binary code')
    shutil.rmtree('/var/www/klever-bridge', ignore_errors=True)
    shutil.copytree(os.path.join(src_dir, 'bridge'), '/var/www/klever-bridge/bridge',
                    ignore=shutil.ignore_patterns('test_files'))
    shutil.copytree(os.path.join(src_dir, 'presets'), '/var/www/klever-bridge/presets')

    logger.info('Prepare media directory')
    media = '/var/www/klever-bridge/bridge/media'
    media_real = os.path.realpath(os.path.join(os.path.realpath(deploy_dir), 'klever-media'))

    shutil.rmtree(media)
    execute_cmd(logger, 'mkdir', '-p', media_real)
    execute_cmd(logger, 'ln', '-s', '-T', media_real, media)

    with Cd('/var/www/klever-bridge/bridge'):
        with open('bridge/settings.py', 'w') as fp:
            fp.write('from bridge.{0} import *\n'.format('production'))
            if not populate_just_production_presets:
                fp.write('POPULATE_JUST_PRODUCTION_PRESETS = False\n')

        _install_klever_bridge(logger, update)

        logger.info('Collect static files')
        execute_cmd(logger, sys.executable, './manage.py', 'collectstatic', '--noinput')

    # Make available data from media, logs and static for its actual user.
    media_user = get_media_user(logger)
    user_group = '{user}:{user}'.format(user=media_user)

    execute_cmd(logger, 'chown', '-R', user_group, media_real)
    execute_cmd(logger, 'chown', '-R', user_group, '/var/www/klever-bridge/bridge/logs')
    execute_cmd(logger, 'chown', '-R', user_group, '/var/www/klever-bridge/bridge/static')

    # Try to add httpd_t to the list of permissive domains.
    execute_cmd(logger, 'semanage', 'permissive', '-a', 'httpd_t', hide_errors=True)

    start_services(logger, services)


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('--development', default=False, action='store_true')
    parser.add_argument('--update', default=False, action='store_true')
    parser.add_argument('--source-directory', default='klever')
    parser.add_argument('--deployment-directory', default='klever-inst')
    args = parser.parse_args()

    if args.development:
        install_klever_bridge_development(get_logger(__name__), args.source_directory, args.update)
    else:
        install_klever_bridge_production(get_logger(__name__), args.source_directory, args.deployment_directory,
                                         args.update)


if __name__ == '__main__':
    main()
