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

import logging
import os
import paramiko
import select
import socket
import sys
import termios
import time
import tty


class SSH:
    CONNECTION_ATTEMPTS = 30
    CONNECTION_RECOVERY_INTERVAL = 10
    COMMAND_EXECUTION_CHECK_INTERVAL = 3
    COMMAND_EXECUTION_STREAM_BUF_SIZE = 10000

    def __init__(self, args, name, floating_ip):
        if not args.ssh_rsa_private_key_file:
            raise ValueError('Please specify path to SSH RSA private key file with help of command-line option --ssh-rsa-private-key-file')

        self.args = args
        self.name = name
        self.floating_ip = floating_ip

    def __enter__(self):
        logging.info('Establish SSH connection to instance "{0}" (IP: {1})'.format(self.name, self.floating_ip))

        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        k = paramiko.RSAKey.from_private_key_file(self.args.ssh_rsa_private_key_file)

        attempts = self.CONNECTION_ATTEMPTS

        while attempts > 0:
            try:
                self.ssh.connect(hostname=self.floating_ip, username=self.args.ssh_username, pkey=k)
                return self
            except:
                attempts -= 1
                logging.exception(
                    'Could not establish SSH connection, wait for {0} seconds and try {1} times more'
                    .format(self.CONNECTION_RECOVERY_INTERVAL, attempts))
                time.sleep(self.CONNECTION_RECOVERY_INTERVAL)

        raise RuntimeError('Could not establish SSH connection')

    def __exit__(self, etype, value, traceback):
        logging.info('Close SSH connection to instance "{0}" (IP: {1})'.format(self.name, self.floating_ip))
        self.ssh.close()

    def execute_cmd(self, cmd):
        logging.info('Execute command over SSH on instance "{0}" (IP: {1})\n{2}'
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
                    logging.info('Executed command STDERR:{0}'.format(stderr.rstrip()))
                stdout = ''
                while chan.recv_ready():
                    stdout += chan.recv(self.COMMAND_EXECUTION_STREAM_BUF_SIZE).decode(encoding='utf8')
                if stdout:
                    logging.info('Executed command STDOUT:{0}'.format(stdout.rstrip()))
            time.sleep(self.COMMAND_EXECUTION_CHECK_INTERVAL)

        retcode = chan.recv_exit_status()

        if retcode:
            raise RuntimeError('Command exitted with {0}'.format(retcode))

    def get(self, src, dest):
        try:
            sftp = self.ssh.open_sftp()
            sftp.get(src, dest)
        finally:
            sftp.close()

    def open_shell(self):
        logging.info('Open interactive SSH to instance "{0}" (IP: {1})'.format(self.name, self.floating_ip))

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

    def put(self, src):
        try:
            sftp = self.ssh.open_sftp()
            if os.path.isfile(src):
                sftp.put(src, os.path.basename(src))
            else:
                raise NotImplementedError
        finally:
            sftp.close()
