#!/usr/local/python3-klever/bin/python3
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

from uuid import UUID

from utils.utils import get_args_parser, Session

parser = get_args_parser('Create and start solution of verification job created on the base of specified preset.')
parser.add_argument('preset', type=UUID,
                    help='Preset job identifier (uuid). Can be obtained form presets/jobs/base.json')
parser.add_argument('--replacement',
                    help='JSON file name or string with data what files should be replaced before starting solution.')
parser.add_argument('--rundata', type=open,
                    help='JSON file name. Set it if you would like to start solution with specific settings.')
args = parser.parse_args()

session = Session(args)
job_id, job_uuid = session.create_preset_job(args.preset)

# Replace files before start
if args.replacement:
    session.replace_files(job_uuid, args.replacement)

session.start_job_decision(job_uuid, args.rundata)

print('Solution of verification job "{0}" was successfully started'.format(job_uuid))
