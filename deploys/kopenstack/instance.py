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

import time
import traceback

import novaclient.exceptions


class OSInstanceCreationTimeout(RuntimeError):
    pass


class OSInstance:
    CREATION_ATTEMPTS = 5
    CREATION_TIMEOUT = 120
    CREATION_CHECK_INTERVAL = 5
    CREATION_RECOVERY_INTERVAL = 10
    OPERATING_SYSTEM_STARTUP_DELAY = 120
    IMAGE_CREATION_ATTEMPTS = 3
    IMAGE_CREATION_TIMEOUT = 300
    IMAGE_CREATION_CHECK_INTERVAL = 10
    IMAGE_CREATION_RECOVERY_INTERVAL = 30
    NETWORK_TYPE = {'internal': 'ispras', 'external': 'external_network'}

    def __init__(self, logger, clients, args, name, base_image, flavor_name, keep_on_exit=False):
        self.logger = logger
        self.clients = clients
        self.args = args
        self.name = name
        self.base_image = base_image
        self.flavor_name = flavor_name
        self.keep_on_exit = keep_on_exit
        self.floating_ip = None

    def __enter__(self):
        self.logger.info('Create instance "{0}" of flavor "{1}" on the base of image "{2}"'
                         .format(self.name, self.flavor_name, self.base_image.name))

        instance = None

        try:
            flavor = self.clients.nova.flavors.find(name=self.flavor_name)
        except novaclient.exceptions.NotFound:
            self.logger.info(
                'You can use one of the following flavors:\n{0}'.format(
                    '\n'.join(['    {0} - {1} VCPUs, {2} MB of RAM, {3} GB of disk space'
                               .format(flavor.name, flavor.vcpus, flavor.ram, flavor.disk)
                               for flavor in self.clients.nova.flavors.list()])))
            raise

        attempts = self.CREATION_ATTEMPTS

        while attempts > 0:
            try:
                instance = self.clients.nova.servers.create(name=self.name, image=self.base_image, flavor=flavor,
                                                            key_name='ldv')

                timeout = self.CREATION_TIMEOUT

                while timeout > 0:
                    if instance.status == 'ACTIVE':
                        self.logger.info('Instance "{0}" is active'.format(self.name))

                        self.instance = instance

                        network_id = None
                        network_name = self.NETWORK_TYPE[self.args.os_network_type]
                        for net in self.clients.neutron.list_networks()['networks']:
                            if net['name'] == network_name:
                                network_id = net['id']

                        if not network_id:
                            timeout = 0
                            raise ValueError('OpenStack does not have network with "{}" name'.format(network_name))

                        for f_ip in self.clients.neutron.list_floatingips()['floatingips']:
                            if f_ip['status'] == 'DOWN' and f_ip['floating_network_id'] == network_id:
                                self.floating_ip = f_ip['floating_ip_address']
                                break

                        if not self.floating_ip:
                            create_dict = {"floating_network_id": network_id}
                            f_ip = self.clients.neutron.create_floatingip({"floatingip": create_dict})['floatingip']
                            self.floating_ip = f_ip['floating_ip_address']

                        port = self.clients.neutron.list_ports(device_id=self.instance.id)['ports'][0]
                        update_dict = {'port_id': port['id']}
                        self.clients.neutron.update_floatingip(f_ip['id'], {'floatingip': update_dict})

                        self.logger.info('Floating IP {0} is attached to instance "{1}"'.format(self.floating_ip,
                                                                                                self.name))

                        self.logger.info(
                            'Wait for {0} seconds until operating system will start before performing other operations'
                            .format(self.OPERATING_SYSTEM_STARTUP_DELAY))
                        time.sleep(self.OPERATING_SYSTEM_STARTUP_DELAY)

                        return self
                    else:
                        timeout -= self.CREATION_CHECK_INTERVAL
                        self.logger.info('Wait until instance will run (remaining timeout is {} seconds)'
                                         .format(timeout))
                        time.sleep(self.CREATION_CHECK_INTERVAL)
                        instance = self.clients.nova.servers.get(instance.id)

                raise OSInstanceCreationTimeout
            except Exception as e:
                if instance:
                    instance.delete()
                attempts -= 1
                self.logger.warning(
                    'Could not create instance, wait for {0} seconds and try {1} times more{2}'
                    .format(self.CREATION_RECOVERY_INTERVAL, attempts,
                            '' if isinstance(e, OSInstanceCreationTimeout) else '\n' + traceback.format_exc().rstrip()))
                time.sleep(self.CREATION_RECOVERY_INTERVAL)

        raise RuntimeError('Could not create instance')

    def __exit__(self, etype, value, traceback):
        if not self.keep_on_exit:
            self.remove()

    def create_image(self):
        self.logger.info('Create image "{0}"'.format(self.name))

        # Shut off instance to ensure all data is written to disks.
        self.instance.stop()

        # TODO: wait until instance will be shut off otherwise image can't be created.

        attempts = self.IMAGE_CREATION_ATTEMPTS

        while attempts > 0:
            try:
                image_id = self.instance.create_image(image_name=self.name)

                timeout = self.IMAGE_CREATION_TIMEOUT

                while timeout > 0:
                    image = self.clients.glance.images.get(image_id)

                    if image.status == 'active':
                        self.logger.info('Image "{0}" was created'.format(self.name))
                        return
                    else:
                        timeout -= self.IMAGE_CREATION_CHECK_INTERVAL
                        self.logger.info('Wait for {0} seconds until image will be created ({1})'
                                         .format(self.IMAGE_CREATION_CHECK_INTERVAL,
                                                 'remaining timeout is {0} seconds'.format(timeout)))
                        time.sleep(self.IMAGE_CREATION_CHECK_INTERVAL)

                raise OSInstanceCreationTimeout
            except Exception as e:
                attempts -= 1
                self.logger.warning(
                    'Could not create image, wait for {0} seconds and try {1} times more{2}'
                    .format(self.CREATION_RECOVERY_INTERVAL, attempts,
                            '' if isinstance(e, OSInstanceCreationTimeout) else '\n' + traceback.format_exc().rstrip()))
                time.sleep(self.IMAGE_CREATION_RECOVERY_INTERVAL)

        raise RuntimeError('Could not create image')

    def remove(self):
        if self.instance:
            self.logger.info('Remove instance "{0}"'.format(self.name))
            self.instance.delete()
