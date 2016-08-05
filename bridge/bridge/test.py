import os
import json
from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from bridge.populate import populate_users
from bridge.settings import BASE_DIR
from bridge.utils import KleverTestCase
from bridge.vars import JOB_CLASSES, USER_ROLES
from users.models import User, Extended
from jobs.models import Job
from marks.models import MarkUnknown, SafeTag, UnsafeTag
from service.models import Scheduler, SCHEDULER_TYPE


class TestPopulation(KleverTestCase):
    def setUp(self):
        super(TestPopulation, self).setUp()
        User.objects.create_superuser('superuser', '', 'top_secret')
        User.objects.create_user(username='user', password='top_secret2')

    def test_index_page(self):
        response = self.client.get('/')
        self.assertRedirects(response, reverse('users:login'))
        self.client.post(reverse('users:login'), {'username': 'superuser', 'password': 'top_secret'})
        response = self.client.get('/')
        self.assertRedirects(response, reverse('jobs:tree'))

    def test_error_page(self):
        response = self.client.get(reverse('error', args=[500]))
        self.assertEqual(response.status_code, 200)

    def test_population(self):
        # Trying to get access without superuser permission
        self.client.post(reverse('users:login'), {'username': 'user', 'password': 'top_secret2'})
        response = self.client.get(reverse('population'))
        self.assertRedirects(response, reverse('error', args=[300]))
        self.client.get(reverse('users:logout'))

        # Trying to get access with superuser permission
        self.client.post(reverse('users:login'), {'username': 'superuser', 'password': 'top_secret'})
        response = self.client.get(reverse('population'))
        self.assertEqual(response.status_code, 200)

        # Trying to populate without service username
        response = self.client.post(reverse('population'), {
            'manager_username': 'superuser', 'service_username': ''
        })
        self.assertRedirects(response, reverse('error', args=[305]))

        # Normal population
        response = self.client.post(reverse('population'), {
            'manager_username': 'superuser', 'service_username': 'service'
        })
        self.assertEqual(response.status_code, 200)

        # Testing populated jobs
        self.assertEqual(len(Job.objects.filter(parent=None)), len(JOB_CLASSES))
        self.assertEqual(
            len(Job.objects.filter(~Q(parent=None))), len(os.listdir(os.path.join(BASE_DIR, 'jobs', 'presets')))
        )

        # Testing populated users
        self.assertEqual(len(Extended.objects.filter(user__username='superuser', role=USER_ROLES[2][0])), 1)
        self.assertEqual(len(Extended.objects.filter(user__username='service', role=USER_ROLES[4][0])), 1)

        # Testing populated unknown marks
        number_of_preset_marks = 0
        for comp_dir in os.listdir(os.path.join(BASE_DIR, 'marks', 'presets')):
            if os.path.isdir(os.path.join(BASE_DIR, 'marks', 'presets', comp_dir)):
                number_of_preset_marks += len(os.listdir(os.path.join(BASE_DIR, 'marks', 'presets', comp_dir)))
        self.assertEqual(len(MarkUnknown.objects.all()), number_of_preset_marks)
        self.assertEqual(len(Scheduler.objects.filter(type=SCHEDULER_TYPE[0][0])), 1)
        self.assertEqual(len(Scheduler.objects.filter(type=SCHEDULER_TYPE[1][0])), 1)

        safe_tags_presets = os.path.join(BASE_DIR, 'marks', 'tags_presets', 'safe.json')
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
                try:
                    tag = SafeTag.objects.get(tag=t['name'])
                except ObjectDoesNotExist:
                    self.fail('Preset safe tag "%s" was not created' % t['name'])
                if 'parent' in t and t['parent'] is not None:
                    self.assertEqual(tag.parent.tag, t['parent'])
                else:
                    self.assertEqual(tag.parent, None)
                self.assertEqual(tag.description, t.get('description', ''))

        unsafe_tags_presets = os.path.join(BASE_DIR, 'marks', 'tags_presets', 'unsafe.json')
        if os.path.isfile(unsafe_tags_presets):
            with open(unsafe_tags_presets, encoding='utf8') as fp:
                data = json.load(fp)
            if not isinstance(data, list):
                self.fail('Wrong preset safe tags format')
            for t in data:
                if not isinstance(t, dict):
                    self.fail('Wrong preset safe tags format')
                if 'name' not in t:
                    self.fail('Safe tag name is required')
                try:
                    tag = UnsafeTag.objects.get(tag=t['name'])
                except ObjectDoesNotExist:
                    self.fail('Preset unsafe tag "%s" was not created' % t['name'])
                if 'parent' in t and t['parent'] is not None:
                    self.assertEqual(tag.parent.tag, t['parent'])
                else:
                    self.assertEqual(tag.parent, None)
                self.assertEqual(tag.description, t.get('description', ''))

    def test_service_population(self):
        result = populate_users(
            admin={'username': 'superuser'},
            manager={'username': 'manager', 'password': '12345'},
            service={'username': 'service', 'password': 'service'}
        )
        self.assertIsNone(result)
        self.assertEqual(len(Extended.objects.filter(user__username='manager', role=USER_ROLES[2][0])), 1)
        self.assertEqual(len(Extended.objects.filter(user__username='service', role=USER_ROLES[4][0])), 1)

        self.client.post(reverse('users:login'), {'username': 'superuser', 'password': 'top_secret'})
        # Population after service and manager were created by function call
        response = self.client.post(reverse('population'))
        self.assertEqual(response.status_code, 200)
