#!/usr/bin/env python3
#
# Copyright (c) 2017 ISPRAS (http://www.ispras.ru)
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

import json
import os
import subprocess


class Cd:
    def __init__(self, path):
        self.new_path = path

    def __enter__(self):
        self.prev_path = os.getcwd()
        os.chdir(self.new_path)

    def __exit__(self, etype, value, traceback):
        os.chdir(self.prev_path)


def execute_cmd(*args, stdin=None, get_output=False):
    print('Execute command "{0}"'.format(' '.join(args)))
    if get_output:
        return subprocess.check_output(args, stdin=stdin).decode('utf8')
    else:
        subprocess.check_call(args, stdin=stdin)


def get_klever_addon_abs_path(prev_deploy_info, name, verification_backend=False):
    klever_addon_desc = prev_deploy_info['Klever Addons']['Verification Backends'][name] \
        if verification_backend is True else prev_deploy_info['Klever Addons'][name]
    return os.path.abspath(os.path.join('klever-addons', 'verification-backends' if verification_backend else '', name,
                                        klever_addon_desc.get('executable path', '')))


def configure_native_scheduler_task_worker(deploy_dir, prev_deploy_info):
    print('Configure Klever Native Scheduler Task Worker')

    with Cd(deploy_dir):
        with open('klever/scheduler/conf/task-client.json') as fp:
            task_client_conf = json.load(fp)

        task_client_conf['client']['benchexec location'] = get_klever_addon_abs_path(prev_deploy_info, 'BenchExec')
        verification_backends = task_client_conf['client']['verification tools'] = {}

        for name, desc in prev_deploy_info['Klever Addons']['Verification Backends'].items():
            if desc['name'] not in verification_backends:
                verification_backends[desc['name']] = {}
            verification_backends[desc['name']][desc['version']] = get_klever_addon_abs_path(prev_deploy_info, name,
                                                                                             verification_backend=True)

        with open('klever-conf/native-scheduler-task-client.json', 'w') as fp:
            json.dump(task_client_conf, fp, sort_keys=True, indent=4)


def configure_controller_and_schedulers(deploy_dir, prev_deploy_info):
    print('(Re)configure Klever Controller and Klever schedulers')

    print('Stop services')
    services = ('klever-controller', 'klever-native-scheduler', 'klever-verifiercloud-scheduler')
    for service in services:
        execute_cmd('service', service, 'stop')

    deploy_dir_abs = os.path.realpath(deploy_dir)

    with Cd(deploy_dir):
        print('Configure Klever Controller')
        with open('klever/scheduler/conf/controller.json') as fp:
            controller_conf = json.load(fp)

        controller_conf['common']['working directory'] = os.path.join(deploy_dir_abs, 'klever-work/controller')
        controller_conf['Klever Bridge'].update({
            'user': 'service',
            'password': 'service'
        })
        controller_conf['client-controller']['consul'] = get_klever_addon_abs_path(prev_deploy_info, 'Consul')

        with open('klever-conf/controller.json', 'w') as fp:
            json.dump(controller_conf, fp, sort_keys=True, indent=4)

        print('Configure Klever Native Scheduler')
        with open('klever/scheduler/conf/native-scheduler.json') as fp:
            native_scheduler_conf = json.load(fp)

        native_scheduler_conf['common']['working directory'] = os.path.join(deploy_dir_abs,
                                                                            'klever-work/native-scheduler')
        native_scheduler_conf['Klever Bridge'].update({
            'user': 'service',
            'password': 'service'
        })
        native_scheduler_conf['scheduler'].update({
            'disable CPU cores account': True,
            'job client configuration': os.path.abspath('klever-conf/native-scheduler-job-client.json'),
            'task client configuration': os.path.abspath('klever-conf/native-scheduler-task-client.json')
        })

        with open('klever-conf/native-scheduler.json', 'w') as fp:
            json.dump(native_scheduler_conf, fp, sort_keys=True, indent=4)

        print('Configure Klever Native Scheduler Job Worker')
        with open('klever/scheduler/conf/job-client.json') as fp:
            job_client_conf = json.load(fp)

        job_client_conf['client'] = {
            'benchexec location': get_klever_addon_abs_path(prev_deploy_info, 'BenchExec'),
            'cif location': get_klever_addon_abs_path(prev_deploy_info, 'CIF'),
            'cil location': get_klever_addon_abs_path(prev_deploy_info, 'CIL')
        }

        with open('klever-conf/native-scheduler-job-client.json', 'w') as fp:
            json.dump(job_client_conf, fp, sort_keys=True, indent=4)

        print('Configure Klever VerifierCloud Scheduler')
        with open('klever/scheduler/conf/verifiercloud-scheduler.json') as fp:
            verifiercloud_scheduler_conf = json.load(fp)

        verifiercloud_scheduler_conf['common']['working directory'] = \
            os.path.join(deploy_dir_abs, 'klever-work/verifiercloud-scheduler')
        verifiercloud_scheduler_conf['Klever Bridge'].update({
            'user': 'service',
            'password': 'service'
        })
        verifiercloud_scheduler_conf['scheduler']['web client location'] =\
            get_klever_addon_abs_path(prev_deploy_info, 'VerifierCloud Client')

        with open('klever-conf/verifiercloud-scheduler.json', 'w') as fp:
            json.dump(verifiercloud_scheduler_conf, fp, sort_keys=True, indent=4)

    configure_native_scheduler_task_worker(deploy_dir, prev_deploy_info)

    print('Start services')
    for service in services:
        execute_cmd('service', service, 'start')


if __name__ == '__main__':
    pass
