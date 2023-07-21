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
import time

from klever.deploys.openstack.client import OSClient
from klever.deploys.openstack.client.instance import OSInstance
from klever.deploys.openstack.ssh import SSH
from klever.deploys.openstack.copy import CopyDeployConfAndSrcs
from klever.deploys.openstack.conf import PYTHON_BIN, KLEVER_DEPLOY_LOCAL, DEPLOYMENT_DIR, OS_USER, \
    VOLUME_DIR, PROD_MEDIA_DIR, DEV_MEDIA_DIR, VOLUME_PGSQL_DIR, VOLUME_MEDIA_DIR


class OSKleverInstance:
    def __init__(self, args, logger, client=None):
        self.args = args
        self.logger = logger
        self.name = self.args.name or f'{self.args.os_username}-klever-{self.args.mode}'
        self.client = client or OSClient(logger, args.os_username, args.store_password)

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

    def add_security_group(self, instance):
        if not any([sec_group.name == self.args.os_sec_group for sec_group in instance.list_security_group()]): # pylint: disable=use-a-generator
            instance.add_security_group(self.args.os_sec_group)

    def share(self):
        if not self.args.non_interactive:
            answer = None
            while answer != 'y':
                self.logger.warning(f'You are going to share instance "{self.name}" to the outer world.'
                                    ' Did you change default passwords for users "admin" and "manager"'
                                    ' (default passwords coincide with usernames)? (y)')
                answer = sys.stdin.readline().rstrip()

        instance = self.client.get_instance(self.name)

        self.client.interface_detach(instance)
        self.client.interface_attach(instance, share=True)
        self.client.assign_floating_ip(instance, share=True)

        self.add_security_group(instance)

        self.logger.info(f'Reboot instance "{self.name}"')
        instance.reboot()

    def hide(self):
        instance = self.client.get_instance(self.name)

        self.client.interface_detach(instance)
        self.client.interface_attach(instance, share=False)
        self.client.assign_floating_ip(instance, share=False)

        self.add_security_group(instance)

        self.logger.info(f'Reboot instance "{self.name}"')
        instance.reboot()

    def remove(self):
        # TODO: wait for successful deletion everywhere.
        instance = self.client.get_instance(self.name)
        volumes = self.client.get_volumes(instance)

        for volume in volumes:
            # self.client.nova.volumes.delete_server_volume(instance.id, volume.id)
            volume.detach()
            volume.delete()

        instance.delete()

    def create(self):
        base_image = self.client.get_base_image(self.args.klever_base_image)

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
            if not self.args.without_volume:
                instance.create_volume()

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

                    if not self.args.without_volume:
                        self.__mount_volume(ssh, instance)

                    self.__deploy_klever(ssh, action='install')

                # Preserve instance if everything above went well.
                instance.keep_on_exit = True

                return instance

    def __install_or_update_klever(self, ssh):
        pip_install_cmd = f'{PYTHON_BIN} -m pip install --upgrade '

        if self.args.log_level == 'INFO':
            pip_install_cmd += '--quiet '

        ssh.execute_cmd(pip_install_cmd + 'pip setuptools setuptools_scm wheel')
        ssh.execute_cmd(pip_install_cmd + '-r klever/requirements.txt ./klever')

    def __deploy_klever(self, ssh, action='install'):
        # TODO: check that source directory contains setup.py file
        ssh.execute_cmd(
            f'sudo {KLEVER_DEPLOY_LOCAL} --deployment-directory {DEPLOYMENT_DIR} --non-interactive'
            + (' --update-packages' if self.args.update_packages else '')
            + (' --update-python3-packages' if self.args.update_python3_packages else '')
            + f' --log-level {self.args.log_level}'
            + f' --deployment-configuration-file klever.json --source-directory klever {action} {self.args.mode}'
        )

    def __mount_volume(self, ssh, instance):
        device = instance.volume.DEVICE
        partition = device + '1'

        # Create partition inside volume
        ssh.execute_cmd(f'echo "start=2048, type=83" | sudo sfdisk {device}')
        # Format partition
        ssh.execute_cmd(f'sudo mkfs.ext4 {partition}')
        # Create mount point for volume
        ssh.execute_cmd(f'mkdir {VOLUME_DIR}')
        # Make volume automount after restarts
        ssh.execute_cmd(f'echo  "{partition} {VOLUME_DIR} auto defaults,nofail 0 3" | sudo tee -a /etc/fstab')
        # Mount created partition
        ssh.execute_cmd(f'sudo mount -t ext4 {partition}')
        # Grant rights to mounted partition to OS_USER
        ssh.execute_cmd(f'sudo chown {OS_USER}:{OS_USER} {VOLUME_DIR}')

        # Store media in volume
        ssh.execute_cmd(f'mkdir {VOLUME_MEDIA_DIR}')

        if self.args.mode == 'production':
            ssh.execute_cmd(f'sudo mkdir -p {DEPLOYMENT_DIR}')
            ssh.execute_cmd(f'sudo ln -s -T {VOLUME_MEDIA_DIR} {PROD_MEDIA_DIR}')
        elif self.args.mode == 'development':
            # Remove empty media directory
            ssh.execute_cmd(f'rm -rf {DEV_MEDIA_DIR}')
            ssh.execute_cmd(f'sudo ln -s -T {VOLUME_MEDIA_DIR} {DEV_MEDIA_DIR}')
        else:
            self.logger.error('Unsupported deployment mode')
            sys.exit(errno.EINVAL)

        # Store PostgreSQL data directory in volume
        data_dir = '/var/lib/postgresql/13/main'
        conf_file = '/etc/postgresql/13/main/postgresql.conf'

        # Stop PostgreSQL to make required changes
        ssh.execute_cmd('sudo systemctl stop postgresql')
        # It seems that PostgreSQL continues to operate for a while after stopping the service. For instance, there may
        # be errors during running rsync below like:
        #   file has vanished: "/var/lib/postgresql/13/main/pg_logical/replorigin_checkpoint.tmp"
        # So let's wait a bit prior to proceed to the following commands.
        time.sleep(5)

        # Move the PostgreSQL data directory to volume
        ssh.execute_cmd(f'mkdir {VOLUME_PGSQL_DIR}')
        # copy the contents of data_dir
        ssh.execute_cmd(f'sudo rsync --exclude "postmaster.pid" -a {data_dir}/ {VOLUME_PGSQL_DIR}')

        # Change PostgreSQL configuration
        ssh.execute_cmd(f'sudo sed -i "s#^\\(data_directory\\s*=\\s*\\).*\\$#\\1\'{VOLUME_PGSQL_DIR}\'#" {conf_file}')

        # Start again
        ssh.execute_cmd('sudo systemctl start postgresql')

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

    def resize(self):
        instance = self.client.get_instance(self.name)
        flavor = self.client.find_flavor(self.args.vcpus, self.args.ram, self.args.disk)

        if instance.flavor['id'] == flavor.id:
            self.logger.error('You must change flavor in order to resize instance')
            sys.exit(errno.EINVAL)

        try:
            self.logger.info(f'Resize instance "{self.name}" to flavor "{flavor.name}"')
            instance.resize(flavor)

            self.logger.info("This will take several minutes")
            while instance.status != "VERIFY_RESIZE":
                instance = self.client.nova.servers.get(instance.id)
                self.logger.info("Wait until resize is complete")
                time.sleep(15)

            instance.confirm_resize()
            self.logger.info('Resize is confirmed and complete')
        except Exception as e:
            self.logger.error(e)

            instance = self.client.nova.servers.get(instance.id)
            if instance.status != "ACTIVE":
                instance.revert_resize()
                self.logger.info('Resize is reverted')

            sys.exit(errno.EINVAL)
