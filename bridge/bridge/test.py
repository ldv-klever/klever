import os
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.test import Client, TestCase
from bridge.settings import BASE_DIR
from bridge.vars import JOB_CLASSES, USER_ROLES
from users.models import User, Extended
from jobs.models import Job
from marks.models import MarkUnknown


class TestPopulation(TestCase):
    def setUp(self):
        self.client = Client()
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
            len(Job.objects.filter(~Q(parent=None))),
            len(os.listdir(os.path.join(BASE_DIR, 'jobs', 'presets')))
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
