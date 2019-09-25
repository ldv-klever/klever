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

from django.core.management.base import BaseCommand, CommandError

from reports.test import DecideJobs, SJC_1, SJC_2, SJC_3, SJC_4, NSJC_1, NSJC_2, NSJC_3


class Command(BaseCommand):
    help = 'Used to decide jobs with fake data.'
    requires_migrations_checks = True

    def add_arguments(self, parser):
        data_choices = list(str(x) for x in range(10))
        parser.add_argument('--username', dest='username', default='service', help='Specifies the service username.')
        parser.add_argument('--password', dest='password', default='service', help='Specifies the service password.')
        parser.add_argument(
            '--data', choices=data_choices, default=data_choices[0],
            help="The user role (0 - SJC_1, 1 - SJC_2, 2 - SJC_3, 3 - SJC_4, 4 - NSJC_1, 5 - NSJC_2, 6 - NSJC_3)"
        )
        parser.add_argument('--progress', dest='with_progress', action='store_true', help='Decision with progress?')
        parser.add_argument(
            '--coverage', dest='with_full_coverage', action='store_true',
            help='Decision with global coverages?'
        )
        parser.add_argument('--queue', dest='queue_name', help='Queue name. Default is from settings.')

    def handle(self, *args, **options):
        data_id = int(options.pop('data'))
        if data_id == 0:
            data = SJC_1
        elif data_id == 1:
            data = SJC_2
        elif data_id == 2:
            data = SJC_3
        elif data_id == 3:
            data = SJC_4
        elif data_id == 4:
            data = NSJC_1
        elif data_id == 5:
            data = NSJC_2
        elif data_id == 6:
            data = NSJC_3
        else:
            raise CommandError('Unknown data identifier: %s' % data_id)
        if not options.get('queue_name'):
            options.pop('queue_name', None)
        DecideJobs(data, **options)
