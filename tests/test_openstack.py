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
import json
import os
import pytest
import subprocess
import time
import random

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
    credentials = ('--host', f'{instance_ip}:8998', '--username', 'manager', '--password', 'manager')

    decision_conf = os.path.join(os.path.dirname(__file__), 'decision.conf')
    ret = subprocess.check_output(
        ('klever-start-preset-solution', '--rundata', decision_conf, preset_job_id, *credentials)
    ).decode('utf8').rstrip()
    job_id = ret[ret.find(': ') + 2:]

    while True:
        time.sleep(5)
        subprocess.check_call(
            ('klever-download-progress', '-o', '/tmp/progress.json', job_id, *credentials),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        with open('/tmp/progress.json') as fp:
            progress = json.load(fp)

        if int(progress['status']) > 2:
            break

    assert progress['status'] == '3'


def solve_all_jobs(instance_ip):
    solve_job('c1529fbf-a7db-4507-829e-55f846044309', instance_ip)
    solve_job('573d4ea2-574b-4f7b-b86c-79182d9e1502', instance_ip)
    solve_job('019debae-9991-421c-bfd8-53e3c38b4b37', instance_ip)


@pytest.mark.parametrize('mode', ['development', 'production'])
def test_deploy(mode):
    instance_name = get_instance_name(mode=mode)
    klever_deploy_openstack(instance_name, 'create', 'instance', mode=mode)

    try:
        instance_ip = get_instance_floating_ip(instance_name)
        solve_all_jobs(instance_ip)
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
        klever_deploy_openstack(instance_name, 'resize', 'instance', vcpus='2', ram='8')
    finally:
        klever_deploy_openstack(instance_name, 'remove', 'instance')


@pytest.mark.parametrize('mode', ['development', 'production'])
def test_update(mode):
    instance_name = 'klever-pytest-' + mode
    klever_deploy_openstack(instance_name, 'update', 'instance')

    instance_ip = get_instance_floating_ip(instance_name)
    solve_all_jobs(instance_ip)


def test_list():
    klever_deploy_openstack('.*klever.*', 'show', 'instance')
