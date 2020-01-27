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
import shutil
import sys
import tempfile

from klever.deploys.utils import execute_cmd, get_logger


def install_deps(logger, deploy_conf, prev_deploy_info, non_interactive, update_pckgs):
    if non_interactive:
        # Do not require users input.
        os.environ['DEBIAN_FRONTEND'] = 'noninteractive'

    # Get packages to be installed/updated.
    pckgs_to_install = []
    pckgs_to_update = []

    deploy_conf.update(load_deps_conf(logger))

    # We can skip installation/update of dependencies if nothing is specified, but most likely one prepares
    # deployment configuration file incorrectly.
    if 'Packages' not in deploy_conf:
        logger.error('Deployment configuration file does not describe packages to be installed/updated')
        sys.exit(errno.EINVAL)

    new_pckgs = []
    for pckgs in deploy_conf['Packages'].values():
        new_pckgs.extend(pckgs)

    if 'Packages' in prev_deploy_info:
        for pckg in new_pckgs:
            if pckg in prev_deploy_info['Packages']:
                pckgs_to_update.append(pckg)
            else:
                pckgs_to_install.append(pckg)
    else:
        # All packages should be installed.
        pckgs_to_install = new_pckgs

    if pckgs_to_install or (pckgs_to_update and update_pckgs):
        logger.info('Update packages list')
        if shutil.which('apt'):
            execute_cmd(logger, 'apt', 'update')
        elif shutil.which('dnf'):
            execute_cmd(logger, 'dnf', 'update')
        elif shutil.which('zypper'):
            execute_cmd(logger, 'zypper', 'ref')
        elif shutil.which('yum'):
            execute_cmd(logger, 'yum', 'check-update')
        else:
            logger.error('Your Linux distribution is not supported')
            sys.exit(errno.EINVAL)

    if pckgs_to_install:
        logger.info('Install packages:\n  {0}'.format('\n  '.join(pckgs_to_install)))

        for util in ('apt', 'dnf', 'zypper', 'yum'):
            if shutil.which(util):
                args = [util, 'install']

                if non_interactive:
                    args.append('-y')
                args.extend(pckgs_to_install)
                execute_cmd(logger, *args)
                break
        else:
            logger.error('Your Linux distribution is not supported')
            sys.exit(errno.EINVAL)

        # Remember what packages were installed just if everything went well.
        if 'Packages' not in prev_deploy_info:
            prev_deploy_info['Packages'] = []

        prev_deploy_info['Packages'] = sorted(prev_deploy_info['Packages'] + pckgs_to_install)

    if pckgs_to_update and update_pckgs:
        logger.info('Update packages:\n  {0}'.format('\n  '.join(pckgs_to_update)))
        for util in ('apt', 'dnf', 'zypper', 'yum'):
            if shutil.which(util):
                if util in ('apt', 'dnf'):
                    args = [util, 'upgrade']
                elif util in ('yum', 'zypper'):
                    args = [util, 'update']

                if non_interactive:
                    args.append('-y')
                args.extend(pckgs_to_install)
                execute_cmd(logger, *args)
                break
        else:
            raise RuntimeError('Your Linux distribution is not supported')


def load_deps_conf(logger):
    deps_conf_dir = os.path.join(os.path.dirname(__file__), 'conf')

    if shutil.which('apt'):
        deps_conf_file = os.path.join(deps_conf_dir, 'debian.json')
    elif shutil.which('dnf'):
        deps_conf_file = os.path.join(deps_conf_dir, 'fedora.json')
    else:
        logger.error('Your Linux distribution is not supported')
        sys.exit(errno.EINVAL)

    with open(deps_conf_file) as fp:
        deps_conf = json.load(fp)

    return deps_conf


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--deployment-configuration-file', default='klever.json')
    parser.add_argument('--deployment-directory', default='klever-inst')
    parser.add_argument('--non-interactive', default=False, action='store_true')
    parser.add_argument('--update-packages', default=False, action='store_true')
    args = parser.parse_args()

    with open(args.deployment_configuration_file) as fp:
        deploy_conf = json.load(fp)

    prev_deploy_info_file = os.path.join(args.deployment_directory, 'klever.json')
    if os.path.exists(prev_deploy_info_file):
        with open(prev_deploy_info_file) as fp:
            prev_deploy_info = json.load(fp)
    else:
        prev_deploy_info = {}

    install_deps(get_logger(__name__), deploy_conf, prev_deploy_info, args.non_interactive, args.update_packages)

    with open(prev_deploy_info_file, 'w') as fp:
        json.dump(prev_deploy_info, fp, sort_keys=True, indent=4)


if __name__ == '__main__':
    main()
