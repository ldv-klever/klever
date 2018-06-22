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
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.urls import reverse

from bridge.vars import JOB_ROLES, JOB_STATUS
from bridge.utils import KleverTestCase
from bridge.populate import populate_users

from users.models import User, View, PreferableView
from jobs.models import Job, JobHistory, JobFile, FileSystem, RunHistory


class TestJobs(KleverTestCase):
    def setUp(self):
        super(TestJobs, self).setUp()
        User.objects.create_superuser('superuser', '', 'top_secret')
        populate_users(
            admin={'username': 'superuser'},
            manager={'username': 'manager', 'password': '12345'},
            service={'username': 'service', 'password': 'service'}
        )
        self.client.post(reverse('users:login'), {'username': 'superuser', 'password': 'top_secret'})
        self.client.post(reverse('population'))
        self.client.get(reverse('users:logout'))
        self.client.post(reverse('users:login'), {'username': 'manager', 'password': '12345'})
        self.test_filename = 'test_jobfile.txt'
        self.test_archive = 'test_jobarchive.zip'

    def test_tree_and_views(self):
        # Check jobs tree
        response = self.client.get(reverse('jobs:tree'))
        self.assertEqual(response.status_code, 200)

        # Creating view
        tree_view = {
            "columns": ['name', 'role', 'author', 'date', 'status', 'resource',
                        'unsafe:total', 'problem:total', 'safe:total'],
            "order": ["up", "date"],
            "filters": {
                "title": {"type": "istartswith", "value": "Testing"},
                "format": {"type": "is", "value": "1"}
            }
        }
        response = self.client.post('/users/ajax/save_view/', {
            'view': json.dumps(tree_view), 'view_type': '1', 'title': 'My view'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
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
        tree_view = {"columns": ["role", "author", "status", "problem", "safe"], "order": [], "filters": {}}
        response = self.client.post('/users/ajax/save_view/', {
            'view': json.dumps(tree_view), 'view_type': '1', 'view_id': view_id
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
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
        response = self.client.post('/users/ajax/preferable_view/', {'view_type': '1', 'view_id': view_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('message', res)
        self.assertEqual(len(PreferableView.objects.filter(user__username='manager', view_id=view_id)), 1)
        response = self.client.get(reverse('jobs:tree'))
        self.assertEqual(response.status_code, 200)

        # Share view
        self.assertFalse(view.shared)
        response = self.client.post('/users/ajax/share_view/', {'view_type': '1', 'view_id': view_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('message', res)
        view = View.objects.get(id=view_id)
        self.assertTrue(view.shared)

        # Testing view name check
        response = self.client.post('/users/ajax/check_view_name/', {'view_type': '1', 'view_title': 'Default'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('error', json.loads(str(response.content, encoding='utf8')))

        response = self.client.post('/users/ajax/check_view_name/', {'view_type': '1', 'view_title': ''})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('error', json.loads(str(response.content, encoding='utf8')))

        response = self.client.post('/users/ajax/check_view_name/', {'view_type': '1', 'view_title': 'My view'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('error', json.loads(str(response.content, encoding='utf8')))

        response = self.client.post('/users/ajax/check_view_name/', {'view_type': '1', 'view_title': 'New view'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Check view deletion
        response = self.client.post('/users/ajax/remove_view/', {'view_type': '1', 'view_id': view_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertIn('message', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(PreferableView.objects.filter(user__username='manager')), 0)
        self.assertEqual(len(View.objects.filter(author__username='manager')), 0)

    def test_create_edit_job(self):
        job_template = Job.objects.all().first()
        self.assertIsNotNone(job_template)

        # Requests for template job's page and data for autoupdate
        response = self.client.get(reverse('jobs:job', args=[job_template.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/jobs/ajax/get_job_data/', {'job_id': job_template.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Job template shouldn't have children now
        response = self.client.post('/jobs/ajax/do_job_has_children/', {'job_id': job_template.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(json.loads(str(response.content, encoding='utf8')), {})

        # Create job page
        response = self.client.post(reverse('jobs:create'), {'parent_id': job_template.pk})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.content) > 0)

        # Save new job
        file_data = []
        for f in job_template.versions.order_by('-version').first().filesystem_set.all().select_related('file'):
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
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        try:
            newjob_pk = int(res['job_id'])
        except ValueError or KeyError:
            self.fail('Integer job id is expected')

        # Job template should have children now
        response = self.client.post('/jobs/ajax/do_job_has_children/', {'job_id': job_template.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(json.loads(str(response.content, encoding='utf8')), {'children': True})

        # Job page
        response = self.client.get(reverse('jobs:job', args=[newjob_pk]))
        self.assertEqual(response.status_code, 200)

        # Job autoupdate data
        response = self.client.post('/jobs/ajax/get_job_data/', {'job_id': newjob_pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

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

        # Enable safe marks
        self.assertFalse(newjob.safe_marks)
        response = self.client.post('/jobs/ajax/enable_safe_marks/', {'job_id': newjob_pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        newjob = Job.objects.get(id=newjob_pk)
        self.assertTrue(newjob.safe_marks)

        # Edit job data
        response = self.client.post('/jobs/ajax/editjob/', {'job_id': newjob.pk, 'version': newjob.version})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.content) > 0)

        # Job versions data
        response = self.client.post('/jobs/ajax/getversions/', {'job_id': newjob.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')

        # Job data for viewing it
        response = self.client.post('/jobs/ajax/showjobdata/', {'job_id': newjob.pk})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.content) > 0)

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
            self.assertEqual(response['Content-Type'], 'application/json')
            self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
            self.assertIn('job_id', json.loads(str(response.content, encoding='utf8')))
            self.assertEqual(len(JobHistory.objects.filter(job=newjob)), 1 + i)

        # Job versions data again (after there are versions user can delete)
        response = self.client.post('/jobs/ajax/getversions/', {'job_id': newjob.pk})
        self.assertEqual(response.status_code, 200)

        # Removing versions
        response = self.client.post('/jobs/ajax/remove_versions/', {'job_id': newjob.pk, 'versions': '["2","3"]'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertIn('message', json.loads(str(response.content, encoding='utf8')))

        # Try to remove first version
        response = self.client.post('/jobs/ajax/remove_versions/', {'job_id': newjob.pk, 'versions': '["1"]'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('error', json.loads(str(response.content, encoding='utf8')))

        # Remove job
        response = self.client.post('/jobs/ajax/removejobs/', {'jobs': json.dumps([newjob.parent_id])})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(Job.objects.filter(id__in={newjob.id, newjob.parent_id}).count(), 0)

    def test_files(self):
        job_template = Job.objects.all().first()
        response = self.client.post('/jobs/ajax/savejob/', {
            'title': 'New job title',
            'description': 'Description of new job',
            'global_role': JOB_ROLES[0][0],
            'user_roles': '[]',
            'parent_identifier': job_template.identifier,
            'file_data': '[]'
        })
        newjob_pk = int(json.loads(str(response.content, encoding='utf8'))['job_id'])

        with open(os.path.join(settings.MEDIA_ROOT, self.test_filename), mode='wb') as fp:
            fp.write(b'My test text')
            fp.close()
        with open(os.path.join(settings.MEDIA_ROOT, self.test_filename), mode='rb') as fp:
            response = self.client.post('/jobs/ajax/upload_file/', {'file': fp})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('checksum', res)

        try:
            newfile = JobFile.objects.get(hash_sum=res['checksum'])
        except ObjectDoesNotExist:
            self.fail('The file was not uploaded')

        # Add new file to job and check result and DB changes
        response = self.client.post('/jobs/ajax/savejob/', {
            'title': 'New job title',
            'description': 'New description of new job',
            'global_role': JOB_ROLES[1][0],
            'user_roles': json.dumps([{'user': User.objects.get(username='superuser').pk, 'role': JOB_ROLES[2][0]}]),
            'job_id': newjob_pk,
            'file_data': json.dumps([{
                'id': newfile.pk, 'parent': None, 'hash_sum': newfile.hash_sum, 'title': 'filename.txt', 'type': '1'
            }]),
            'parent_identifier': job_template.identifier,
            'comment': 'Add file',
            'last_version': 1
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('job_id', res)
        self.assertEqual(len(JobHistory.objects.filter(job_id=newjob_pk)), 2)
        try:
            job_file = FileSystem.objects.get(job__job_id=newjob_pk, job__version=2)
        except ObjectDoesNotExist:
            self.fail('File was not saved')
        except MultipleObjectsReturned:
            self.fail('Too many files for new job (only 1 expected)')
        self.assertEqual(job_file.name, 'filename.txt')
        self.assertIsNone(job_file.parent)
        self.assertEqual(job_file.file_id, newfile.pk)

        # Try to download new file
        response = self.client.get(reverse('jobs:download_file', args=[job_file.pk]))
        self.assertEqual(response.status_code, 200)

        # Try to download new job and one of the defaults
        response = self.client.post('/jobs/ajax/downloadjobs/', {
            'job_ids': json.dumps([newjob_pk, Job.objects.filter(parent=None).first().pk])
        })
        self.assertEqual(response.status_code, 200)

        # Check access to download job
        response = self.client.post('/jobs/ajax/check_access/', {
            'jobs': json.dumps([newjob_pk, Job.objects.filter(parent=None).first().pk])
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Try to download new job
        response = self.client.get('/jobs/ajax/downloadjob/%s/' % newjob_pk)
        self.assertEqual(response.status_code, 200)
        with open(os.path.join(settings.MEDIA_ROOT, self.test_archive), mode='wb') as fp:
            for content in response.streaming_content:
                fp.write(content)

        # We have to remove job before uploading new one with the same identifier
        response = self.client.post('/jobs/ajax/removejobs/', {'jobs': json.dumps([newjob_pk])})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Upload downloaded job
        with open(os.path.join(settings.MEDIA_ROOT, self.test_archive), mode='rb') as fp:
            response = self.client.post('/jobs/ajax/upload_job/%s/' % job_template.identifier, {
                'file': fp
            })
            fp.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertJSONEqual(str(response.content, encoding='utf8'), '{}')
        try:
            uploaded_job = Job.objects.get(parent__identifier=job_template.identifier, name='New job title')
        except ObjectDoesNotExist:
            self.fail('The job was not found after upload')
        self.assertEqual(len(FileSystem.objects.filter(job__job=uploaded_job, job__version=2)), 1)
        self.assertEqual(len(FileSystem.objects.filter(job__job=uploaded_job, job__version=1)), 0)
        self.assertEqual(len(JobHistory.objects.filter(job=uploaded_job)), 2)

        # Check file content of uploaded job
        response = self.client.post('/jobs/ajax/getfilecontent/', {
            'file_id': FileSystem.objects.get(job__job=uploaded_job, job__version=2).pk
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
        self.assertEqual(response.content, b'My test text')

    def test_run_decision(self):
        job_template = Job.objects.all().first()
        response = self.client.post('/jobs/ajax/savejob/', {
            'title': 'New job title',
            'description': 'Description of new job',
            'global_role': JOB_ROLES[0][0],
            'user_roles': '[]',
            'parent_identifier': job_template.identifier,
            'file_data': '[]'
        })
        job_pk = int(json.loads(str(response.content, encoding='utf8'))['job_id'])

        # Fast run
        response = self.client.post('/jobs/ajax/fast_run_decision/', {'job_id': job_pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(Job.objects.filter(pk=job_pk, status=JOB_STATUS[1][0])), 1)
        self.assertEqual(len(RunHistory.objects.filter(
            job_id=job_pk, operator__username='manager', status=JOB_STATUS[1][0]
        )), 1)

        # Stop decision
        response = self.client.post('/jobs/ajax/stop_decision/', {'job_id': job_pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(Job.objects.get(pk=job_pk).status, JOB_STATUS[6][0])
        self.assertEqual(len(RunHistory.objects.filter(job_id=job_pk, operator__username='manager')), 1)

        # Start decision page
        # TODO: test run decision with config file and preset configurations
        response = self.client.get(reverse('jobs:prepare_run', args=[job_pk]))
        self.assertEqual(response.status_code, 200)

        # Get KLEVER_CORE_LOG_FORMATTERS value
        response = self.client.post('/jobs/ajax/get_def_start_job_val/', {'name': 'formatter', 'value': 'brief'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('value', res)

        # Start decision with settings
        run_conf = json.dumps([
            ["HIGH", "0", 100], ["1", "2.0", "1.0", "2"], [1, 1, 100, '', 15, None],
            [
                "INFO", "%(asctime)s (%(filename)s:%(lineno)03d) %(name)s %(levelname)5s> %(message)s",
                "NOTSET", "%(name)s %(levelname)5s> %(message)s"
            ],
            [False, True, True, False, True, False, True, True, '0']
        ])
        response = self.client.post('/jobs/ajax/run_decision/', {'job_id': job_pk, 'data': run_conf})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(Job.objects.get(pk=job_pk).status, JOB_STATUS[1][0])
        self.assertEqual(len(RunHistory.objects.filter(job_id=job_pk, operator__username='manager')), 2)

        self.client.post('/jobs/ajax/stop_decision/', {'job_id': job_pk})
        response = self.client.post('/jobs/ajax/lastconf_run_decision/', {'job_id': job_pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(Job.objects.get(pk=job_pk).status, JOB_STATUS[1][0])
        self.assertEqual(len(RunHistory.objects.filter(job_id=job_pk, operator__username='manager')), 3)

        response = self.client.get(
            '/jobs/download_configuration/%s/' % RunHistory.objects.filter(job_id=job_pk).order_by('-date').first().pk
        )
        self.assertEqual(response.status_code, 200)

    def tearDown(self):
        if os.path.exists(os.path.join(settings.MEDIA_ROOT, self.test_filename)):
            os.remove(os.path.join(settings.MEDIA_ROOT, self.test_filename))
        if os.path.exists(os.path.join(settings.MEDIA_ROOT, self.test_archive)):
            os.remove(os.path.join(settings.MEDIA_ROOT, self.test_archive))
        super(TestJobs, self).tearDown()
