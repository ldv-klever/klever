# Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
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

import os
import json

from uuid import UUID
from klever.cli.utils import get_args_parser, Session


def download_job():
    parser = get_args_parser('Download ZIP archive of verificaiton job.')
    parser.add_argument('job', type=UUID, help='Verification job identifier (uuid).')
    parser.add_argument('-o', '--out', help='ZIP archive name.')
    args = parser.parse_args()

    session = Session(args)
    arch = session.download_job(args.job, args.out)

    print('ZIP archive with verification job "{0}" was successfully downloaded to "{1}"'.format(args.job, arch))


def download_marks():
    parser = get_args_parser('Download ZIP archive of all expert marks.')
    parser.add_argument('-o', '--out', help='ZIP archive name.')
    args = parser.parse_args()

    session = Session(args)
    arch = session.download_all_marks(args.out)

    print('ZIP archive with all expert marks was successfully downloaded to "{0}"'.format(arch))


def download_progress():
    parser = get_args_parser('Download JSON file with solution progress of verification job.')
    parser.add_argument('job', type=UUID, help='Verification job identifier (uuid).')
    parser.add_argument('-o', '--out', help='JSON file name.', default='progress.json')
    args = parser.parse_args()

    session = Session(args)
    session.job_progress(args.job, args.out)

    print('JSON file with solution progress of verification job "{0}" was successfully downloaded to "{1}"'
          .format(args.job, args.out))


def download_results():
    parser = get_args_parser('Download JSON file with verification results of verificaiton job.')
    parser.add_argument('decision', type=UUID, help='Verification job decision identifier (uuid).')
    parser.add_argument('-o', '--out', help='JSON file name.', default='results.json')
    args = parser.parse_args()

    session = Session(args)
    session.decision_results(args.decision, args.out)

    print('JSON file with verification results of verificaiton job decision "{0}" was successfully downloaded to "{1}"'
          .format(args.job, args.out))


def start_preset_solution():
    parser = get_args_parser('Create and start solution of verification job created on the base of specified preset.')
    parser.add_argument('preset', type=UUID,
                        help='Preset job identifier (uuid). Can be obtained form presets/jobs/base.json')
    parser.add_argument(
        '--replacement',
        help='JSON file name or string with data what files should be replaced before starting solution.')
    parser.add_argument('--rundata', type=open,
                        help='JSON file name. Set it if you would like to start solution with specific settings.')
    args = parser.parse_args()

    session = Session(args)
    _, job_uuid = session.create_preset_job(args.preset, args.replacement)

    session.start_job_decision(job_uuid, args.rundata)

    print('Solution of verification job "{0}" was successfully started'.format(job_uuid))


def start_solution():
    parser = get_args_parser('Start solution of verification job.')
    parser.add_argument('job', type=UUID, help='Verification job identifier (uuid).')
    parser.add_argument('--copy', action='store_true',
                        help='Set it if you would like to copy verification job before starting solution.')
    parser.add_argument(
        '--replacement',
        help='JSON file name or string with data what files should be replaced before starting solution.')
    parser.add_argument('--rundata', type=open,
                        help='JSON file name. Set it if you would like to start solution with specific settings.')
    args = parser.parse_args()

    session = Session(args)
    job_uuid = args.job

    # Copy job if we need to change files or set --copy option
    if args.copy or args.replacement:
        job_uuid = session.copy_job(args.job, args.replacement)

    session.start_job_decision(job_uuid, args.rundata)

    print('Solution of verification job "{0}" was successfully started'.format(job_uuid))


def update_preset_mark():
    parser = get_args_parser('Update preset mark on the base of most relevant associated report and current version.')
    parser.add_argument('mark', type=str, help='Preset mark path.')
    parser.add_argument('--report', type=int,
                        help='Unsafe report primary key if you want specific error trace for update.')
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


def upload_job():
    parser = get_args_parser('Upload ZIP archive of verification job.')
    parser.add_argument('--parent', type=UUID, help='Parent verification job identifier (uuid). '
                                                    'By default the job will be uploaded to the root.')
    parser.add_argument('--archive', help='ZIP archive name.', required=True)
    args = parser.parse_args()

    if not os.path.exists(args.archive):
        raise FileNotFoundError('ZIP archive of verification job "{0}" does not exist'.format(args.archive))

    session = Session(args)
    session.upload_job(args.parent, args.archive)

    print('ZIP archive of verification job "{0}" was successfully uploaded. '
          'If archive is not corrupted the job will be soon created.'.format(args.archive))
