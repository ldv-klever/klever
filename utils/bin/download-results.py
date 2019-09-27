#!/usr/bin/env python3
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

from utils.utils import get_args_parser, Session

parser = get_args_parser('Download JSON file with verification results of verificaiton job.')
parser.add_argument('job', help='Verification job identifier or its name.')
parser.add_argument('-o', '--out', help='JSON file name.', default='results.json')
args = parser.parse_args()

session = Session(args)
session.decision_results(args.job, args.out)

print('JSON file with verification results of verificaiton job "{0}" was successfully downloaded to "{1}"'
      .format(args.job, args.out))
