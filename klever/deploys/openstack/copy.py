# Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
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

import os
import json
import shutil
import tempfile
import setuptools_scm

from klever.core.utils import Cd
from klever.deploys.utils import execute_cmd
from klever.deploys.openstack.conf import STORAGE


class CopyDeployConfAndSrcs:
    def __init__(self, args, logger, ssh, action, is_remove_srcs=False):
        self.args = args
        self.logger = logger
        self.ssh = ssh
        self.action = action
        self.is_remove_srcs = is_remove_srcs

    def __enter__(self):
        self.__copy_deployment_files()

        self.logger.info('Copy sources that can be used during {0}'.format(self.action))
        with Cd(self.args.source_directory):
            try:
                klever_copy = os.path.join(tempfile.mkdtemp(), 'klever')
                execute_cmd(self.logger, 'git', 'clone', '.', klever_copy)
                # Store Klever version to dedicated file and remove directory ".git" since it occupies too much space.
                with open(os.path.join(klever_copy, 'version'), 'w') as fp:
                    fp.write(setuptools_scm.get_version())
                execute_cmd(self.logger, 'rm', '-rf', klever_copy + '/.git')

                # Development Klever Bridge runs from Klever sources and it creates directories like __pycache__, media,
                # etc. with root access. We need to backup media and to restore it after update of Klever sources. Other
                # directories are out of interest, but they should not hinder rsync.
                sftp = self.ssh.ssh.open_sftp()
                media_exists = False
                try:
                    sftp.stat('klever/bridge/media')
                    media_exists = True
                    self.ssh.execute_cmd('mv klever/bridge/media media-backup')
                    self.ssh.execute_cmd('sudo rm -rf klever/bridge')
                except IOError:
                    pass

                self.ssh.rsync(klever_copy, '~/')

                if media_exists:
                    self.ssh.execute_cmd('sudo rm -rf klever/bridge/media')
                    self.ssh.execute_cmd('mv media-backup klever/bridge/media')
            finally:
                if os.path.exists(klever_copy):
                    shutil.rmtree(klever_copy)

    def __exit__(self, etype, value, traceback):
        if self.is_remove_srcs:
            self.logger.info('Remove sources used during {0}'.format(self.action))
            self.ssh.execute_cmd('sudo rm -r klever')

        self.logger.info('Remove deployment configuration file')
        self.ssh.execute_cmd('rm klever.json')

    def __copy_deployment_files(self):
        with open(self.args.deployment_configuration_file) as fp:
            deploy_conf = json.load(fp)

        deploy_conf = self.__copy_klever_addons(deploy_conf)
        deploy_conf = self.__copy_verification_backends(deploy_conf)
        deploy_conf = self.__copy_build_bases(deploy_conf)

        self.__copy_deployment_configuration(deploy_conf)

    def __copy_klever_addons(self, deploy_conf):
        for addon in deploy_conf['Klever Addons']:
            path = deploy_conf['Klever Addons'][addon].get('path')
            if path and os.path.exists(path):
                self.logger.info(f'Copy Klever addon {addon}')
                to_path = self.__copy_path(path)

                # Store new path in the deployment configuration
                deploy_conf['Klever Addons'][addon]['path'] = to_path

        return deploy_conf

    def __copy_verification_backends(self, deploy_conf):
        if 'Verification Backends' not in deploy_conf['Klever Addons']:
            return deploy_conf

        conf = deploy_conf['Klever Addons']['Verification Backends']

        for verifier in conf:
            path = conf[verifier].get('path')
            if path and os.path.exists(path):
                self.logger.info(f'Copy Klever Verification Backend {verifier}')
                to_path = self.__copy_path(path)

                # Store new path in the deployment configuration
                conf[verifier]['path'] = to_path

        return deploy_conf

    def __copy_build_bases(self, deploy_conf):
        for build_base in deploy_conf['Klever Build Bases']:
            path = deploy_conf['Klever Build Bases'][build_base].get('path')
            if path and os.path.exists(path):
                self.logger.info(f'Copy Klever Build Base {build_base}')
                to_path = self.__copy_path(path)

                # Store new path in the deployment configuration
                deploy_conf['Klever Build Bases'][build_base]['path'] = to_path

        return deploy_conf

    def __copy_path(self, path):
        if os.path.isabs(path):
            to_path = STORAGE + path
        else:
            to_path = os.path.join(STORAGE, path)

        to_path = os.path.normpath(to_path)
        self.ssh.rsync(path, os.path.dirname(to_path))

        return to_path

    def __copy_deployment_configuration(self, deploy_conf):
        changed_configuration_file = os.path.join(tempfile.mkdtemp(), 'klever.json')
        with open(changed_configuration_file, 'w') as fp:
            json.dump(deploy_conf, fp, sort_keys=True, indent=4)

        self.logger.info('Copy deployment configuration file')
        self.ssh.rsync(changed_configuration_file, '~/')

        if os.path.exists(changed_configuration_file):
            os.remove(changed_configuration_file)
