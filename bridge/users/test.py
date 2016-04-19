from django.core.urlresolvers import reverse
from django.test import Client, TestCase
from users.models import User, Extended, Notifications
from service.models import SchedulerUser


class TestLoginAndRegister(TestCase):
    def setUp(self):
        self.client = Client()

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
        from bridge.vars import LANGUAGES, DATAFORMAT
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
            user__username='user',
            first_name='Firstname',
            last_name='Lastname',
            data_format=DATAFORMAT[1][0],
            accuracy=2,
            language=LANGUAGES[0][0]
        )), 1)

    def test_service(self):
        import json

        Extended.objects.create(
            user=User.objects.create_user(username='service', password='service'),
            last_name='Lastname', first_name='Firstname'
        )

        response = self.client.get('/users/service_signin/')
        self.assertEqual(response.status_code, 200)

        response = self.client.post('/users/service_signin/', {'username': 'service', 'password': 'service'})
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
            if 'error' not in res:
                self.fail('Json response must contain error message')
            self.fail('Json response returns error message for good values')
        except ValueError:
            # This means HttpResponse() - it's OK
            pass
        response = self.client.get('/users/service_signout/')
        self.assertEqual(response.status_code, 200)

        response = self.client.post('/users/service_signin/', {'username': 'service', 'password': 'incorrect'})
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
            if 'error' not in res:
                self.fail('Json response must contain error message')
            self.assertEqual(res['error'], 'Incorrect username or password')
        except ValueError:
            self.fail('Response is Http for bad password')

        User.objects.create_user(username='service2', password='service2')
        response = self.client.post('/users/service_signin/', {'username': 'service2', 'password': 'service2'})
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
            if 'error' not in res:
                self.fail('Json response must contain error message')
            self.assertEqual(res['error'], 'User does not have extended data')
        except ValueError:
            self.fail('Response is Http for service without extended')

        # TODO: check cookies: job identifier and scheduler (population must be done first)


class TestLoggedInUser(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('user', password='top_secret')
        self.client.post(reverse('users:login'), {'username': 'user', 'password': 'top_secret'})

    def test_show_profile(self):
        response = self.client.get(reverse('users:show_profile', args=[self.user.pk]))
        self.assertEqual(response.status_code, 200)
        # Check that page with unexisted user profile does not exist
        response = self.client.get(reverse('users:show_profile', args=[self.user.pk + 1]))
        self.assertEqual(response.status_code, 404)

    def test_save_notifications(self):
        import json

        def get_json_val(param):
            try:
                res = json.loads(str(response.content, encoding='utf8'))
                return res[param]
            except Exception as e:
                self.fail('Wrong json response: %s' % e)

        save_ntf_url = '/users/ajax/save_notifications/'
        response = self.client.post(save_ntf_url, {'self_ntf': 'true', 'notifications': '["0_0","0_4"]'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_json_val('status'), 0)
        ntf = Notifications.objects.get(user=self.user)
        self.assertEqual(ntf.self_ntf, True)
        self.assertEqual(ntf.settings, '["0_0","0_4"]')

    def test_edit_profile(self):
        from bridge.vars import LANGUAGES, DATAFORMAT
        response = self.client.get(reverse('users:edit_profile'))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('users:edit_profile'), {
            'new_password': '', 'retype_password': '', 'email': '',
            'accuracy': 2, 'language': LANGUAGES[1][0], 'data_format': DATAFORMAT[0][0],
            'last_name': 'Newlastname', 'first_name': 'Newname'
        })
        self.assertRedirects(response, reverse('users:edit_profile'))
        self.assertEqual(Extended.objects.get(user=self.user).first_name, 'Newname')
        self.assertEqual(Extended.objects.get(user=self.user).last_name, 'Newlastname')

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
