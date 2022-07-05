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
import time
import random

from klever.cli import Cli
from klever.deploys.utils import get_logger
from klever.deploys.openstack.client import OSClient


def get_os_username():
    return os.environ.get('OPENSTACK_USER', getpass.getuser())


def get_instance_name(mode='production'):
    return get_os_username() + '-klever-pytest-' + mode + '-' + str(random.randint(100, 999))


def klever_deploy_openstack(name, action, entity, vcpus='2', ram='8', disk='50', mode='production', os_network_type='internal'):
    args = [
        'klever-deploy-openstack',
        '--ssh-rsa-private-key-file', os.environ.get('OPENSTACK_KEY', os.path.expanduser('~/.ssh/ldv.key')),
        '--os-username', get_os_username(),
        '--name', name,
        '--vcpus', vcpus,
        '--ram', ram,
        '--disk', disk,
        '--log-level', 'DEBUG',
        '--mode', mode,
        '--os-network-type', os_network_type,
        '--non-interactive',
        action,
        entity
    ]

    # Note that only strings are allowed by join, no argument should be an integer
    print("Execute command:", ' '.join(args))
    r = subprocess.run(args)

    assert r.returncode == 0


def get_instance_floating_ip(instance_name):
    client = OSClient(get_logger(__name__, 'ERROR'), get_os_username())
    return client.get_instance_floating_ip(client.get_instance(instance_name))


def solve_job(preset_job_id, instance_ip):
    print(f'Solve {preset_job_id} job')

    cli = Cli(host=f'{instance_ip}:8998', username='manager', password='manager')
    decision_conf = os.path.join(os.path.dirname(__file__), 'decision.conf')

    job_id = cli.create_job(preset_job_id)[1]
    decision_id = cli.start_job_decision(job_id, rundata=decision_conf)[1]

    while True:
        time.sleep(5)
        progress = cli.decision_progress(decision_id)

        if int(progress['status']) > 2:
            break

    assert progress['status'] == '3'


@pytest.mark.parametrize('mode', ['development', 'production'])
def test_deploy(mode):
    instance_name = get_instance_name(mode=mode)
    klever_deploy_openstack(instance_name, 'create', 'instance', mode=mode)

    try:
        instance_ip = get_instance_floating_ip(instance_name)
        solve_job('019debae-9991-421c-bfd8-53e3c38b4b37', instance_ip)
    finally:
        klever_deploy_openstack(instance_name, 'remove', 'instance')


@pytest.mark.parametrize('os_network_type', ['internal', 'external'])
def test_share_hide(os_network_type):
    instance_name = get_instance_name()
    klever_deploy_openstack(instance_name, 'create', 'instance', os_network_type=os_network_type)

    try:
        if os_network_type == 'internal':
            klever_deploy_openstack(instance_name, 'share', 'instance')
        else:
            klever_deploy_openstack(instance_name, 'hide', 'instance')
    finally:
        klever_deploy_openstack(instance_name, 'remove', 'instance')


def test_resize():
    instance_name = get_instance_name()
    klever_deploy_openstack(instance_name, 'create', 'instance')

    try:
        klever_deploy_openstack(instance_name, 'resize', 'instance', vcpus='1', ram='4')
    finally:
        klever_deploy_openstack(instance_name, 'remove', 'instance')


@pytest.mark.parametrize('mode', ['development', 'production'])
def test_update(mode):
    instance_name = 'klever-pytest-' + mode
    klever_deploy_openstack(instance_name, 'update', 'instance')

    instance_ip = get_instance_floating_ip(instance_name)
    solve_job('019debae-9991-421c-bfd8-53e3c38b4b37', instance_ip)


def test_list():
    klever_deploy_openstack('.*klever.*', 'show', 'instance')
