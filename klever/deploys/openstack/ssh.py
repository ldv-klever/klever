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
import paramiko
import subprocess
import sys
import tarfile
import time
import zipfile

from klever.deploys.utils import execute_cmd, get_password
from klever.deploys.openstack.constants import OS_USER


class SSH:
    CONNECTION_ATTEMPTS = 30
    CONNECTION_RECOVERY_INTERVAL = 10
    COMMAND_EXECUTION_CHECK_INTERVAL = 0.1
    COMMAND_EXECUTION_STREAM_BUF_SIZE = 10000

    def __init__(self, args, logger, name, floating_ip):
        if not args.ssh_rsa_private_key_file:
            logger.error('Please specify path to SSH RSA private key file with help of command-line option'
                         ' --ssh-rsa-private-key-file')
            sys.exit(errno.EINVAL)

        self.args = args
        self.logger = logger
        self.name = name
        self.floating_ip = floating_ip

    def __enter__(self):
        self.logger.info('Open SSH session to instance "{0}" (IP: {1})'.format(self.name, self.floating_ip))

        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            k = paramiko.RSAKey.from_private_key_file(self.args.ssh_rsa_private_key_file)
        except paramiko.ssh_exception.PasswordRequiredException:
            if hasattr(self.args, 'key_password'):
                key_password = self.args.key_password
            else:
                key_password = get_password(self.logger, 'Private key password: ')

            try:
                k = paramiko.RSAKey.from_private_key_file(self.args.ssh_rsa_private_key_file, key_password)
            except paramiko.ssh_exception.SSHException:
                self.logger.error('Incorrect password for private key')
                sys.exit(errno.EACCES)

        attempts = self.CONNECTION_ATTEMPTS

        while attempts > 0:
            try:
                self.ssh.connect(hostname=self.floating_ip, username=self.args.ssh_username, pkey=k)
                return self
            except Exception:
                attempts -= 1
                self.logger.info('Could not open SSH session, wait for {0} seconds and try {1} times more'
                                 .format(self.CONNECTION_RECOVERY_INTERVAL, attempts))
                time.sleep(self.CONNECTION_RECOVERY_INTERVAL)

        self.logger.error('Could not open SSH session')
        sys.exit(errno.EPERM)

    def __exit__(self, etype, value, traceback):
        self.logger.info('Close SSH session to instance "{0}" (IP: {1})'.format(self.name, self.floating_ip))
        self.ssh.close()

    def execute_cmd(self, cmd, timeout=COMMAND_EXECUTION_CHECK_INTERVAL):
        self.logger.info('Execute command over SSH on instance "{0}" (IP: {1})\n{2}'
                         .format(self.name, self.floating_ip, cmd))

        chan = self.ssh.get_transport().open_session()
        chan.setblocking(0)
        chan.exec_command(cmd)

        # Print command STDOUT and STDERR until it will be executed.
        while not chan.exit_status_ready():
            stderr = ''
            while chan.recv_stderr_ready():
                stderr += chan.recv_stderr(self.COMMAND_EXECUTION_STREAM_BUF_SIZE).decode(encoding='utf8')
            stderr = stderr.rstrip()

            if stderr:
                print('Executed command STDERR:\n"{}"'.format(stderr))

            stdout = ''
            while chan.recv_ready():
                stdout += chan.recv(self.COMMAND_EXECUTION_STREAM_BUF_SIZE).decode(encoding='utf8')
            stdout = stdout.rstrip()

            if stdout:
                print(stdout)
            time.sleep(timeout)

        retcode = chan.recv_exit_status()

        if retcode:
            self.logger.error('Command exitted with {0}'.format(retcode))
            sys.exit(errno.EPERM)

    def open_shell(self):
        self.logger.info('Open interactive SSH to instance "{0}" (IP: {1})'.format(self.name, self.floating_ip))

        execute_cmd(self.logger, 'ssh', '-o', 'StrictHostKeyChecking=no', '-i', self.args.ssh_rsa_private_key_file,
                    '{0}@{1}'.format(self.args.ssh_username, self.floating_ip))

    def rsync(self, host_path, instance_path):
        if instance_path:
            self.execute_cmd(f'mkdir -p {instance_path}')
        else:
            instance_path = "~/"

        if os.path.isfile(host_path) and (tarfile.is_tarfile(host_path) or zipfile.is_zipfile(host_path)):
            rsync_flags = '-ar'
        else:
            # with -z flag rsync compresses the transmitted data
            rsync_flags = '-arz'

        # stderr=subprocess.DEVNULL is required to suppress WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!
        # maybe there is a better way to fix it
        execute_cmd(
            self.logger,
            'rsync', rsync_flags,
            '-e', f'ssh -o StrictHostKeyChecking=no -i {self.args.ssh_rsa_private_key_file}',
            host_path,
            f'{OS_USER}@{self.floating_ip}:{instance_path}',
            stderr=subprocess.DEVNULL
        )
