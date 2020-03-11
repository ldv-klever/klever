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

import os
import json

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.urls import reverse

from bridge.vars import JOB_ROLES
from bridge.utils import KleverTestCase

from users.models import User, PreferableView
from jobs.models import Job, JobFile, FileSystem


class TestJobs(KleverTestCase):
    def setUp(self):
        super(TestJobs, self).setUp()
        User.objects.create_superuser('superuser', '', 'top_secret')
        populate_users(
            admin={'username': 'admin', 'password': 'admin'},
            manager={'username': 'manager', 'password': 'manager'},
            service={'username': 'service', 'password': 'service'}
        )
        self.client.post(reverse('users:login'), {'username': 'manager', 'password': 'manager'})
        self.client.post(reverse('population'))
        self.test_filename = 'test_jobfile.txt'
        self.test_archive = 'test_jobarchive.zip'
        self.test_conf = 'test.conf'

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
        job_template = Job.objects.order_by('name').first()
        self.assertIsNotNone(job_template)

        # Requests for template job's page and data for autoupdate
        response = self.client.get(reverse('jobs:job', args=[job_template.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/jobs/decision_results/%s/' % job_template.pk)
        self.assertEqual(response.status_code, 200)
        response = self.client.get('/jobs/progress/%s/' % job_template.pk)
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/jobs/status/%s/' % job_template.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Job template shouldn't have children now
        response = self.client.get('/jobs/do_job_has_children/%s/' % job_template.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertIn('children', res)
        self.assertFalse(res['children'])

        # Create job page
        response = self.client.get(reverse('jobs:form', args=[job_template.pk, 'copy']))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.content) > 0)

        tmpl_filedata = json.dumps(LoadFilesTree(job_template.id, job_template.version).as_json()['children'])

        # Save new job
        response = self.client.post(reverse('jobs:form', args=[job_template.pk, 'copy']), {
            'name': 'New job title',
            'description': 'Description of new job',
            'global_role': JOB_ROLES[0][0],
            'user_roles': json.dumps([{'user': User.objects.get(username='superuser').pk, 'role': JOB_ROLES[2][0]}]),
            'parent': job_template.identifier,
            'file_data': tmpl_filedata
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        try:
            newjob_pk = int(res['job_id'])
        except ValueError or KeyError:
            self.fail('Integer job id is expected')

        # Job page
        response = self.client.get(reverse('jobs:job', args=[newjob_pk]))
        self.assertEqual(response.status_code, 200)

        # Job autoupdate data
        response = self.client.post('/jobs/decision_results/%s/' % newjob_pk)
        self.assertEqual(response.status_code, 200)
        response = self.client.get('/jobs/progress/%s/' % newjob_pk)
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/jobs/status/%s/' % newjob_pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        resp = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', resp)
        self.assertIn('status', resp)

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

        # Edit job page
        response = self.client.get(reverse('jobs:form', args=[newjob.pk, 'edit']))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.content) > 0)

        # Version data (description) for edit job page
        response = self.client.get('/jobs/get_version_data/%s/%s/' % (newjob.pk, newjob.version))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        resp = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', resp)
        self.assertIn('description', resp)

        # Version roles for edit job page
        response = self.client.get('/jobs/get_version_roles/%s/%s/' % (newjob.pk, newjob.version))
        self.assertEqual(response.status_code, 200)

        # Version files for edit job page
        response = self.client.post('/jobs/get_version_files/%s/%s/' % (newjob.pk, newjob.version))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        resp = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', resp)

        for i in range(1, 5):
            response = self.client.post(reverse('jobs:form', args=[newjob.pk, 'edit']), {
                'name': 'New job title',
                'description': 'New description of new job',
                'global_role': JOB_ROLES[1][0],
                'user_roles': '[]',
                'job_id': newjob.pk,
                'file_data': tmpl_filedata,
                'parent': job_template.identifier,
                'comment': 'Comment %s' % i,
                'last_version': Job.objects.get(pk=newjob.pk).version
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/json')
            self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
            self.assertIn('job_id', json.loads(str(response.content, encoding='utf8')))
            self.assertEqual(len(JobHistory.objects.filter(job=newjob)), 1 + i)

        response = self.client.get(reverse('jobs:job', args=[newjob_pk]))
        self.assertEqual(response.status_code, 200)

        # Removing versions
        response = self.client.post('/jobs/remove_versions/%s/' % newjob.pk, {'versions': '["2","3"]'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertIn('message', json.loads(str(response.content, encoding='utf8')))

        # Try to remove first version
        response = self.client.post('/jobs/remove_versions/%s/' % newjob.pk, {'versions': '["1"]'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('error', json.loads(str(response.content, encoding='utf8')))

        # Remove job
        response = self.client.post('/jobs/api/%s/remove/' % newjob.parent_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(Job.objects.filter(id__in={newjob.id, newjob.parent_id}).count(), 0)

    def test_files(self):
        job_template = Job.objects.all().first()
        file_data = [{"type": "root", "text": "Files", "children": []}]

        response = self.client.post(reverse('jobs:form', args=[job_template.pk, 'copy']), {
            'name': 'New job title', 'description': 'Description of new job', 'parent': job_template.identifier,
            'global_role': JOB_ROLES[0][0], 'user_roles': '[]',
            'file_data': json.dumps(file_data)
        })
        newjob_pk = int(json.loads(str(response.content, encoding='utf8'))['job_id'])
        self.assertEqual(Job.objects.filter(id=newjob_pk).count(), 1)

        with open(os.path.join(settings.MEDIA_ROOT, self.test_filename), mode='wb') as fp:
            fp.write(b'My test text')
            fp.close()
        with open(os.path.join(settings.MEDIA_ROOT, self.test_filename), mode='rb') as fp:
            response = self.client.post('/jobs/upload_file/', {'file': fp})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('hashsum', res)

        try:
            newfile = JobFile.objects.get(hash_sum=res['hashsum'])
        except ObjectDoesNotExist:
            self.fail('The file was not uploaded')

        file_data[0]['children'].append({
            "data": {"hashsum": newfile.hash_sum}, 'text': 'filename.txt', 'type': 'file'
        })
        # Add new file to job and check result and DB changes
        response = self.client.post(reverse('jobs:form', args=[newjob_pk, 'edit']), {
            'name': 'New job title', 'description': 'New description of new job',
            'parent': job_template.identifier, 'global_role': JOB_ROLES[1][0],
            'user_roles': json.dumps([{'user': User.objects.get(username='superuser').pk, 'role': JOB_ROLES[2][0]}]),
            'file_data': json.dumps(file_data),
            'comment': 'Add file', 'last_version': 1
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
        self.assertEqual(job_file.file_id, newfile.id)

        # Try to download new file
        response = self.client.get(reverse('jobs:download_file', args=[newfile.hash_sum]))
        self.assertEqual(response.status_code, 200)

        # Try to download new job and one of the defaults
        response = self.client.post('/jobs/downloadjobs/', {
            'job_ids': json.dumps([newjob_pk, Job.objects.filter(parent=None).first().pk])
        })
        self.assertEqual(response.status_code, 200)

        # Check access to download job
        response = self.client.post('/jobs/check_download_access/', {
            'jobs': json.dumps([newjob_pk, Job.objects.filter(parent=None).first().pk])
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Try to download new job
        response = self.client.get('/jobs/downloadjob/%s/' % newjob_pk)
        self.assertEqual(response.status_code, 200)
        with open(os.path.join(settings.MEDIA_ROOT, self.test_archive), mode='wb') as fp:
            for content in response.streaming_content:
                fp.write(content)

        # We have to remove job before uploading new one with the same identifier
        response = self.client.post('/jobs/api/%s/remove/' % newjob_pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Upload downloaded job
        with open(os.path.join(settings.MEDIA_ROOT, self.test_archive), mode='rb') as fp:
            response = self.client.post('/jobs/upload_jobs/%s/' % job_template.identifier, {'file': fp})
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
        response = self.client.get('/jobs/api/file/{0}/'.format(
            FileSystem.objects.get(job__job=uploaded_job, job__version=2).file.hash_sum
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('content', res)
        self.assertEqual(res['content'], 'My test text')

    def test_run_decision(self):
        file_data = [{"type": "root", "text": "Files", "children": []}]
        job_template = Job.objects.all().first()
        response = self.client.post(reverse('jobs:form', args=[job_template.id, 'copy']), {
            'name': 'New job title', 'description': 'Description of new job',
            'global_role': JOB_ROLES[0][0], 'user_roles': '[]',
            'parent': job_template.identifier, 'file_data': json.dumps(file_data)
        })
        job_pk = int(json.loads(str(response.content, encoding='utf8'))['job_id'])

        # Fast run
        response = self.client.post('/jobs/run_decision/%s/' % job_pk, {'mode': 'fast'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(Job.objects.filter(pk=job_pk, status=JOB_STATUS[1][0])), 1)
        self.assertEqual(len(RunHistory.objects.filter(
            job_id=job_pk, operator__username='manager', status=JOB_STATUS[1][0]
        )), 1)

        # Get progress (console request)
        response = self.client.get('/jobs/get_job_progress_json/%s/' % job_pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('data', res)

        # Stop decision
        response = self.client.post('/jobs/stop_decision/%s/' % job_pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(Job.objects.get(pk=job_pk).status, JOB_STATUS[6][0])
        self.assertEqual(len(RunHistory.objects.filter(job_id=job_pk, operator__username='manager')), 1)
        Job.objects.filter(status=JOB_STATUS[6][0]).update(status=JOB_STATUS[7][0])

        # Start decision page
        response = self.client.get(reverse('jobs:prepare_run', args=[job_pk]))
        self.assertEqual(response.status_code, 200)

        # Get KLEVER_CORE_LOG_FORMATTERS value
        response = self.client.post('/jobs/get_def_start_job_val/', {'name': 'console_log_formatter', 'value': 'brief'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('console_log_formatter', res)

        # Start decision with settings
        run_conf = json.dumps([
            ["HIGH", "0", 100, '1'], ["1", "1.0", "2"], [1, 1, 100, ''],
            [
                "INFO", "%(asctime)s (%(filename)s:%(lineno)03d) %(name)s %(levelname)5s> %(message)s",
                "NOTSET", "%(name)s %(levelname)5s> %(message)s"
            ],
            [False, True, True, True, False, True]
        ])
        response = self.client.post('/jobs/run_decision/%s/' % job_pk, {'mode': 'data', 'data': run_conf})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(Job.objects.get(pk=job_pk).status, JOB_STATUS[1][0])
        self.assertEqual(len(RunHistory.objects.filter(job_id=job_pk, operator__username='manager')), 2)

        self.client.post('/jobs/stop_decision/%s/' % job_pk)
        Job.objects.filter(status=JOB_STATUS[6][0]).update(status=JOB_STATUS[7][0])

        response = self.client.post('/jobs/run_decision/%s/' % job_pk, {'mode': 'lastconf'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(Job.objects.get(pk=job_pk).status, JOB_STATUS[1][0])
        self.assertEqual(len(RunHistory.objects.filter(job_id=job_pk, operator__username='manager')), 3)

        self.client.post('/jobs/stop_decision/%s/' % job_pk)
        Job.objects.filter(status=JOB_STATUS[6][0]).update(status=JOB_STATUS[7][0])

        response = self.client.get(
            '/jobs/download_configuration/%s/' % RunHistory.objects.filter(job_id=job_pk).order_by('-date').first().pk
        )
        self.assertEqual(response.status_code, 200)

        with open(os.path.join(settings.MEDIA_ROOT, self.test_conf), mode='wb') as fp:
            for content in response.streaming_content:
                fp.write(content)
        with open(os.path.join(settings.MEDIA_ROOT, self.test_conf), mode='rb') as fp:
            response = self.client.post('/jobs/run_decision/%s/' % job_pk, {'mode': 'file_conf', 'file_conf': fp})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(Job.objects.get(pk=job_pk).status, JOB_STATUS[1][0])

    def test_console_requests(self):
        job_template = Job.objects.all().first()
        if not job_template:
            return

        # Copy the job with autofilled name
        response = self.client.post('/jobs/api/duplicate-job/', data={'parent': job_template.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('id', res)
        self.assertIn('identifier', res)
        job_pk = res['id']
        job_identifer = res['identifier']
        try:
            job = Job.objects.get(id=job_pk)
        except ObjectDoesNotExist:
            self.fail("The job wasn't copied")

        # Copy job version
        response = self.client.patch('/jobs/api/duplicate/{}/'.format(job_pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Get job fields: status (by id)
        response = self.client.post('/jobs/get_job_field/', {'job': job_identifer, 'field': 'status'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertIn('status', res)
        self.assertEqual(res['status'], JOB_STATUS[0][0])

        # Get job fields: identifier (by name)
        response = self.client.post('/jobs/get_job_field/', {'job': job.name, 'field': 'identifier'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertIn('identifier', res)
        self.assertEqual(res['identifier'], job_identifer)

    def test_comparison_and_trees(self):
        jobs = Job.objects.all()
        job1 = jobs.first()
        if not job1:
            return

        file_data = [{"type": "root", "text": "Files"}]

        # Add file for the first job (job1)
        with open(os.path.join(settings.MEDIA_ROOT, self.test_filename), mode='wb') as fp:
            fp.write(b'My test text 1')
            fp.close()
        with open(os.path.join(settings.MEDIA_ROOT, self.test_filename), mode='rb') as fp:
            response = self.client.post('/jobs/upload_file/', {'file': fp})
        f1_hashsum = json.loads(str(response.content, encoding='utf8'))['hashsum']
        file_data[0]['children'] = [{"data": {"hashsum": f1_hashsum}, 'text': 'filename.txt', 'type': 'file'}]
        self.client.post(reverse('jobs:form', args=[job1.id, 'edit']), {
            'name': job1.name, 'description': job1.versions.get(version=job1.version).description,
            'global_role': JOB_ROLES[0][0], 'user_roles': '[]',
            'parent': job1.parent.identifier if job1.parent else '', 'file_data': json.dumps(file_data),
            'comment': 'Replace all files with one', 'last_version': job1.version
        })

        # Save job copy and copy new version
        response = self.client.post('/jobs/api/duplicate-job/', data={'parent': job1.pk})
        job2 = Job.objects.get(id=json.loads(str(response.content, encoding='utf8'))['id'])
        self.client.patch('/jobs/api/duplicate/{}/'.format(job2.id))
        self.assertEqual(JobHistory.objects.filter(job=job2).count(), 2)

        # Replace file for job2
        with open(os.path.join(settings.MEDIA_ROOT, self.test_filename), mode='wb') as fp:
            fp.write(b'My test text 2')
            fp.close()
        with open(os.path.join(settings.MEDIA_ROOT, self.test_filename), mode='rb') as fp:
            response = self.client.post('/jobs/replace_job_file/%s/' % job2.id, {'name': 'filename.txt', 'file': fp})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        try:
            fs = FileSystem.objects.select_related('file').get(job__job=job2, name='filename.txt', job__version=2)
        except ObjectDoesNotExist:
            self.fail('Job2 file was not copied with version copy')
        f2_hashsum = fs.file.hash_sum

        # Compare versions of job2
        response = self.client.post('/jobs/compare_versions/%s/' % job2.id, {'v1': 1, 'v2': 2})
        self.assertEqual(response.status_code, 200)

        # Check compare access
        response = self.client.post('/jobs/check_compare_access/', {'job1': job1.id, 'job2': job2.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Compare jobs' files
        response = self.client.get(reverse('jobs:comparison', args=[job1.id, job2.id]))
        self.assertEqual(response.status_code, 200)

        # get files difference
        response = self.client.post('/jobs/get_files_diff/%s/%s/' % (f1_hashsum, f2_hashsum))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('content', res)

        # Download tree (should dowload at least job1 and job2)
        response = self.client.post('/jobs/downloadtrees/', {'job_ids': json.dumps([job1.id])})
        self.assertEqual(response.status_code, 200)
        with open(os.path.join(settings.MEDIA_ROOT, self.test_archive), mode='wb') as fp:
            for content in response.streaming_content:
                fp.write(content)

        # Remove jobs are currently downloaded
        self.client.post('/jobs/api/%s/remove/' % job1.id)

        # Upload tree
        with open(os.path.join(settings.MEDIA_ROOT, self.test_archive), mode='rb') as fp:
            response = self.client.post('/jobs/upload_jobs_tree/', {'parent_id': 'null', 'file': fp})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        self.assertEqual(Job.objects.filter(identifier=job1.identifier).count(), 1)
        self.assertEqual(Job.objects.filter(identifier=job2.identifier).count(), 1)

    def tearDown(self):
        if os.path.exists(os.path.join(settings.MEDIA_ROOT, self.test_filename)):
            os.remove(os.path.join(settings.MEDIA_ROOT, self.test_filename))
        if os.path.exists(os.path.join(settings.MEDIA_ROOT, self.test_archive)):
            os.remove(os.path.join(settings.MEDIA_ROOT, self.test_archive))
        if os.path.exists(os.path.join(settings.MEDIA_ROOT, self.test_conf)):
            os.remove(os.path.join(settings.MEDIA_ROOT, self.test_conf))
        super().tearDown()
