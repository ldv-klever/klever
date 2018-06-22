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

import json

from django.urls import reverse

from bridge.utils import KleverTestCase
from bridge.vars import LANGUAGES, DATAFORMAT

from users.models import User, Extended, Notifications
from service.models import SchedulerUser


class TestLoginAndRegister(KleverTestCase):
    def test_admin(self):
        uname = 'user'

        response = self.client.get(reverse('users:login'))
        self.assertEqual(response.status_code, 200)

        User.objects.create_superuser(uname, '', 'top_secret')
        response = self.client.post(reverse('users:login'), {'username': uname, 'password': 'top_secret'})

        # Admin must be redirected to the population page
        self.assertRedirects(response, reverse('population'))

        # User without "Extended" object must be extended after signing in
        self.assertEqual(len(Extended.objects.filter(user__username=uname)), 1)

    def test_wrong_username(self):
        response = self.client.post(reverse('users:login'), {'username': 'unknown', 'password': 'unknown'})
        # If user was not redirected then OK
        self.assertEqual(response.status_code, 200)

    def test_signout(self):
        User.objects.create_user('user', '', 'password')
        self.client.post(reverse('users:login'), {'username': 'user', 'password': 'password'})
        response = self.client.get(reverse('users:logout'))
        self.assertRedirects(response, reverse('users:login'))

    def test_register(self):
        response = self.client.get(reverse('users:register'))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse('users:register'), {
            'username': 'user',
            'password': 'top_secret',
            'retype_password': 'top_secret',
            'email': '',
            'first_name': 'Firstname',
            'last_name': 'Lastname',
            'language': LANGUAGES[0][0],
            'data_format': DATAFORMAT[1][0],
            'accuracy': 2
        })
        # After successfull registration user must be redirected to login page
        self.assertRedirects(response, reverse('users:login'))
        # Check if new user exists in DB
        self.assertEqual(len(Extended.objects.filter(
            user__username='user', user__first_name='Firstname', user__last_name='Lastname',
            data_format=DATAFORMAT[1][0], accuracy=2, language=LANGUAGES[0][0]
        )), 1)

    def test_service(self):

        Extended.objects.create(user=User.objects.create_user(
            username='service', password='service', last_name='Lastname', first_name='Firstname'
        ))

        response = self.client.get('/users/service_signin/')
        self.assertEqual(response.status_code, 200)

        response = self.client.post('/users/service_signin/', {'username': 'service', 'password': 'service'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
        response = self.client.get('/users/service_signout/')
        self.assertEqual(response.status_code, 200)

        response = self.client.post('/users/service_signin/', {'username': 'service', 'password': 'incorrect'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertJSONEqual(
            str(response.content, encoding='utf8'), json.dumps({'error': 'Incorrect username or password'},
                                                               ensure_ascii=False, sort_keys=True, indent=4)
        )

        User.objects.create_user(username='service2', password='service2')
        response = self.client.post('/users/service_signin/', {'username': 'service2', 'password': 'service2'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertJSONEqual(
            str(response.content, encoding='utf8'), json.dumps({'error': 'User does not have extended data'},
                                                               ensure_ascii=False, sort_keys=True, indent=4)
        )


class TestLoggedInUser(KleverTestCase):
    def setUp(self):
        super(TestLoggedInUser, self).setUp()
        self.user = User.objects.create_user('user', password='top_secret')
        self.client.post(reverse('users:login'), {'username': 'user', 'password': 'top_secret'})

    def test_show_profile(self):
        response = self.client.get(reverse('users:show_profile', args=[self.user.pk]))
        self.assertEqual(response.status_code, 200)

    def test_save_notifications(self):
        save_ntf_url = '/users/ajax/save_notifications/'
        response = self.client.post(save_ntf_url, {'self_ntf': 'true', 'notifications': '["0_0","0_4"]'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('message', res)
        ntf = Notifications.objects.get(user=self.user)
        self.assertTrue(ntf.self_ntf)
        self.assertEqual(set(json.loads(ntf.settings)), {"0_0", "0_4"})

    def test_edit_profile(self):
        response = self.client.get(reverse('users:edit_profile'))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('users:edit_profile'), {
            'new_password': '', 'retype_password': '', 'email': '',
            'accuracy': 2, 'language': LANGUAGES[1][0], 'data_format': DATAFORMAT[0][0],
            'last_name': 'Newlastname', 'first_name': 'Newname'
        })
        self.user = User.objects.get(pk=self.user.pk)
        self.assertRedirects(response, reverse('users:edit_profile'))
        self.assertEqual(self.user.first_name, 'Newname')
        self.assertEqual(self.user.last_name, 'Newlastname')

        # Check that user can change password
        response = self.client.post(reverse('users:edit_profile'), {
            'new_password': 'top_secret2', 'retype_password': 'top_secret2', 'email': '',
            'accuracy': 2, 'language': LANGUAGES[1][0], 'data_format': DATAFORMAT[0][0],
            'last_name': 'Newlastname', 'first_name': 'Newname'
        })
        self.assertRedirects(response, reverse('users:login'))
        response = self.client.post(reverse('users:login'), {'username': 'user', 'password': 'top_secret2'})
        self.assertRedirects(response, reverse('jobs:tree'))

        response = self.client.post(reverse('users:edit_profile'), {
            'new_password': '', '': 'top_secret2', 'email': '',
            'accuracy': 2, 'language': LANGUAGES[1][0], 'data_format': DATAFORMAT[0][0],
            'last_name': 'Newlastname', 'first_name': 'Newname',
            'sch_login': 'Schlogin', 'sch_password': 'top_secret3'
        })
        self.assertRedirects(response, reverse('users:edit_profile'))
        # Check that scheduler user was created
        self.assertEqual(len(SchedulerUser.objects.filter(user=self.user, login='Schlogin', password='top_secret3')), 1)

        # Check that user can't change password if he didn't retyped it
        response = self.client.post(reverse('users:edit_profile'), {
            'new_password': 'single', 'retype_password': '', 'email': '',
            'accuracy': 3, 'language': LANGUAGES[1][0], 'data_format': DATAFORMAT[0][0],
            'last_name': 'Newlastname', 'first_name': 'Newname'
        })
        self.assertEqual(response.status_code, 200)
        # Check that other data didn't changed
        self.assertEqual(len(Extended.objects.filter(user=self.user, accuracy=2)), 1)
