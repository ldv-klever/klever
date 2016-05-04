import os
import json
import tempfile
from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db.models import Q
from django.test import Client, TestCase
from bridge.populate import populate_users
from bridge.settings import MEDIA_ROOT
from users.models import View, PreferableView
from jobs.models import *


class TestJobs(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_superuser('superuser', '', 'top_secret')
        populate_users(
            admin={'username': 'superuser'},
            manager={'username': 'manager', 'password': '12345'},
            service={'username': 'service', 'password': 'service'}
        )
        self.client.post(reverse('users:login'), {'username': 'superuser', 'password': 'top_secret'})

    def test_tree_and_views(self):

        # Check jobs tree before and after population
        response = self.client.get(reverse('jobs:tree'))
        self.assertEqual(response.status_code, 200)
        self.client.post(reverse('population'))
        self.client.get(reverse('users:logout'))
        self.client.post(reverse('users:login'), {'username': 'manager', 'password': '12345'})
        response = self.client.get(reverse('jobs:tree'))
        self.assertEqual(response.status_code, 200)

        # Creating view
        tree_view = {
            "columns": ["role", "author", "status", "problem", "safe", "resource"],
            "orders": ["-date", "status", "-finish_date"],
            "filters": {
                "name": {"type": "istartswith", "value": "Validation"},
                "format": {"type": "is", "value": "1"}
            }
        }
        response = self.client.post('/jobs/ajax/save_view/', {
            'view': json.dumps(tree_view), 'view_type': '1', 'title': 'My view'
        })
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
            if 'error' in res:
                self.fail('Error message was returned')
        except ValueError:
            self.fail('Response must be in JSON format')
        try:
            view_id = int(res['view_id'])
        except KeyError or ValueError:
            self.fail('Response must contain integer "view_id"')
        response = self.client.get(reverse('jobs:tree'))
        self.assertEqual(response.status_code, 200)
        try:
            view = View.objects.get(author__username='manager', type='1', name='My view', pk=view_id)
        except ObjectDoesNotExist:
            self.fail('The view was not saved')
        self.assertEqual(tree_view, json.loads(view.view))

        # Changing view
        tree_view = {
            "columns": ["role", "author", "status", "problem", "safe"],
            "orders": [], "filters": {}
        }
        response = self.client.post('/jobs/ajax/save_view/', {
            'view': json.dumps(tree_view), 'view_type': '1', 'view_id': view_id
        })
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
            if 'error' in res:
                self.fail('Error message was returned')
        except ValueError:
            self.fail('Response must be in JSON format')
        try:
            view_id = int(res['view_id'])
        except KeyError or ValueError:
            self.fail('Response must contain integer "view_id"')
        response = self.client.get(reverse('jobs:tree'))
        self.assertEqual(response.status_code, 200)
        try:
            view = View.objects.get(author__username='manager', type='1', name='My view', pk=view_id)
        except ObjectDoesNotExist:
            self.fail('The view was not saved')
        self.assertEqual(tree_view, json.loads(view.view))

        # Making view preffered
        response = self.client.post('/jobs/ajax/preferable_view/', {
            'view_type': '1', 'view_id': view_id
        })
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
            if 'error' in res:
                self.fail('Error message is not expected')
            if 'message' not in res:
                self.fail('Success message is expected')
        except ValueError:
            self.fail('Response must be in JSON format')
        self.assertEqual(len(PreferableView.objects.filter(user__username='manager', view_id=view_id)), 1)
        response = self.client.get(reverse('jobs:tree'))
        self.assertEqual(response.status_code, 200)

        # Testing view name check
        response = self.client.post('/jobs/ajax/check_view_name/', {'view_type': '1', 'view_title': 'Default'})
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
            if 'error' not in res:
                self.fail('Error message is expected')
        except ValueError:
            self.fail('Response must be in JSON format')

        response = self.client.post('/jobs/ajax/check_view_name/', {'view_type': '1', 'view_title': ''})
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
            if 'error' not in res:
                self.fail('Error message is expected')
        except ValueError:
            self.fail('Response must be in JSON format')

        response = self.client.post('/jobs/ajax/check_view_name/', {'view_type': '1', 'view_title': 'My view'})
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
            if 'error' not in res:
                self.fail('Error message is expected')
        except ValueError:
            self.fail('Response must be in JSON format')

        response = self.client.post('/jobs/ajax/check_view_name/', {'view_type': '1', 'view_title': 'New view'})
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
            if 'error' in res:
                self.fail('Error message is not expected')
        except ValueError:
            self.fail('Response must be in JSON format')

        # Check view deletion
        response = self.client.post('/jobs/ajax/remove_view/', {'view_type': '1', 'view_id': view_id})
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
            if 'error' in res:
                self.fail('Error message is not expected')
            if 'message' not in res:
                self.fail('Success message is expected')
        except ValueError:
            self.fail('Response must be in JSON format')
        self.assertEqual(len(PreferableView.objects.filter(user__username='manager')), 0)
        self.assertEqual(len(View.objects.filter(author__username='manager')), 0)

    def test_create_edit_job(self):
        self.client.post(reverse('population'))
        self.client.get(reverse('users:logout'))
        self.client.post(reverse('users:login'), {'username': 'manager', 'password': '12345'})

        try:
            job_template = Job.objects.filter(~Q(parent=None))[0]
        except IndexError:
            try:
                job_template = Job.objects.get(type=JOB_CLASSES[0][0], parent=None)
            except ObjectDoesNotExist:
                self.fail('Job template was not populated')

        # Requests for template job's page and data for autoupdate
        response = self.client.get(reverse('jobs:job', args=[job_template.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/jobs/ajax/get_job_data/', {'job_id': job_template.pk})
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
        except ValueError:
            self.fail('Response must be in JSON format')
        if 'error' in res:
            self.fail('Error message is not expected')

        # Create job page
        response = self.client.post(reverse('jobs:create'), {'parent_id': job_template.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((len(response.content) > 0), True)

        # Save new job
        file_data = []
        for f in job_template.versions.order_by('-version').first().filesystem_set.all():
            file_data.append({
                'id': f.pk,
                'parent': f.parent_id,
                'hash_sum': f.file.hash_sum if f.file is not None else None,
                'title': f.name,
                'type': '1' if f.file is not None else '0'
            })
        response = self.client.post('/jobs/ajax/savejob/', {
            'title': 'New job title',
            'description': 'Description of new job',
            'global_role': JOB_ROLES[0][0],
            'user_roles': json.dumps([{'user': User.objects.get(username='superuser').pk, 'role': JOB_ROLES[2][0]}]),
            'parent_identifier': job_template.identifier,
            'file_data': json.dumps(file_data)
        })
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
        except ValueError:
            self.fail('Response must be in JSON format')
        if 'error' in res:
            self.fail('Error message is not expected')
        if 'job_id' not in res:
            self.fail('Job id is expected')
        try:
            newjob_pk = int(res['job_id'])
        except ValueError:
            self.fail('Integer job id is expected')

        # Job page
        response = self.client.get(reverse('jobs:job', args=[newjob_pk]))
        self.assertEqual(response.status_code, 200)

        # Job autoupdate data
        response = self.client.post('/jobs/ajax/get_job_data/', {'job_id': newjob_pk})
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
        except ValueError:
            self.fail('Response must be in JSON format')
        if 'error' in res:
            self.fail('Error message is not expected')

        # Check if job and its versions exist
        try:
            newjob = Job.objects.get(pk=newjob_pk)
        except ObjectDoesNotExist:
            self.fail('New job was not created')
        try:
            JobHistory.objects.get(job=newjob)
        except ObjectDoesNotExist:
            self.fail('New job was created without version')
        except MultipleObjectsReturned:
            self.fail('New job has too many versions')

        # Edit job data
        response = self.client.post('/jobs/ajax/editjob/', {'job_id': newjob.pk, 'version': newjob.version})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((len(response.content) > 0), True)

        # Job versions data
        response = self.client.post('/jobs/ajax/getversions/', {'job_id': newjob.pk})
        self.assertEqual(response.status_code, 200)
        try:
            json.loads(str(response.content, encoding='utf8'))
            self.fail('Error message is not expected')
        except ValueError:
            # If response is HTML then OK
            pass

        # Job data for viewing it
        response = self.client.post('/jobs/ajax/showjobdata/', {'job_id': newjob.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((len(response.content) > 0), True)

        for i in range(1, 5):
            response = self.client.post('/jobs/ajax/savejob/', {
                'title': 'New job title',
                'description': 'New description of new job',
                'global_role': JOB_ROLES[1][0],
                'user_roles': '[]',
                'job_id': newjob.pk,
                'file_data': json.dumps(file_data),
                'parent_identifier': job_template.identifier,
                'comment': 'Comment %s' % i,
                'last_version': Job.objects.get(pk=newjob.pk).version
            })
            self.assertEqual(response.status_code, 200)
            try:
                res = json.loads(str(response.content, encoding='utf8'))
            except ValueError:
                self.fail('Response must be in JSON format')
            if 'error' in res:
                print(res['error'])
                self.fail('Error message is not expected')
            if 'job_id' not in res:
                self.fail('Job id is expected')
            self.assertEqual(len(JobHistory.objects.filter(job=newjob)), 1 + i)

        # Job versions data again (after there are versions user can delete)
        response = self.client.post('/jobs/ajax/getversions/', {'job_id': newjob.pk})
        self.assertEqual(response.status_code, 200)

        # Removing versions
        response = self.client.post('/jobs/ajax/remove_versions/', {'job_id': newjob.pk, 'versions': '["2","3"]'})
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
            if 'error' in res:
                self.fail('Error message is not expected')
            elif 'message' not in res:
                self.fail('Success message is expected')
        except ValueError:
            self.fail('Response must be in JSON format')

        # Try to remove first version
        response = self.client.post('/jobs/ajax/remove_versions/', {'job_id': newjob.pk, 'versions': '["1"]'})
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
            if 'error' not in res:
                self.fail('Error message is expected')
        except ValueError:
            self.fail('Response must be in JSON format')

        # Remove job
        response = self.client.post('/jobs/ajax/removejobs/', {'jobs': json.dumps([newjob.pk])})
        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
            if 'error' in res:
                self.fail('Error message is not expected')
        except ValueError:
            self.fail('Response must be in JSON format')

    def test_files(self):
        self.client.post(reverse('population'))
        self.client.get(reverse('users:logout'))
        self.client.post(reverse('users:login'), {'username': 'manager', 'password': '12345'})
        job_template = Job.objects.get(type=JOB_CLASSES[0][0], parent=None)
        response = self.client.post('/jobs/ajax/savejob/', {
            'title': 'New job title',
            'description': 'Description of new job',
            'global_role': JOB_ROLES[0][0],
            'user_roles': json.dumps([{'user': User.objects.get(username='superuser').pk, 'role': JOB_ROLES[2][0]}]),
            'parent_identifier': job_template.identifier,
            'file_data': '[]'
        })
        newjob_pk = int(json.loads(str(response.content, encoding='utf8'))['job_id'])
        test_filename = 'test_jobfile.txt'
        with open(os.path.join(MEDIA_ROOT, test_filename), mode='wb') as fp:
            fp.write(b'My test text')
            fp.close()
        with open(os.path.join(MEDIA_ROOT, test_filename), mode='rb') as fp:
            response = self.client.post('/jobs/ajax/upload_file/', {'file': fp})
        os.remove(os.path.join(MEDIA_ROOT, test_filename))

        self.assertEqual(response.status_code, 200)
        try:
            res = json.loads(str(response.content, encoding='utf8'))
            if 'error' in res:
                self.fail('Error message is not expected')
            elif 'checksum' not in res:
                self.fail('File check sum is expected')
        except ValueError:
            self.fail('Response must be in JSON format')
        try:
            newfile = File.objects.get(hash_sum=res['checksum'])
        except ObjectDoesNotExist:
            self.fail('The file was not uploaded')


