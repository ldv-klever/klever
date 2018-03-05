#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
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
import argparse

from utils import Session


parser = argparse.ArgumentParser(description='Obtaining solution progress in json format.')
parser.add_argument('identifier', nargs='?', help='Job identifier')
parser.add_argument('--config', help='Server configuration file in json format', required=True, type=open)
parser.add_argument('--host', help='Server host, set it if you want to override server config')
parser.add_argument('--username', help='Your username, set it if you want to override server config')
parser.add_argument('--password', help='Your password, set it if you want to override server config')
parser.add_argument('-o', '--out', help='Where to store json data', required=True)

args = parser.parse_args()

conf = json.load(args.config)
if not isinstance(conf, dict):
    raise ValueError("Server configuration must be a dictionary")

session = Session(
    args.host or conf.get('host'),
    args.username or conf.get('username'),
    args.password or conf.get('password')
)
session.job_progress(args.identifier, args.out)
session.sign_out()
print('Progress data were successfully saved to {0}'.format(args.out))
