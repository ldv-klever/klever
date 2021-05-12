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

import errno
import sys

from klever.deploys.openstack.client import OSClient
from klever.deploys.openstack.client.instance import OSInstance
from klever.deploys.openstack.ssh import SSH
from klever.deploys.openstack.copy import CopyDeployConfAndSrcs
from klever.deploys.openstack.constants import PYTHON, KLEVER_DEPLOY_LOCAL, DEPLOYMENT_DIRECTORY


class OSKleverInstance:
    def __init__(self, args, logger, client=None):
        self.args = args
        self.logger = logger
        self.name = self.args.name or f'{self.args.os_username}-klever-{self.args.mode}'
        self.client = client or OSClient(args, logger)

    def __getattr__(self, name):
        self.logger.error(f'Action "{name}" is not supported for "{self.args.entity}"')
        sys.exit(errno.ENOSYS)

    def show(self):
        instances = self.client.get_instances(self.name)

        if len(instances) == 1:
            instance_info = self.client.show_instance(instances[0])
            self.logger.info(f'There is Klever instance "{instance_info}" matching "{self.name}"')
        elif len(instances) > 1:
            self.logger.info(f'There are {len(instances)} Klever instances matching "{self.name}":')

            for instance in instances:
                print(
                    f'\t * {self.client.show_instance(instance)}'
                )
        else:
            self.logger.info(f'There are no Klever instances matching "{self.name}"')

    def ssh(self):
        with SSH(
            args=self.args,
            logger=self.logger,
            name=self.name,
            floating_ip=self.client.get_instance_floating_ip(self.client.get_instance(self.name))
        ) as ssh:
            ssh.open_shell()

    def share(self):
        instance = self.client.get_instance(self.name)

        self.client.interface_detach(instance)
        self.client.interface_attach(instance, share=True)
        self.client.assign_floating_ip(instance, share=True)

        instance.add_security_group(self.args.os_sec_group)

        self.logger.info(f'Reboot instance "{self.name}"')
        instance.reboot()

    def hide(self):
        instance = self.client.get_instance(self.name)

        self.client.interface_detach(instance)
        self.client.interface_attach(instance, share=False)
        self.client.assign_floating_ip(instance, share=False)

        instance.add_security_group(self.args.os_sec_group)

        self.logger.info(f'Reboot instance "{self.name}"')
        instance.reboot()

    def remove(self):
        # TODO: wait for successfull deletion everywhere.
        self.client.nova.servers.delete(self.client.get_instance(self.name).id)

    def create(self):
        base_image = self.client.get_base_image(self.args.klever_base_image)
        self.logger.debug(f'Klever base image: {base_image}')

        if self.client.instance_exists(self.name):
            self.logger.error(f'Klever instance matching "{self.name}" already exists')
            sys.exit(errno.EINVAL)

        with OSInstance(
            logger=self.logger,
            client=self.client,
            args=self.args,
            name=self.name,
            base_image=base_image,
            vcpus=self.args.vcpus,
            ram=self.args.ram,
            disk=self.args.disk
        ) as instance:
            with SSH(
                args=self.args,
                logger=self.logger,
                name=self.name,
                floating_ip=instance.floating_ip['floating_ip_address']
            ) as ssh:
                with CopyDeployConfAndSrcs(
                    self.args,
                    self.logger,
                    ssh,
                    'creation of Klever instance'
                ):
                    self.__install_or_update_klever(ssh)
                    self.__deploy_klever(ssh, action='install')

                # Preserve instance if everything above went well.
                instance.keep_on_exit = True

                return instance

    def __install_or_update_klever(self, ssh):
        ssh.execute_cmd(f'sudo {PYTHON} -m pip install --upgrade pip setuptools wheel')

        ssh.execute_cmd(f'sudo {PYTHON} -m pip install --upgrade -r klever/requirements.txt ./klever')

    def __deploy_klever(self, ssh, action='install'):
        # TODO: check that source directory contains setup.py file
        ssh.execute_cmd(
            f'sudo {KLEVER_DEPLOY_LOCAL} --deployment-directory {DEPLOYMENT_DIRECTORY} --non-interactive'
            + (' --update-packages' if self.args.update_packages else '')
            + (' --update-python3-packages' if self.args.update_python3_packages else '')
            + f' --deployment-configuration-file klever.json --source-directory klever {action} {self.args.mode}'
        )

    def update(self):
        instance = self.client.get_instance(self.name)

        with SSH(
            args=self.args,
            logger=self.logger,
            name=instance.name,
            floating_ip=self.client.get_instance_floating_ip(instance)
        ) as ssh:
            with CopyDeployConfAndSrcs(
                self.args,
                self.logger,
                ssh,
                'update of Klever instance'
            ):
                self.__install_or_update_klever(ssh)
                self.__deploy_klever(ssh, action='update')
