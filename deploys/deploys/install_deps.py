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

import errno
import json
import os
import sys

from deploys.utils import execute_cmd, get_logger


def install_deps(logger, deploy_conf, prev_deploy_info, non_interactive, update_pckgs, update_py_pckgs):
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

    # We can skip installation/update of dependencies if nothing is specified, but most likely one prepares
    # deployment configuration file incorrectly.
    if 'Packages' not in deploy_conf:
        logger.error('Deployment configuration file does not describe packages to be installed/updated')
        sys.exit(errno.EINVAL)

    if 'Python3 Packages' not in deploy_conf:
        logger.error('Deployment configuration file does not describe Python3 packages to be installed/updated')
        sys.exit(errno.EINVAL)

    new_pckgs = get_pckgs(deploy_conf['Packages'])
    new_py_pckgs = get_pckgs(deploy_conf['Python3 Packages'])

    if 'Packages' in prev_deploy_info:
        for pckg in new_pckgs:
            if pckg in prev_deploy_info['Packages']:
                pckgs_to_update.append(pckg)
            else:
                pckgs_to_install.append(pckg)
    else:
        # All packages should be installed.
        pckgs_to_install = new_pckgs

    if 'Python3 Packages' in prev_deploy_info:
        for py_pckg in new_py_pckgs:
            if py_pckg in prev_deploy_info['Python3 Packages']:
                py_pckgs_to_update.append(py_pckg)
            else:
                py_pckgs_to_install.append(py_pckg)
    else:
        # All Python3 packages should be installed.
        py_pckgs_to_install = new_py_pckgs

    if pckgs_to_install or (pckgs_to_update and update_pckgs):
        logger.info('Update packages list')
        execute_cmd(logger, 'apt-get', 'update')

    if pckgs_to_install:
        logger.info('Install packages:\n  {0}'.format('\n  '.join(pckgs_to_install)))
        args = ['apt-get', 'install']
        if non_interactive:
            args.append('--assume-yes')
        args.extend(pckgs_to_install)
        execute_cmd(logger, *args)

        # Remember what packages were installed just if everything went well.
        if 'Packages' not in prev_deploy_info:
            prev_deploy_info['Packages'] = []

        prev_deploy_info['Packages'] = sorted(prev_deploy_info['Packages'] + pckgs_to_install)

    if py_pckgs_to_install:
        logger.info('Install Python3 packages:\n  {0}'.format('\n  '.join(py_pckgs_to_install)))
        execute_cmd(logger, 'pip3', 'install', *py_pckgs_to_install)

        # Remember what Python3 packages were installed just if everything went well.
        if 'Python3 Packages' not in prev_deploy_info:
            prev_deploy_info['Python3 Packages'] = []

        prev_deploy_info['Python3 Packages'] = sorted(prev_deploy_info['Python3 Packages'] + py_pckgs_to_install)

    if pckgs_to_update and update_pckgs:
        logger.info('Update packages:\n  {0}'.format('\n  '.join(pckgs_to_update)))
        args = ['apt-get', 'upgrade']
        if non_interactive:
            args.append('--assume-yes')
        args.extend(pckgs_to_update)
        execute_cmd(logger, *args)

    if py_pckgs_to_update and update_py_pckgs:
        logger.info('Update Python3 packages:\n  {0}'.format('\n  '.join(py_pckgs_to_update)))
        execute_cmd(logger, 'pip3', 'install', '--upgrade', *py_pckgs_to_update)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--deployment-configuration-file', default='klever.json')
    parser.add_argument('--deployment-directory', default='klever-inst')
    parser.add_argument('--non-interactive', default=False, action='store_true')
    parser.add_argument('--update-packages', default=False, action='store_true')
    parser.add_argument('--update-python3-packages', default=False, action='store_true')
    args = parser.parse_args()

    with open(args.deployment_configuration_file) as fp:
        deploy_conf = json.load(fp)

    prev_deploy_info_file = os.path.join(args.deployment_directory, 'klever.json')
    if os.path.exists(prev_deploy_info_file):
        with open(prev_deploy_info_file) as fp:
            prev_deploy_info = json.load(fp)
    else:
        prev_deploy_info = {}

    install_deps(get_logger(__name__), deploy_conf, prev_deploy_info, args.non_interactive, args.update_packages,
                 args.update_python3_packages)

    with open(prev_deploy_info_file, 'w') as fp:
        json.dump(prev_deploy_info, fp, sort_keys=True, indent=4)


if __name__ == '__main__':
    main()
