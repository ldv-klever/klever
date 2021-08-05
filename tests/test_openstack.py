# Copyright (c) 2021 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import getpass
import os
import pytest
import subprocess
import random


def klever_deploy_openstack(name, action, entity, vcpus='1', ram='4', disk='50', mode='production', os_network_type='internal'):
    args = [
        'klever-deploy-openstack',
        '--ssh-rsa-private-key-file', os.environ.get('OPENSTACK_KEY', os.path.expanduser('~/.ssh/ldv.key')),
        '--os-username', os.environ.get('OPENSTACK_USER', getpass.getuser()),
        '--name', name,
        '--vcpus', vcpus,
        '--ram', ram,
        '--disk', disk,
        '--log-level', 'DEBUG',
        '--mode', mode,
        '--os-network-type', os_network_type,
        action,
        entity
    ]

    # Note that only strings are allowed by join, no argument should be an integer
    print("Execute command:", ' '.join(args))
    r = subprocess.run(args)

    assert r.returncode == 0


@pytest.mark.parametrize('mode', ['development', 'production'])
@pytest.mark.parametrize('os_network_type', ['internal', 'external'])
def test_deploy(mode, os_network_type):
    instance_name = getpass.getuser() + '-klever-pytest-' + mode + '-' + str(random.randint(100, 999))
    klever_deploy_openstack(instance_name, 'create', 'instance', mode=mode, os_network_type=os_network_type)

    try:
        klever_deploy_openstack(instance_name, 'update', 'instance')

        if os_network_type == 'internal':
            klever_deploy_openstack(instance_name, 'share', 'instance')
        else:
            klever_deploy_openstack(instance_name, 'hide', 'instance')
    finally:
        klever_deploy_openstack(instance_name, 'remove', 'instance')


def test_resize():
    instance_name = getpass.getuser() + '-klever-pytest-' + str(random.randint(100, 999))
    klever_deploy_openstack(instance_name, 'create', 'instance')

    try:
        klever_deploy_openstack(instance_name, 'resize', 'instance', vcpus='2', ram='8')
    finally:
        klever_deploy_openstack(instance_name, 'remove', 'instance')


@pytest.mark.parametrize('mode', ['development', 'production'])
def test_update(mode):
    instance_name = 'klever-pytest-' + mode
    klever_deploy_openstack(instance_name, 'update', 'instance')
