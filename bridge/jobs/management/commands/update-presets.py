#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

from django.core.management.base import BaseCommand
from jobs.preset import PopulatePresets


class Command(BaseCommand):
    help = 'Used to populate (update) preset jobs and files and store check date if files were changed.'
    requires_migrations_checks = True

    def handle(self, *args, **options):
        PopulatePresets().populate()
        if options['verbosity'] >= 1:
            self.stdout.write("Preset jobs and files were successfully populated.")
