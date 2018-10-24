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

from django.conf import settings
from django.urls import reverse

from bridge.populate import populate_users
from bridge.utils import KleverTestCase
from bridge.vars import USER_ROLES

from users.models import User, Extended
from jobs.models import Job
from marks.models import MarkUnknown, SafeTag, UnsafeTag
from service.models import Scheduler, SCHEDULER_TYPE


class TestPopulation(KleverTestCase):
    def test_index_page(self):
        # Create admin
        User.objects.create_superuser('admin', '', 'admin')

        response = self.client.get('/')
        self.assertRedirects(response, reverse('users:login'))
        self.client.post(reverse('users:login'), {'username': 'admin', 'password': 'admin'})
        response = self.client.get('/')
        self.assertRedirects(response, reverse('jobs:tree'))

    def test_population(self):
        # Create admin, manager and user with no access
        User.objects.create_superuser('admin', '', 'admin')
        User.objects.create_user(username='user', password='user')
        manager = User.objects.create_user(username='manager', password='manager')
        Extended.objects.create(user=manager, role=USER_ROLES[2][0])

        # Trying to get access without manager permission
        self.client.post(reverse('users:login'), {'username': 'user', 'password': 'user'})
        response = self.client.get(reverse('population'))
        self.assertEqual(response.status_code, 400)
        self.client.get(reverse('users:logout'))

        # Trying to get access with admin permission
        self.client.post(reverse('users:login'), {'username': 'admin', 'password': 'admin'})
        response = self.client.get(reverse('population'))
        self.assertEqual(response.status_code, 400)

        # Trying to get access with manager permission
        self.client.post(reverse('users:login'), {'username': 'manager', 'password': 'manager'})
        response = self.client.get(reverse('population'))
        self.assertEqual(response.status_code, 200)

        # Trying to populate without service username
        response = self.client.post(reverse('population'), {'service_username': ''})
        self.assertEqual(response.status_code, 400)

        # Normal population
        response = self.client.post(reverse('population'), {'service_username': 'service'})
        self.assertEqual(response.status_code, 200)

        # Testing populated service user
        self.assertEqual(Extended.objects.filter(user__username='service', role=USER_ROLES[4][0]).count(), 1)

        # Testing populated unknown marks
        num_of_preset_marks = 0
        for comp_dir in os.listdir(os.path.join(settings.BASE_DIR, 'marks', 'presets', 'unknowns')):
            if os.path.isdir(os.path.join(settings.BASE_DIR, 'marks', 'presets', 'unknowns', comp_dir)):
                num_of_preset_marks += len(os.listdir(os.path.join(
                    settings.BASE_DIR, 'marks', 'presets', 'unknowns', comp_dir)))

        if not settings.POPULATE_JUST_PRODUCTION_PRESETS:
            self.assertEqual(MarkUnknown.objects.count(), num_of_preset_marks)

        self.assertEqual(Scheduler.objects.filter(type=SCHEDULER_TYPE[0][0]).count(), 1)
        self.assertEqual(Scheduler.objects.filter(type=SCHEDULER_TYPE[1][0]).count(), 1)

        safe_tags_presets = os.path.join(settings.BASE_DIR, 'marks', 'tags_presets', 'safe.json')
        prepopulated_tags = set()
        if os.path.isfile(safe_tags_presets):
            with open(safe_tags_presets, encoding='utf8') as fp:
                data = json.load(fp)
            if not isinstance(data, list):
                self.fail('Wrong preset safe tags format')
            for t in data:
                if not isinstance(t, dict):
                    self.fail('Wrong preset safe tags format')
                if 'name' not in t:
                    self.fail('Safe tag name is required')
                prepopulated_tags.add((t['name'], t.get('parent'), t.get('description', '')))
        for st in SafeTag.objects.select_related('parent'):
            if st.parent is None:
                tag_data = (st.tag, None, st.description)

            else:
                tag_data = (st.tag, st.parent.tag, st.description)
            self.assertIn(tag_data, prepopulated_tags)
            prepopulated_tags.remove(tag_data)
        self.assertEqual(prepopulated_tags, set())

        unsafe_tags_presets = os.path.join(settings.BASE_DIR, 'marks', 'tags_presets', 'unsafe.json')
        prepopulated_tags = set()
        if os.path.isfile(unsafe_tags_presets):
            with open(unsafe_tags_presets, encoding='utf8') as fp:
                data = json.load(fp)
            if not isinstance(data, list):
                self.fail('Wrong preset unsafe tags format')
            for t in data:
                if not isinstance(t, dict):
                    self.fail('Wrong preset unsafe tags format')
                if 'name' not in t:
                    self.fail('Unsafe tag name is required')
                prepopulated_tags.add((t['name'], t.get('parent'), t.get('description', '')))
        for ut in UnsafeTag.objects.select_related('parent'):
            if ut.parent is None:
                tag_data = (ut.tag, None, ut.description)

            else:
                tag_data = (ut.tag, ut.parent.tag, ut.description)
            self.assertIn(tag_data, prepopulated_tags)
            prepopulated_tags.remove(tag_data)
        self.assertEqual(prepopulated_tags, set())

    def test_service_population(self):
        result = populate_users(
            admin={'username': 'admin', 'password': 'admin'},
            manager={'username': 'manager', 'password': 'manager'},
            service={'username': 'service', 'password': 'service'}
        )
        self.assertIsNone(result)
        self.assertEqual(Extended.objects.filter(user__username='manager', role=USER_ROLES[2][0]).count(), 1)
        self.assertEqual(Extended.objects.filter(user__username='service', role=USER_ROLES[4][0]).count(), 1)

        self.client.post(reverse('users:login'), {'username': 'manager', 'password': 'manager'})
        # Population after service and manager were created by function call
        response = self.client.post(reverse('population'))
        self.assertEqual(response.status_code, 200)
