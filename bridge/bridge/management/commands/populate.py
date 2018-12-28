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

from bridge.vars import USER_ROLES
from users.models import User
from jobs.population import JobsPopulation


class Command(BaseCommand):
    help = 'Populates jobs, marks and tags.'
    requires_migrations_checks = True

    def add_arguments(self, parser):
        parser.add_argument('--all', dest='all', action='store_true', help='Populate everything?')
        parser.add_argument('--jobs', dest='jobs', action='store_true', help='Populate jobs?')
        parser.add_argument('--marks', dest='marks', action='store_true', help='Populate all marks?')
        parser.add_argument('--safe-marks', dest='marks_s', action='store_true', help='Populate safe marks?')
        parser.add_argument('--unsafe-marks', dest='marks_u', action='store_true', help='Populate unsafe marks?')
        parser.add_argument('--unknown-marks', dest='marks_f', action='store_true', help='Populate unknown marks?')
        parser.add_argument('--tags', dest='tags', action='store_true', help='Populate all tags?')
        parser.add_argument('--safe-tags', dest='tags_s', action='store_true', help='Populate safe tags?')
        parser.add_argument('--unsafe-tags', dest='tags_u', action='store_true', help='Populate unsafe tags?')

    def handle(self, *args, **options):
        # Jobs
        if options['all'] or options['jobs']:
            self.stdout.write('Jobs population started')
            try:
                res = JobsPopulation().populate()
            except Exception as e:
                raise
                raise CommandError('Jobs population failed: %s' % e)
            self.stdout.write("Jobs were populated successfully. Number of new jobs: %s" % len(res))

        # Safe marks
        if options['all'] or options['marks'] or options['marks_s']:
            self.stdout.write('Safe marks population started')
            res = []
            self.stdout.write("Safe marks were populated successfully. Number of new marks: %s" % len(res))

        # Unsafe marks
        if options['all'] or options['marks'] or options['marks_u']:
            self.stdout.write('Unsafe marks population started')
            res = []
            self.stdout.write("Unsafe marks were populated successfully. Number of new marks: %s" % len(res))

        # Unknown marks
        if options['all'] or options['marks'] or options['marks_f']:
            self.stdout.write('Unknown marks population started')
            res = []
            self.stdout.write("Unknown marks were populated successfully. Number of new marks: %s" % len(res))

        # Safe tags
        if options['all'] or options['tags'] or options['tags_s']:
            self.stdout.write('Safe tags population started')
            res = []
            self.stdout.write("Safe tags were populated successfully. Number of new tags: %s" % len(res))

        # Unsafe tags
        if options['all'] or options['tags'] or options['tags_u']:
            self.stdout.write('Unsafe tags population started')
            res = []
            self.stdout.write("Unsafe tags were populated successfully. Number of new tags: %s" % len(res))

        self.stdout.write('Population was successfully finished')
