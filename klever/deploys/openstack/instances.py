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

import copy
import errno
import sys
import time

from concurrent.futures import ThreadPoolExecutor

from klever.deploys.openstack.client import OSClient
from klever.deploys.openstack.instance import OSKleverInstance


class OSKleverInstances:
    def __init__(self, args, logger):
        self.args = args
        self.logger = logger
        self.client = OSClient(logger, args.os_username, args.store_password)

        self.name = self.args.name or f'{self.args.os_username}-klever-production'
        # It is assumed that all requested Klever experimental instances have the same unique prefix (name).
        self.name_pattern = self.name + '.*'

    def __getattr__(self, name):
        self.logger.error(f'Action "{name}" is not supported for multiple instances')
        sys.exit(errno.ENOSYS)

    def show(self):
        name = self.name_pattern
        instances = self.client.get_instances(self.name_pattern)

        if len(instances) == 1:
            instance_info = self.client.show_instance(instances[0])
            self.logger.info(f'There is Klever production instance "{instance_info}" matching "{name}"')
        elif len(instances) > 1:
            self.logger.info(f'There are {len(instances)} Klever production instances matching "{name}":')

            for instance in instances:
                instance_info = self.client.show_instance(instance)
                print(
                    f'\t * "{instance_info}"'
                )
        else:
            self.logger.info(f'There are no Klever production instances matching "{name}"')

    def create(self):
        base_image = self.client.get_base_image(self.args.klever_base_image)
        self.logger.debug(f'Klever base image: {base_image}')

        if self.client.instance_exists(self.name_pattern):
            self.logger.error(f'Klever instance matching "{self.name_pattern}" already exists')
            sys.exit(errno.EINVAL)

        with ThreadPoolExecutor(max_workers=self.args.instances) as p:
            for instance_id in range(1, self.args.instances + 1):
                instance_name = f'{self.name}-{instance_id}'
                self.logger.info(f'Create Klever production instance "{instance_name}"')

                instance_args = copy.deepcopy(self.args)
                instance_args.name = instance_name

                i = OSKleverInstance(instance_args, self.logger, client=self.client)
                p.submit(i.create)

                # Without waiting OpenStack can assign the same floating IP address to different instances
                time.sleep(10)

    def update(self):
        instances = self.client.get_instances(self.name_pattern)

        if len(instances) == 0:
            self.logger.error(f'There are no Klever production instances matching "{self.name_pattern}"')
            sys.exit(errno.EINVAL)

        self.logger.warning(
            'Please, do not keep Klever production instances for a long period of time'
            ' (these updates are intended just for fixing initial deployment issues)'
        )

        for instance in instances:
            self.logger.info(f'Update instance "{instance.name}"')
            instance_args = copy.deepcopy(self.args)
            instance_args.name = instance.name

            i = OSKleverInstance(instance_args, self.logger, client=self.client)
            i.update()

    def remove(self):
        instances = self.client.get_instances(self.name_pattern)

        if len(instances) == 0:
            self.logger.error(f'There are no Klever production instances matching "{self.name_pattern}"')
            sys.exit(errno.EINVAL)

        for instance in instances:
            self.logger.info(f'Remove instance "{instance.name}"')
            self.client.nova.servers.delete(instance.id)
