#!/usr/bin/env python3
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

import json
import os
import subprocess


def execute_cmd(*args, get_output=False):
    print('Execute command "{0}"'.format(' '.join(args)))
    # if get_output:
    #     return subprocess.check_output(args).decode('utf8')
    # else:
    #     subprocess.check_call(args)


def install_deps(deploy_conf, prev_deploy_info, non_interactive):
    if non_interactive:
        # Do not require users input.
        os.environ['DEBIAN_FRONTEND'] = 'noninteractive'

    # Get packages to be installed/updated.
    pckgs_to_install = []
    pckgs_to_update = []
    py_pckgs_to_install = []
    py_pckgs_to_update = []

    def get_pckgs(pckgs):
        _pckgs = []
        for val in pckgs.values():
            _pckgs.extend(val)
        return _pckgs

    new_pckgs = get_pckgs(deploy_conf['Packages'])
    new_py_pckgs = get_pckgs(deploy_conf['Python3 Packages'])

    if prev_deploy_info:
        for pckg in new_pckgs:
            if pckg in prev_deploy_info['Packages']:
                pckgs_to_update.append(pckg)
            else:
                pckgs_to_install.append(pckg)

        for py_pckg in new_py_pckgs:
            if py_pckg in prev_deploy_info['Python3 Packages']:
                py_pckgs_to_update.append(py_pckg)
            else:
                py_pckgs_to_install.append(py_pckg)
    else:
        # All packages should be installed.
        pckgs_to_install = new_pckgs
        py_pckgs_to_install = new_py_pckgs

    if pckgs_to_install or pckgs_to_update:
        print('Update packages list')
        execute_cmd('apt-get', 'update')

    if pckgs_to_install:
        print('Install packages:\n  {0}'.format('\n  '.join(pckgs_to_install)))
        execute_cmd('apt-get', 'install', '--assume-yes' if non_interactive else '--assume-no', *pckgs_to_install)

        # Remember what packages were installed just if everything went well.
        if 'Packages' not in prev_deploy_info:
            prev_deploy_info['Packages'] = []

        prev_deploy_info['Packages'] = sorted(prev_deploy_info['Packages'] + pckgs_to_install)

    if py_pckgs_to_install:
        print('Install Python3 packages:\n  {0}'.format('\n  '.join(py_pckgs_to_install)))
        execute_cmd('pip3', 'install', *py_pckgs_to_install)

        # Remember what Python3 packages were installed just if everything went well.
        if 'Python3 Packages' not in prev_deploy_info:
            prev_deploy_info['Python3 Packages'] = []

        prev_deploy_info['Python3 Packages'] = sorted(prev_deploy_info['Python3 Packages'] + pckgs_to_install)

    if pckgs_to_update:
        print('Update packages:\n  {0}'.format('\n  '.join(pckgs_to_update)))
        execute_cmd('apt-get', 'upgrade', '--assume-yes' if non_interactive else '--assume-no', *pckgs_to_update)

    if py_pckgs_to_update:
        print('Update Python3 packages:\n  {0}'.format('\n  '.join(py_pckgs_to_update)))
        execute_cmd('pip3', 'install', '--upgrade', *py_pckgs_to_update)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--deployment-configuration-file', required=True)
    parser.add_argument('--deployment-directory', required=True)
    args = parser.parse_args()

    with open(args.deployment_configuration_file) as fp:
        deploy_conf = json.load(fp)

    prev_deploy_info_file = os.path.join(args.deployment_directory, 'klever.json')
    if os.path.exists(prev_deploy_info_file):
        with open(prev_deploy_info_file) as fp:
            prev_deploy_info = json.load(fp)
    else:
        prev_deploy_info = None

    install_deps(deploy_conf, prev_deploy_info, True)
