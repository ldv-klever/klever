# Copyright (c) 2021 ISP RAS (http://www.ispras.ru)
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

import time

from klever.deploys.openstack.client import OSClient


class OSVolume:
    CREATION_ATTEMPTS = 5
    DEVICE = '/dev/vdb'

    def __init__(self, logger, client, args, name):
        self.logger = logger
        self.client: OSClient = client
        self.args = args
        self.name = name
        self.volume = None

    def create(self):
        attempts = self.CREATION_ATTEMPTS

        while attempts > 0:
            try:
                self.logger.info(f'Create {self.name} volume')
                self.volume = self.client.cinder.volumes.create(size=self.args.volume_size, name=self.name)

                while self.volume.status != 'available':
                    self.volume = self.volume.manager.get(self.volume.id)

                    if self.volume.status == 'error':
                        raise RuntimeError(f"Volume {self.name} has error status")

                    self.logger.info('Wait until volume is available')
                    time.sleep(3)

                self.logger.info(f'Volume "{self.name}" is active')

                return self
            except RuntimeError:
                attempts -= 1
                self.logger.info(f'Could not create volume, try {attempts} times more')
                self.remove()
            except Exception as e:
                self.logger.error(e)
                self.logger.error('Could not create volume')
                self.remove()
                raise

        self.logger.error('Could not create volume')
        self.remove()
        raise RuntimeError("Volume was not created")

    def attach(self, instance):
        self.logger.info('Attach volume to instance')
        self.client.nova.volumes.create_server_volume(instance.id, self.volume.id, device=self.DEVICE)

    def remove(self):
        if self.volume:
            self.logger.info(f'Remove volume "{self.volume.name}"')
            self.volume.detach()
            self.volume.delete()
            self.volume = None
