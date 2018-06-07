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

import errno
import os
import paramiko
import select
import socket
import sys
import tarfile
import tempfile
import termios
import time
import tty

from deploys.utils import get_password


class SSH:
    CONNECTION_ATTEMPTS = 30
    CONNECTION_RECOVERY_INTERVAL = 10
    COMMAND_EXECUTION_CHECK_INTERVAL = 3
    COMMAND_EXECUTION_STREAM_BUF_SIZE = 10000

    def __init__(self, args, logger, name, floating_ip, open_sftp=True):
        if not args.ssh_rsa_private_key_file:
            self.logger.error('Please specify path to SSH RSA private key file with help of command-line option' +
                              ' --ssh-rsa-private-key-file')
            sys.exit(errno.EINVAL)

        self.args = args
        self.logger = logger
        self.name = name
        self.floating_ip = floating_ip
        self.open_sftp = open_sftp

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

                if self.open_sftp:
                    self.logger.info(
                        'Open SFTP session to instance "{0}" (IP: {1})'.format(self.name, self.floating_ip))
                    self.sftp = self.ssh.open_sftp()

                return self
            except:
                attempts -= 1
                self.logger.warning('Could not open SSH session, wait for {0} seconds and try {1} times more'
                                    .format(self.CONNECTION_RECOVERY_INTERVAL, attempts))
                time.sleep(self.CONNECTION_RECOVERY_INTERVAL)

        self.logger.error('Could not open SSH session')
        sys.exit(errno.EPERM)

    def __exit__(self, etype, value, traceback):
        if self.open_sftp:
            self.logger.info(
                'Close SFTP session to instance "{0}" (IP: {1})'.format(self.name, self.floating_ip))
            self.sftp.close()

        self.logger.info('Close SSH session to instance "{0}" (IP: {1})'.format(self.name, self.floating_ip))
        self.ssh.close()

    def execute_cmd(self, cmd):
        self.logger.info('Execute command over SSH on instance "{0}" (IP: {1})\n{2}'
                         .format(self.name, self.floating_ip, cmd))

        chan = self.ssh.get_transport().open_session()
        chan.setblocking(0)
        chan.exec_command(cmd)

        # Print command STDOUT and STDERR until it will be executed.
        while True:
            try:
                if chan.exit_status_ready():
                    break
            finally:
                stderr = ''
                while chan.recv_stderr_ready():
                    stderr += chan.recv_stderr(self.COMMAND_EXECUTION_STREAM_BUF_SIZE).decode(encoding='utf8')
                if stderr:
                    self.logger.info('Executed command STDERR:\n{0}'.format(stderr.rstrip()))
                stdout = ''
                while chan.recv_ready():
                    stdout += chan.recv(self.COMMAND_EXECUTION_STREAM_BUF_SIZE).decode(encoding='utf8')
                if stdout:
                    self.logger.info('Executed command STDOUT:\n{0}'.format(stdout.rstrip()))
            time.sleep(self.COMMAND_EXECUTION_CHECK_INTERVAL)

        retcode = chan.recv_exit_status()

        if retcode:
            self.logger.error('Command exitted with {0}'.format(retcode))
            sys.exit(errno.EPERM)

    def open_shell(self):
        self.logger.info('Open interactive SSH to instance "{0}" (IP: {1})'.format(self.name, self.floating_ip))
        self.logger.warning(
            'Just simple operations can be peformed, for the complex ones, please, run "{0}"'
            .format('ssh -o StrictHostKeyChecking=no -i {0} {1}@{2}'
                    .format(self.args.ssh_rsa_private_key_file, self.args.ssh_username, self.floating_ip)))

        chan = self.ssh.get_transport().open_session()
        chan.get_pty()
        chan.invoke_shell()

        # https://github.com/paramiko/paramiko/blob/master/demos/interactive.py (commit 15aa741).
        oldtty = termios.tcgetattr(sys.stdin)

        try:
            tty.setraw(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
            chan.settimeout(0.0)

            while True:
                r, w, e = select.select([chan, sys.stdin], [], [])
                if chan in r:
                    try:
                        x = chan.recv(self.COMMAND_EXECUTION_STREAM_BUF_SIZE).decode(encoding='utf8')
                        if len(x) == 0:
                            break
                        sys.stdout.write(x)
                        sys.stdout.flush()
                    except socket.timeout:
                        pass
                if sys.stdin in r:
                    x = sys.stdin.read(1)
                    if len(x) == 0:
                        break
                    chan.send(x)
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, oldtty)

    def sftp_put(self, host_path, instance_path, sudo=False, directory=None, ignore=None):
        self.logger.info('Copy "{0}" to "{1}"'
                         .format(host_path,
                                 os.path.join(directory if directory else '', instance_path)))

        # Always transfer files using compressed tar archives to preserve file permissions and reduce net load.
        with tempfile.NamedTemporaryFile(suffix='.tar.gz') as fp:
            instance_archive = os.path.basename(fp.name)
            with tarfile.open(fileobj=fp, mode='w:gz') as TarFile:
                TarFile.add(host_path, os.path.normpath(instance_path),
                            exclude=lambda path: any(path.endswith(ignore_path) for ignore_path in ignore))
            fp.flush()
            fp.seek(0)
            self.sftp.putfo(fp, instance_archive)

        # TODO: get rid of numerous warnings like "tar: ...: time stamp 2018-06-04 11:14:25 is 109.824694369 s in the future".
        # Use sudo to allow extracting archives outside home directory.
        self.execute_cmd('{0} -xf {1}'
                         .format(('sudo ' if sudo else '') + 'tar' + (' -C ' + directory if directory else ''),
                                 instance_archive))
        self.execute_cmd('rm ' + instance_archive)
