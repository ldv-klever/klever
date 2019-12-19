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

import os
import json

from uuid import UUID
from utils.utils import get_args_parser, Session

parser = get_args_parser('Update preset mark on the base of most relevant associated report and current version.')
parser.add_argument('mark', type=str, help='Preset mark path.')
parser.add_argument('--report', type=int, help='Unsafe report primary key if you want specific error trace for update.')
args = parser.parse_args()

session = Session(args)

mark_path = os.path.abspath(args.mark)
if not os.path.isfile(mark_path):
    raise ValueError('The preset mark file was not found')

mark_identifier = UUID(os.path.splitext(os.path.basename(mark_path))[0])
mark_data = session.get_updated_preset_mark(mark_identifier, args.report)
with open(mark_path, mode='w', encoding='utf-8') as fp:
    json.dump(mark_data, fp, indent=2, sort_keys=True, ensure_ascii=False)

print('Preset mark "{0}" was successfully updated'.format(mark_identifier))
