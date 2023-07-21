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
import os
import sys
import time
import novaclient

from Crypto.PublicKey import RSA

from klever.deploys.utils import get_password
from klever.deploys.openstack.client import OSClient
from klever.deploys.openstack.client.volume import OSVolume


class OSCreationTimeout(RuntimeError):
    pass


class OSInstance:
    CREATION_ATTEMPTS = 5
    CREATION_TIMEOUT = 120
    CREATION_CHECK_INTERVAL = 5
    CREATION_RECOVERY_INTERVAL = 10
    OPERATING_SYSTEM_STARTUP_DELAY = 40
    IMAGE_CREATION_ATTEMPTS = 3
    IMAGE_CREATION_TIMEOUT = 300
    IMAGE_CREATION_CHECK_INTERVAL = 10
    IMAGE_CREATION_RECOVERY_INTERVAL = 30

    def __init__(self, logger, client, args, name, base_image, vcpus, ram, disk, keep_on_exit=False):
        self.logger = logger
        self.client: OSClient = client
        self.args = args
        self.name = name
        self.base_image = base_image
        self.vcpus = vcpus
        self.ram = ram
        self.disk = disk
        self.keep_on_exit = keep_on_exit
        self.instance = None
        self.volume = None

    def __enter__(self):
        return self.create()

    def __exit__(self, etype, value, traceback):
        if not self.keep_on_exit:
            self.remove()

    def create(self):
        flavor = self.client.find_flavor(self.vcpus, self.ram, self.disk)

        self.logger.info(
            f'Create instance "{self.name}" of flavor "{flavor.name}"'
            f' on the base of image "{self.base_image.name}"'
        )

        self.__setup_keypair()

        attempts = self.CREATION_ATTEMPTS

        network_name = self.client.NET_TYPE[self.args.os_network_type]
        network_id = self.client.get_network_id(network_name)

        while attempts > 0:
            try:
                instance = self.client.nova.servers.create(
                    name=self.name,
                    image=self.base_image,
                    flavor=flavor,
                    key_name=self.args.os_keypair_name,
                    nics=[{'net-id': network_id}],
                    security_groups=['default', self.args.os_sec_group]
                )

                timeout = self.CREATION_TIMEOUT

                while timeout > 0:
                    if instance.status == 'ACTIVE':
                        self.logger.info('Instance "{0}" is active'.format(self.name))
                        self.instance = instance

                        share = self.args.os_network_type == 'external'
                        self.floating_ip = self.client.assign_floating_ip(instance, share=share) # pylint: disable=attribute-defined-outside-init

                        self.logger.info(
                            'Wait for {0} seconds until operating system is started before performing other operations'
                            .format(self.OPERATING_SYSTEM_STARTUP_DELAY))
                        time.sleep(self.OPERATING_SYSTEM_STARTUP_DELAY)

                        return self
                    if instance.status == 'ERROR':
                        self.logger.error('An error occurred during instance creation. '
                                          'Perhaps there are not enough resources available')
                        self.remove(instance)
                        sys.exit(errno.EAGAIN)

                    timeout -= self.CREATION_CHECK_INTERVAL
                    self.logger.info('Wait until instance will run (remaining timeout is {} seconds)'
                                     .format(timeout))
                    time.sleep(self.CREATION_CHECK_INTERVAL)
                    instance = self.client.nova.servers.get(instance.id)

                raise OSCreationTimeout
            except OSCreationTimeout:
                attempts -= 1
                self.logger.info('Could not create instance, wait for {0} seconds and try {1} times more'
                                 .format(self.CREATION_RECOVERY_INTERVAL, attempts))
                time.sleep(self.CREATION_RECOVERY_INTERVAL)
                self.remove(instance)
            except Exception:
                attempts -= 1
                # Give a chance to see information on this exception for handling it one day.
                self.logger.exception('Please, handle me!')
                time.sleep(self.CREATION_RECOVERY_INTERVAL)
                self.remove(instance)

        self.logger.error('Could not create instance')
        sys.exit(errno.EPERM)

    def create_volume(self):
        self.volume = OSVolume(self.logger, self.client, self.args, self.name)
        self.volume.create()
        self.volume.attach(self.instance)

        return self.volume

    def remove(self, instance=None):
        if not instance:
            instance = self.instance

        if instance:
            self.logger.info(f'Remove instance "{self.name}"')
            instance.delete()

        if self.volume:
            self.volume.remove()

    def __setup_keypair(self):
        private_key_file = self.args.ssh_rsa_private_key_file

        if not private_key_file:
            self.logger.error('Private key is required. Please specify it using --ssh-rsa-private-key-file argument')
            sys.exit(errno.EINVAL)

        if not os.path.exists(private_key_file):
            self.logger.error('Specified private key "{}" does not exist'.format(private_key_file))
            sys.exit(errno.ENOENT)

        self.logger.info('Setup OpenStack keypair using specified private key "{}"'.format(private_key_file))

        private_key = open(private_key_file, 'rb').read() # pylint: disable=consider-using-with

        try:
            public_key = RSA.import_key(private_key).publickey().exportKey('OpenSSH')
        except ValueError:
            self.args.key_password = get_password(self.logger, 'Private key password: ')
            try:
                public_key = RSA.import_key(private_key, self.args.key_password).publickey().exportKey('OpenSSH')
            except ValueError:
                self.logger.error('Incorrect password for private key')
                sys.exit(errno.EACCES)

        try:
            kp = self.client.nova.keypairs.get(self.args.os_keypair_name)
            kp_public_key = kp.to_dict()['public_key']
            # Normalize kp_public_key in order to be able to compare it with public_key
            kp_public_key = RSA.import_key(kp_public_key).publickey().exportKey('OpenSSH')

            if public_key != kp_public_key:
                self.logger.error('Specified private key "{}" does not match "{}" keypair stored in OpenStack'
                                  .format(private_key_file, self.args.os_keypair_name))
                sys.exit(errno.EINVAL)
        except novaclient.exceptions.NotFound:
            self.logger.info('Specified keypair "{}" is not found and will be created'
                             .format(self.args.os_keypair_name))

            self.client.nova.keypairs.create(self.args.os_keypair_name, public_key=public_key.decode('utf-8'))

    def create_image(self):
        self.logger.info(f'Create image "{self.name}"')

        # Shut off instance to ensure all data is written to disks.
        self.instance.stop()

        # TODO: wait until instance will be shut off otherwise image can't be created. Corresponding exceptions look like:
        # novaclient.exceptions.Conflict: Cannot 'createImage' instance ... while it is in task_state powering-off (HTTP 409) (Request-ID: ...)

        attempts = self.IMAGE_CREATION_ATTEMPTS

        while attempts > 0:
            try:
                image_id = self.instance.create_image(image_name=self.name)

                timeout = self.IMAGE_CREATION_TIMEOUT

                while timeout > 0:
                    image = self.client.glance.images.get(image_id)

                    if image.status == 'active':
                        self.logger.info(f'Image "{self.name}" was created')
                        return

                    timeout -= self.IMAGE_CREATION_CHECK_INTERVAL
                    self.logger.info(
                        f'Wait for {self.IMAGE_CREATION_CHECK_INTERVAL} seconds until image will be created'
                        f' (remaining timeout is {timeout} seconds)'
                    )
                    time.sleep(self.IMAGE_CREATION_CHECK_INTERVAL)

                raise OSCreationTimeout
            except OSCreationTimeout:
                attempts -= 1
                self.logger.info(
                    f'Could not create image, wait for {self.CREATION_RECOVERY_INTERVAL} seconds'
                    f' and try {attempts} times more'
                )
                time.sleep(self.IMAGE_CREATION_RECOVERY_INTERVAL)
            except Exception:
                attempts -= 1
                # Give a chance to see information on this exception for handling it one day.
                self.logger.exception('Please, handle me!')
                time.sleep(self.IMAGE_CREATION_RECOVERY_INTERVAL)

        self.logger.error('Could not create image')
        sys.exit(errno.EPERM)
