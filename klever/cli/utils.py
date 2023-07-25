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

import getpass
import logging
import subprocess
import sys

PROMPT = 'Password: '


def execute_cmd(logger, *args, **kwargs):
    logger.info('Execute command "{0}"'.format(' '.join(args)))

    get_output = kwargs.pop('get_output') if 'get_output' in kwargs else False

    if get_output:
        return subprocess.check_output(args, **kwargs).decode('utf-8').rstrip().split('\n')

    subprocess.check_call(args, **kwargs)
    return None


def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s (%(filename)s:%(lineno)03d) %(levelname)s> %(message)s',
                                  "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


def get_password(password):
    if password is not None and len(password) > 0:
        return password
    if sys.stdin.isatty():
        return getpass.getpass(PROMPT)

    print(PROMPT, end='', flush=True)
    return sys.stdin.readline().rstrip()
