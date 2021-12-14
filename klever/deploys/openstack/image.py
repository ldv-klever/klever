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
import os
import re
import sys

from klever.deploys.openstack.client import OSClient
from klever.deploys.openstack.client.instance import OSInstance
from klever.deploys.openstack.ssh import SSH
from klever.deploys.openstack.copy import CopyDeployConfAndSrcs
from klever.deploys.openstack.conf import PYTHON


class OSKleverBaseImage:
    def __init__(self, args, logger):
        self.args = args
        self.logger = logger
        self.name = self.args.name
        self.client = OSClient(logger, args.os_username, args.store_password)

    def __getattr__(self, name):
        self.logger.error(f'Action "{name}" is not supported for "{self.args.entity}"')
        sys.exit(errno.ENOSYS)

    def show(self):
        image_name = self.name if self.name else 'Klever Base.*'
        images = self.client.get_images(image_name)

        if len(images) == 1:
            self.logger.info(
                f'There is Klever base image "{images[0].name}" (status: {images[0].status}) matching "{image_name}"'
            )
        elif len(images) > 1:
            self.logger.info(f'There are {len(images)} Klever base images matching "{image_name}":')

            for image in images:
                print(
                    f'\t * "{image.name}" (status: {image.status})'
                )
        else:
            self.logger.info(f'There are no Klever base images matching "{image_name}"')

    def create(self):
        # Use either name specified explicitly or "Klever Base vN" where N is 1 plus a maximum of 0 and vi.
        if self.name:
            klever_base_image_name = self.name
            if self.client.image_exists(klever_base_image_name):
                self.logger.error(f'Klever image matching "{klever_base_image_name}" already exists')
                sys.exit(errno.EINVAL)
        else:
            n = 0
            image_name = self.name if self.name else 'Klever Base.*'
            images = self.client.get_images(image_name)
            if images:
                for image in images:
                    match = re.search(r' v(\d+)', image.name)
                    if match:
                        i = int(match.group(1))
                        n = max(i, n)

            klever_base_image_name = "Klever Base v{}".format(n + 1)

        base_image = self.client.get_base_image(self.args.base_image)

        with OSInstance(
            logger=self.logger,
            client=self.client,
            args=self.args,
            name=klever_base_image_name,
            base_image=base_image,
            vcpus=1,
            ram=2048,
            disk=10
        ) as instance:
            with SSH(
                args=self.args,
                logger=self.logger,
                name=klever_base_image_name,
                floating_ip=instance.floating_ip['floating_ip_address']
            ) as ssh:
                # Copying files uses rsync that needs rsync to be installed on the remote host as well.
                self.__install_rsync(ssh)
                with CopyDeployConfAndSrcs(
                    self.args,
                    self.logger,
                    ssh,
                    'creation of Klever base image',
                    True
                ):
                    self.__install_sys_deps(ssh)
                    self.__install_klever_python(ssh)
                    self.__install_python_packages(ssh)

            instance.create_image()

        self.__overwrite_default_base_image_name(klever_base_image_name)

    def __install_rsync(self, ssh):
        ssh.execute_cmd('sudo apt-get update', timeout=1)
        ssh.execute_cmd('sudo apt-get install -y rsync', timeout=1)

    def __install_sys_deps(self, ssh):
        # Only Debian (Ubuntu) is supported for now
        ssh.execute_cmd('sudo apt-get update', timeout=1)
        ssh.execute_cmd('cat klever/klever/deploys/conf/debian-packages.txt | sudo xargs apt-get install -y',
                        timeout=3)

    def __install_klever_python(self, ssh):
        ssh.execute_cmd('wget https://forge.ispras.ru/attachments/download/7251/python-3.7.6.tar.xz', timeout=1)
        ssh.execute_cmd('sudo tar -C / -xf python-3.7.6.tar.xz')
        ssh.execute_cmd('rm python-3.7.6.tar.xz')

    def __install_python_packages(self, ssh):
        ssh.execute_cmd(f'sudo {PYTHON} -m pip install --upgrade pip setuptools wheel', timeout=1)
        ssh.execute_cmd(f'sudo {PYTHON} -m pip install --upgrade -r klever/requirements.txt', timeout=3)

    def __overwrite_default_base_image_name(self, klever_base_image_name):
        # Most likely the new base image should be used for creating instances by all users.
        with open(os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'conf', 'openstack-base-image.txt')),
                  'w') as fp:
            fp.write(klever_base_image_name + '\n')

    def remove(self):
        klever_base_image_name = self.name or self.args.klever_base_image
        klever_base_image = self.client.get_base_image(klever_base_image_name)
        self.client.glance.images.delete(klever_base_image.id)
