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
import subprocess


class Cd:
    def __init__(self, path):
        self.new_path = path

    def __enter__(self):
        self.prev_path = os.getcwd()
        os.chdir(self.new_path)

    def __exit__(self, etype, value, traceback):
        os.chdir(self.prev_path)


def execute_cmd(*args, stdin=None, get_output=False):
    print('Execute command "{0}"'.format(' '.join(args)))
    if get_output:
        return subprocess.check_output(args, stdin=stdin).decode('utf8')
    else:
        subprocess.check_call(args, stdin=stdin)


def install_klever_bridge(action, mode, deploy_dir, psql_user_passwd='klever', psql_user_name='klever'):
    print('(Re)install Klever Bridge')

    services = ['klever-bridge-development'] if mode == 'development' else ['nginx', 'klever-bridge']

    print('Stop services')
    for service in services:
        execute_cmd('service', service, 'stop')

    media = None
    media_real = os.path.join(os.path.realpath(deploy_dir), 'media')

    if mode == 'development':
        if action == 'install':
            media = os.path.join(deploy_dir, 'klever/bridge/media')
    else:
        print('Copy Klever Bridge configuration file for NGINX')
        shutil.copy(os.path.join(deploy_dir, 'klever/bridge/conf/debian-nginx'),
                    '/etc/nginx/sites-enabled/klever-bridge')

        print('Update Klever Bridge source/binary code')
        shutil.rmtree('/var/www/klever-bridge', ignore_errors=True)
        shutil.copytree(os.path.join(deploy_dir, 'klever/bridge'), '/var/www/klever-bridge', symlinks=True)

        media = '/var/www/klever-bridge/media'

    if media:
        shutil.rmtree(media)
        execute_cmd('ln', '-s', '-T', media_real, media)

    with Cd(os.path.join(deploy_dir, 'klever/bridge') if mode == 'development' else '/var/www/klever-bridge'):
        print('Configure Klever Bridge')
        with open('bridge/settings.py', 'w') as fp:
            fp.write('from bridge.{0} import *\n'.format('development' if mode == 'development' else 'production'))

        with open('bridge/db.json', 'w') as fp:
            json.dump({
                'ENGINE': 'django.db.backends.postgresql',
                'HOST': '127.0.0.1',
                'NAME': 'klever',
                'USER': psql_user_name,
                'PASSWORD': psql_user_passwd
            }, fp, sort_keys=True, indent=4)

        print('Update translations')
        execute_cmd('./manage.py', 'compilemessages')

        print('Migrate database')
        execute_cmd('./manage.py', 'migrate')

        if mode != 'development':
            print('Collect static files')
            execute_cmd('./manage.py', 'collectstatic', '--noinput')

        print('Populate databace')
        execute_cmd('./manage.py', 'PopulateUsers', '--exist-ok',
                    '--admin', '{"username": "admin", "password": "admin"}',
                    '--manager', '{"username": "manager", "password": "manager"}',
                    '--service', '{"username": "service", "password": "service"}')
        execute_cmd('./manage.py', 'Population')

    if mode != 'development':
        execute_cmd('chown', '-R', 'www-data:www-data', media_real)

    print('Start services')
    for service in services:
        execute_cmd('service', service, 'start')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--action', required=True)
    parser.add_argument('--mode', required=True)
    parser.add_argument('--deployment-directory', default='klever-inst')
    args = parser.parse_args()

    install_klever_bridge(args.action, args.mode, args.deployment_directory)
