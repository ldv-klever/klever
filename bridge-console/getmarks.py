#!/usr/bin/env python3
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

import argparse

from utils import Session


parser = argparse.ArgumentParser(description='All marks download.')
parser.add_argument('--host', required=True, help='Server host')
parser.add_argument('--username', required=True, help='Your username')
parser.add_argument('--password', required=True, help='Your password')
parser.add_argument('-o', '--out', help='Downloaded archive name')

args = parser.parse_args()

session = Session(args.host, args.username, args.password)

arch = session.download_all_marks(args.out)
session.sign_out()
print('Marks archive was successfully saved to {0}'.format(arch))
