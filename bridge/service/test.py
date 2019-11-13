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
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.test import Client
from django.urls import reverse

from bridge.vars import JOB_STATUS, SCHEDULER_TYPE, SCHEDULER_STATUS, PRIORITY, NODE_STATUS
from bridge.utils import KleverTestCase
# from bridge.populate import populate_users

from users.models import User, SchedulerUser
from jobs.models import Job
from service.models import Scheduler, Decision, Task, Solution, VerificationTool, Node, NodesConfiguration,\
    Workload

from reports.test import COMPUTER


TEST_NODES_DATA = [
    {
        'CPU model': 'string',
        'CPU number': 8,
        'RAM memory': 16000000000,
        'disk memory': 300000000000,
        'nodes': {
            'viro.intra.ispras.ru': {
                'status': 'HEALTHY',
                'workload': {
                    'reserved CPU number': 4,
                    'reserved RAM memory': 8000000000,
                    'reserved disk memory': 200000000000,
                    'running verification tasks': 2,
                    'running verification jobs': 2,
                    'available for jobs': True,
                    'available for tasks': True
                }
            },
            'cox.intra.ispras.ru': {
                'status': 'DISCONNECTED'
            }
        }
    },
    {
        'CPU model': 'string',
        'CPU number': 8,
        'RAM memory': 64000000000,
        'disk memory': 1000000000000,
        'nodes': {
            'kent.intra.ispras.ru': {
                'status': 'AILING',
                'workload': {
                    'reserved CPU number': 6,
                    'reserved RAM memory': 20000000000,
                    'reserved disk memory': 500000000000,
                    'running verification tasks': 96,
                    'running verification jobs': 0,
                    'available for jobs': False,
                    'available for tasks': True
                }
            },
            'morton.intra.ispras.ru': {
                'status': 'HEALTHY',
                'workload': {
                    'reserved CPU number': 0,
                    'reserved RAM memory': 0,
                    'reserved disk memory': 0,
                    'running verification tasks': 0,
                    'running verification jobs': 0,
                    'available for jobs': True,
                    'available for tasks': True
                }
            },
        }
    },
]

TEST_TOOLS_DATA = [
    {
        'tool': 'BLAST',
        'version': '2.7.2'
    },
    {
        'tool': 'CPAchecker',
        'version': '1.1.1'
    }
]

TEST_JSON = {
    'tasks': {
        'pending': [],
        'processing': [],
        'finished': [],
        'error': []
    },
    'task errors': {},
    'task descriptions': {},
    'task solutions': {},
    'jobs': {
        'pending': [],
        'processing': [],
        'finished': [],
        'error': [],
        'cancelled': []
    },
    'job errors': {},
    'job configurations': {}
}

ARCHIVE_PATH = os.path.join(settings.BASE_DIR, 'service', 'test_files')


class TestService(KleverTestCase):
    def setUp(self):
        super(TestService, self).setUp()
        User.objects.create_superuser('superuser', '', 'top_secret')
        populate_users(
            manager={'username': 'manager', 'password': 'manager'},
            service={'username': 'service', 'password': 'service'}
        )
        self.client.post(reverse('users:login'), {'username': 'manager', 'password': 'manager'})
        self.client.post(reverse('population'))
        self.scheduler = Client()
        self.scheduler.post('/users/service_signin/', {
            'username': 'service', 'password': 'service', 'scheduler': SCHEDULER_TYPE[0][1]
        })
        self.controller = Client()
        self.controller.post('/users/service_signin/', {'username': 'service', 'password': 'service'})
        try:
            self.job = Job.objects.filter(~Q(parent=None))[0]
        except IndexError:
            self.job = Job.objects.all()[0]
        # Run decision
        self.client.post('/jobs/run_decision/%s/' % self.job.pk, {'mode': 'default', 'conf_name': 'development'})
        self.core = Client()
        self.core.post('/users/service_signin/', {
            'username': 'service', 'password': 'service', 'job identifier': self.job.identifier
        })

    def test1_success(self):
        # Set schedulers status
        self.assertEqual(len(SolvingProgress.objects.filter(job_id=self.job.id)), 1)
        self.assertEqual(Scheduler.objects.get(type=SCHEDULER_TYPE[0][0]).status, SCHEDULER_STATUS[1][0])
        self.assertEqual(Scheduler.objects.get(type=SCHEDULER_TYPE[1][0]).status, SCHEDULER_STATUS[1][0])
        response = self.controller.post('/service/set_schedulers_status/', {
            'statuses': json.dumps({
                SCHEDULER_TYPE[0][1]: SCHEDULER_STATUS[0][0],
                SCHEDULER_TYPE[1][1]: SCHEDULER_STATUS[0][0]
            })
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(Scheduler.objects.get(type=SCHEDULER_TYPE[0][0]).status, SCHEDULER_STATUS[0][0])
        self.assertEqual(Scheduler.objects.get(type=SCHEDULER_TYPE[1][0]).status, SCHEDULER_STATUS[0][0])

        # Get jobs and tasks
        sch_data = {
            'tasks': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'task errors': {}, 'task descriptions': {}, 'task solutions': {},
            'jobs': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'job errors': {}, 'job configurations': {}
        }
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        try:
            new_sch_data = json.loads(res['jobs and tasks status'])
            self.assertEqual(new_sch_data['tasks'], {'pending': [], 'processing': [], 'error': [], 'finished': []})
            self.assertEqual(new_sch_data['task errors'], {})
            self.assertEqual(new_sch_data['task descriptions'], {})
            self.assertEqual(new_sch_data['task solutions'], {})
            self.assertEqual(new_sch_data['jobs'], {
                'pending': [self.job.identifier], 'processing': [], 'error': [], 'finished': [], 'cancelled': []
            })
            self.assertEqual(new_sch_data['job errors'], {})
        except Exception as e:
            self.fail("Wrong json: %s" % e)

        # Decide the job
        response = self.core.post('/jobs/decide_job/', {'report': json.dumps({
            'type': 'start', 'id': '/', 'comp': COMPUTER,
            'attrs': [{'name': 'Core version', 'value': 'stage-2-1k123j13'}]
        })})
        self.assertEqual(response.status_code, 200)
        self.assertIn(response['Content-Type'], {'application/x-zip-compressed', 'application/zip'})
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[2][0])

        # Schedule 5 tasks
        task_ids = []
        for i in range(0, 5):
            with open(os.path.join(ARCHIVE_PATH, 'archive.zip'), mode='rb') as fp:
                response = self.core.post('/service/schedule_task/', {
                    'description': json.dumps({'priority': PRIORITY[3][0]}), 'file': fp
                })
                fp.close()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/json')
            progress = SolvingProgress.objects.get(job_id=self.job.pk)
            self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
            self.assertEqual(len(Task.objects.filter(progress__job_id=self.job.pk)), 1 + i)
            self.assertEqual(progress.tasks_pending, 1 + i)
            self.assertEqual(progress.tasks_total, 1 + i)
            task_id = json.loads(str(response.content, encoding='utf8')).get('task id', 0)
            self.assertEqual(len(Task.objects.filter(pk=task_id)), 1)
            task_ids.append(str(task_id))

        # Update scheduler tools
        scheduler_tools = [
            {'tool': 'ToolName1', 'version': 'Version_1'}, {'tool': 'ToolName2', 'version': 'Version_2'},
            {'tool': 'ToolName3', 'version': 'Version_3'}, {'tool': 'ToolName4', 'version': 'Version_4'}
        ]
        response = self.scheduler.post('/service/update_tools/', {'tools data': json.dumps(scheduler_tools)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        tools = VerificationTool.objects.filter(scheduler__type=SCHEDULER_TYPE[0][0])
        self.assertEqual(len(tools), len(scheduler_tools))
        for tool in tools:
            self.assertIn({'tool': tool.name, 'version': tool.version}, scheduler_tools)

        # Get tasks
        sch_data2 = sch_data.copy()
        sch_data2['jobs']['processing'].append(self.job.identifier)
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data2)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(set(json.loads(res['jobs and tasks status'])['tasks']['pending']), set(task_ids))

        # Get task status
        response = self.core.post('/service/get_tasks_statuses/', {'tasks': json.dumps([task_ids[3]])})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(json.loads(res['tasks statuses']), {
            'pending': [task_ids[3]], 'processing': [], 'finished': [], 'error': []
        })

        # Trying to delete unfinished task
        response = self.core.post('/service/remove_task/', {'task id': task_ids[3]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertJSONEqual(
            str(response.content, encoding='utf8'), json.dumps({'error': 'The task is not finished'})
        )

        # Process all tasks
        sch_data2['tasks']['processing'] = task_ids
        sch_data2['tasks']['pending'] = []
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data2)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(set(json.loads(res['jobs and tasks status'])['tasks']['processing']), set(task_ids))
        self.assertEqual(json.loads(res['jobs and tasks status'])['tasks']['pending'], [])

        # Cancel 1st and 2nd tasks
        response = self.core.post('/service/cancel_task/', {'task id': task_ids[0]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        response = self.core.post('/service/cancel_task/', {'task id': task_ids[1]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(Task.objects.filter(id__in=[task_ids[0], task_ids[1]])), 0)
        progress = SolvingProgress.objects.get(job_id=self.job.pk)
        self.assertEqual(progress.tasks_total, 5)
        self.assertEqual(progress.tasks_pending, 0)
        self.assertEqual(progress.tasks_processing, 3)
        self.assertEqual(progress.tasks_cancelled, 2)

        # Download 3d task
        response = self.scheduler.post('/service/download_task/', {'task id': task_ids[2]})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response['Content-Type'], 'application/json')

        # Upload solutions for 3d and 4th tasks
        with open(os.path.join(ARCHIVE_PATH, 'archive.zip'), mode='rb') as fp:
            response = self.core.post('/service/upload_solution/', {
                'task id': task_ids[2], 'file': fp, 'description': json.dumps({'resources': {'wall time': 1000}})
            })
            fp.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        with open(os.path.join(ARCHIVE_PATH, 'archive.zip'), mode='rb') as fp:
            response = self.core.post('/service/upload_solution/', {
                'task id': task_ids[3], 'file': fp, 'description': json.dumps({'resources': {'wall time': 1000}})
            })
            fp.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(Solution.objects.filter(task_id__in=[task_ids[2], task_ids[3]])), 2)
        progress = SolvingProgress.objects.get(job_id=self.job.pk)
        self.assertEqual(progress.solutions, 2)

        # Try to download solution for 3d task
        response = self.core.post('/service/download_solution/', {'task id': task_ids[2]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertJSONEqual(str(response.content, encoding='utf8'), json.dumps({'error': 'The task is not finished'}))

        # Finish decision of 3d and 4th tasks and finish with error for 5th task
        sch_data2['tasks']['processing'] = []
        sch_data2['tasks']['pending'] = []
        sch_data2['tasks']['finished'] = [task_ids[2], task_ids[3]]
        sch_data2['tasks']['error'] = [task_ids[4]]
        sch_data2['task errors'] = {task_ids[4]: 'Task error'}
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data2)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(json.loads(res['jobs and tasks status'])['tasks']['processing'], [])
        self.assertEqual(json.loads(res['jobs and tasks status'])['tasks']['pending'], [])
        self.assertEqual(json.loads(res['jobs and tasks status'])['tasks']['error'], [])
        self.assertEqual(json.loads(res['jobs and tasks status'])['tasks']['finished'], [])

        # Donwload solutions for finished tasks
        response = self.core.post('/service/download_solution/', {'task id': task_ids[2]})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response['Content-Type'], 'application/json')
        response = self.core.post('/service/download_solution/', {'task id': task_ids[4]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertJSONEqual(str(response.content, encoding='utf8'), json.dumps({'task error': 'Task error'}))

        # Delete finished tasks (FAIL FOR WINDOWS)
        response = self.core.post('/service/remove_task/', {'task id': task_ids[2]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        response = self.core.post('/service/remove_task/', {'task id': task_ids[3]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        response = self.core.post('/service/remove_task/', {'task id': task_ids[4]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(Task.objects.filter(id__in=task_ids)), 0)

        # Upload finish report
        with open(os.path.join(settings.BASE_DIR, 'reports', 'test_files', 'log.zip'), mode='rb') as fp:
            response = self.core.post('/reports/upload/', {
                'report': json.dumps({
                    'id': '/', 'type': 'finish', 'resources': {
                        'CPU time': 1000, 'memory size': 5 * 10 ** 8, 'wall time': 2000
                    },
                    'log': 'log.zip', 'desc': 'It does not matter'
                }), 'file': fp
            })
            fp.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Check that scheduler does not get any tasks or jobs
        sch_data3 = sch_data.copy()
        sch_data3['jobs']['finished'].append(self.job.identifier)
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {
            'jobs and tasks status': json.dumps(sch_data3)
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        new_sch_data = json.loads(res['jobs and tasks status'])
        self.assertEqual(new_sch_data['tasks'], {'pending': [], 'processing': [], 'error': [], 'finished': []})
        self.assertEqual(new_sch_data['jobs'], {
            'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []
        })

        # Status is corrupted beacause there are unfinisheed tasks
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[3][0])

        # Check tasks quantities after finishing job decision
        progress = SolvingProgress.objects.get(job_id=self.job.pk)
        self.assertEqual(progress.tasks_total, 5)
        self.assertEqual(progress.solutions, 2)
        self.assertEqual(progress.tasks_error, 1)
        self.assertEqual(progress.tasks_processing, 0)
        self.assertEqual(progress.tasks_pending, 0)
        self.assertEqual(progress.tasks_finished, 2)
        self.assertEqual(progress.tasks_cancelled, 2)

    def test2_unfinished_tasks(self):
        sch_data = {
            'tasks': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'task errors': {}, 'task descriptions': {}, 'task solutions': {},
            'jobs': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'job errors': {}, 'job configurations': {}
        }
        # Decide the job
        self.core.post('/jobs/decide_job/', {'report': json.dumps({
            'type': 'start', 'id': '/', 'comp': COMPUTER,
            'attrs': [{'name': 'Core version', 'value': 'stage-2-1k123j13'}]
        }), 'job format': 1})
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[2][0])

        # Schedule 5 tasks
        task_ids = []
        for i in range(0, 5):
            with open(os.path.join(ARCHIVE_PATH, 'archive.zip'), mode='rb') as fp:
                response = self.core.post('/service/schedule_task/', {
                    'description': json.dumps({'priority': PRIORITY[3][0]}), 'file': fp
                })
                fp.close()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/json')
            self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
            self.assertEqual(len(Task.objects.filter(progress__job_id=self.job.pk)), 1 + i)
            task_id = json.loads(str(response.content, encoding='utf8')).get('task id', 0)
            self.assertEqual(len(Task.objects.filter(pk=task_id)), 1)
            task_ids.append(str(task_id))
        progress = SolvingProgress.objects.get(job_id=self.job.pk)
        self.assertEqual(progress.tasks_pending, 5)
        self.assertEqual(progress.tasks_total, 5)

        # Get tasks
        sch_data2 = sch_data.copy()
        sch_data2['jobs']['processing'].append(self.job.identifier)
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data2)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(set(json.loads(res['jobs and tasks status'])['tasks']['pending']), set(task_ids))

        # Process first 3 tasks
        sch_data2['tasks']['processing'] = list(x for x in task_ids[:3])
        sch_data2['tasks']['pending'] = list(x for x in task_ids[3:])
        self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data2)})

        # Cancel the 4th task
        self.core.post('/service/cancel_task/', {'task id': task_ids[3]})
        self.assertEqual(len(Task.objects.filter(pk=task_ids[3])), 0)
        progress = SolvingProgress.objects.get(job_id=self.job.pk)
        self.assertEqual(progress.tasks_total, 5)
        self.assertEqual(progress.tasks_pending, 1)
        self.assertEqual(progress.tasks_processing, 3)
        self.assertEqual(progress.tasks_cancelled, 1)

        # Upload solution for the 1st task
        with open(os.path.join(ARCHIVE_PATH, 'archive.zip'), mode='rb') as fp:
            response = self.core.post('/service/upload_solution/', {
                'task id': task_ids[0], 'file': fp, 'description': json.dumps({'resources': {'wall time': 1000}})
            })
            fp.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(Solution.objects.filter(task_id=task_ids[0])), 1)
        self.assertEqual(SolvingProgress.objects.get(job_id=self.job.pk).solutions, 1)

        # Finish decision of the 1st task and finish with error the 2nd task
        sch_data2['tasks']['processing'] = [task_ids[2]]
        sch_data2['tasks']['pending'] = [task_ids[4]]
        sch_data2['tasks']['finished'] = [task_ids[0]]
        sch_data2['tasks']['error'] = [task_ids[1]]
        sch_data2['task errors'] = {task_ids[1]: 'Task error'}
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data2)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(set(json.loads(res['jobs and tasks status'])['tasks']['processing']), {task_ids[2]})
        self.assertEqual(set(json.loads(res['jobs and tasks status'])['tasks']['pending']), {task_ids[4]})
        self.assertEqual(json.loads(res['jobs and tasks status'])['tasks']['error'], [])
        self.assertEqual(json.loads(res['jobs and tasks status'])['tasks']['finished'], [])

        # Delete finished tasks (FAIL FOR WINDOWS)
        response = self.core.post('/service/remove_task/', {'task id': task_ids[0]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        response = self.core.post('/service/remove_task/', {'task id': task_ids[1]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(Task.objects.filter(id__in=[task_ids[0], task_ids[1], task_ids[3]])), 0)

        # Upload finish report
        with open(os.path.join(settings.BASE_DIR, 'reports', 'test_files', 'log.zip'), mode='rb') as fp:
            response = self.core.post('/reports/upload/', {
                'report': json.dumps({
                    'id': '/', 'type': 'finish', 'resources': {
                        'CPU time': 1000, 'memory size': 5 * 10**8, 'wall time': 2000
                    },
                    'log': 'log.zip', 'desc': 'It does not matter'
                }), 'file': fp
            })
            fp.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Check that scheduler does not get any tasks or jobs
        sch_data3 = sch_data.copy()
        sch_data3['jobs']['finished'].append(self.job.identifier)
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data3)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        new_sch_data = json.loads(res['jobs and tasks status'])
        self.assertEqual(new_sch_data['tasks'], {'pending': [], 'processing': [], 'error': [], 'finished': []})
        self.assertEqual(new_sch_data['jobs'], {
            'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []
        })

        # Status is corrupted beacause there are unfinisheed tasks
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[5][0])

        # Check tasks quantities after finishing job decision
        progress = SolvingProgress.objects.get(job_id=self.job.pk)
        self.assertEqual(progress.tasks_total, 5)
        self.assertEqual(progress.solutions, 1)
        self.assertEqual(progress.tasks_error, 1)
        self.assertEqual(progress.tasks_processing, 1)
        self.assertEqual(progress.tasks_pending, 1)
        self.assertEqual(progress.tasks_finished, 1)
        self.assertEqual(progress.tasks_cancelled, 1)

    def test3_disconnect(self):
        # Decide job
        response = self.core.post('/jobs/decide_job/', {'report': json.dumps({
            'type': 'start', 'id': '/', 'comp': COMPUTER,
            'attrs': [{'name': 'Core version', 'value': 'stage-2-1k123j13'}]
        })})
        self.assertEqual(response.status_code, 200)
        self.assertIn(response['Content-Type'], {'application/x-zip-compressed', 'application/zip'})
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[2][0])

        # Schedule 5 tasks
        task_ids = []
        for i in range(0, 5):
            with open(os.path.join(ARCHIVE_PATH, 'archive.zip'), mode='rb') as fp:
                response = self.core.post('/service/schedule_task/', {
                    'description': json.dumps({'priority': PRIORITY[3][0]}), 'file': fp
                })
                fp.close()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/json')
            self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
            self.assertEqual(len(Task.objects.filter(progress__job_id=self.job.pk)), 1 + i)
            task_id = json.loads(str(response.content, encoding='utf8')).get('task id', 0)
            self.assertEqual(len(Task.objects.filter(pk=task_id)), 1)
            task_ids.append(str(task_id))

        progress = SolvingProgress.objects.get(job_id=self.job.pk)
        self.assertEqual(progress.tasks_pending, 5)
        self.assertEqual(progress.tasks_total, 5)

        # Get tasks
        sch_data = {
            'tasks': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'task errors': {}, 'task descriptions': {}, 'task solutions': {},
            'jobs': {'pending': [], 'processing': [self.job.identifier], 'error': [], 'finished': [], 'cancelled': []},
            'job errors': {}, 'job configurations': {}
        }
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(set(json.loads(res['jobs and tasks status'])['tasks']['pending']), set(task_ids))

        # Process first 4 tasks
        sch_data['tasks']['processing'] = list(x for x in task_ids[:4])
        sch_data['tasks']['pending'] = [task_ids[4]]
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(set(json.loads(res['jobs and tasks status'])['tasks']['processing']), set(task_ids[:4]))
        self.assertEqual(set(json.loads(res['jobs and tasks status'])['tasks']['pending']), {task_ids[4]})

        # Upload solution for 1st task
        with open(os.path.join(ARCHIVE_PATH, 'archive.zip'), mode='rb') as fp:
            response = self.core.post('/service/upload_solution/', {
                'task id': task_ids[0], 'file': fp, 'description': json.dumps({'resources': {'wall time': 1000}})
            })
            fp.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(Solution.objects.filter(task_id=task_ids[0])), 1)

        # Finish decision of 1st task and finish with error for 2nd task
        sch_data['tasks'] = {
            'processing': [task_ids[2], task_ids[3]], 'pending': [task_ids[4]], 'finished': [task_ids[0]],
            'error': [task_ids[1]], 'cancel': []
        }
        sch_data['task errors'] = {task_ids[1]: 'Task error'}
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(
            set(json.loads(res['jobs and tasks status'])['tasks']['processing']), set(sch_data['tasks']['processing'])
        )
        self.assertEqual(
            set(json.loads(res['jobs and tasks status'])['tasks']['pending']), set(sch_data['tasks']['pending'])
        )
        self.assertEqual(json.loads(res['jobs and tasks status'])['tasks']['error'], [])
        self.assertEqual(json.loads(res['jobs and tasks status'])['tasks']['finished'], [])

        # Donwload solutions for finished tasks
        response = self.core.post('/service/download_solution/', {'task id': task_ids[0]})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response['Content-Type'], 'application/json')
        response = self.core.post('/service/download_solution/', {'task id': task_ids[1]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertJSONEqual(str(response.content, encoding='utf8'), json.dumps({'task error': 'Task error'}))

        # Disconnect Klever scheduler
        response = self.controller.post('/service/set_schedulers_status/', {
            'statuses': json.dumps({
                SCHEDULER_TYPE[0][1]: SCHEDULER_STATUS[2][0],
                SCHEDULER_TYPE[1][1]: SCHEDULER_STATUS[0][0]
            })
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(Scheduler.objects.get(type=SCHEDULER_TYPE[0][0]).status, SCHEDULER_STATUS[2][0])
        self.assertEqual(Scheduler.objects.get(type=SCHEDULER_TYPE[1][0]).status, SCHEDULER_STATUS[0][0])

        # Status is terminated because scheduler is disconnected
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[8][0])

        # Check that scheduler does not get any tasks or jobs
        sch_data = {
            'tasks': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'task errors': {}, 'task descriptions': {}, 'task solutions': {},
            'jobs': {'pending': [], 'processing': [self.job.identifier], 'error': [], 'finished': [], 'cancelled': []},
            'job errors': {}, 'job configurations': {}
        }
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {
            'jobs and tasks status': json.dumps(sch_data)
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        new_sch_data = json.loads(res['jobs and tasks status'])
        self.assertEqual(new_sch_data['tasks'], {'pending': [], 'processing': [], 'error': [], 'finished': []})
        self.assertEqual(new_sch_data['jobs'], {
            'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []
        })

        # Check that after job is corrupted you can't upload report
        with open(os.path.join(settings.BASE_DIR, 'reports', 'test_files', 'log.zip'), mode='rb') as fp:
            response = self.core.post('/reports/upload/', {
                'report': json.dumps({
                    'id': '/', 'type': 'finish', 'resources': {
                        'CPU time': 1000, 'memory size': 5 * 10 ** 8, 'wall time': 2000
                    },
                    'log': 'log.zip', 'desc': 'It does not matter'
                }), 'file': fp
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertJSONEqual(
            str(response.content, encoding='utf8'),
            json.dumps({'error': 'Reports can be uploaded only for processing jobs'})
        )

        # Check tasks quantities after finishing job decision
        progress = SolvingProgress.objects.get(job_id=self.job.pk)
        self.assertEqual(progress.error, 'Klever scheduler was disconnected')
        self.assertEqual(progress.tasks_total, 5)
        self.assertEqual(progress.solutions, 1)
        self.assertEqual(progress.tasks_error, 4)
        self.assertEqual(progress.tasks_processing, 0)
        self.assertEqual(progress.tasks_pending, 0)
        self.assertEqual(progress.tasks_finished, 1)
        self.assertEqual(progress.tasks_cancelled, 0)

    def test4_cancel_job(self):
        # Decide job
        self.core.post('/jobs/decide_job/', {'report': json.dumps({
            'type': 'start', 'id': '/', 'comp': COMPUTER,
            'attrs': [{'name': 'Core version', 'value': 'stage-2-1k123j13'}]
        }), 'job format': 1})

        # Schedule 5 tasks
        task_ids = []
        for i in range(0, 5):
            with open(os.path.join(ARCHIVE_PATH, 'archive.zip'), mode='rb') as fp:
                response = self.core.post('/service/schedule_task/', {
                    'description': json.dumps({'priority': PRIORITY[3][0]}), 'file': fp
                })
                fp.close()
            task_ids.append(str(json.loads(str(response.content, encoding='utf8')).get('task id', 0)))

        # Get tasks
        sch_data = {
            'tasks': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'task errors': {}, 'task descriptions': {}, 'task solutions': {},
            'jobs': {'pending': [], 'processing': [self.job.identifier], 'error': [], 'finished': [], 'cancelled': []},
            'job errors': {}, 'job configurations': {}
        }
        self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data)})

        # Process first 4 tasks
        sch_data['tasks']['processing'] = list(x for x in task_ids[:4])
        sch_data['tasks']['pending'] = [task_ids[4]]
        self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data)})

        # Upload solution for the 1st task
        with open(os.path.join(ARCHIVE_PATH, 'archive.zip'), mode='rb') as fp:
            self.core.post('/service/upload_solution/', {
                'task id': task_ids[0], 'file': fp, 'description': json.dumps({'resources': {'wall time': 1000}})
            })
            fp.close()

        # Finish decision of the 1st task and finish with error for the 2nd task
        sch_data['tasks'] = {
            'processing': [task_ids[2], task_ids[3]], 'pending': [task_ids[4]], 'finished': [task_ids[0]],
            'error': [task_ids[1]], 'cancel': []
        }
        sch_data['task errors'] = {task_ids[1]: 'Task error'}
        self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data)})

        # Stop job decision
        response = self.client.post('/jobs/stop_decision/%s/' % self.job.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Check that scheduler does not get any tasks or jobs
        sch_data = {
            'tasks': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'task errors': {}, 'task descriptions': {}, 'task solutions': {},
            'jobs': {'pending': [], 'processing': [self.job.identifier], 'error': [], 'finished': [], 'cancelled': []},
            'job errors': {}, 'job configurations': {}
        }
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        new_sch_data = json.loads(res['jobs and tasks status'])
        self.assertEqual(new_sch_data['tasks'], {'pending': [], 'processing': [], 'error': [], 'finished': []})
        self.assertEqual(new_sch_data['jobs'], {
            'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': [self.job.identifier]
        })
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[6][0])

        # Check that getting tasks with cancelling job in cancelled list makes job cancelled
        response = self.scheduler.post('/service/get_jobs_and_tasks/',
                                       {'jobs and tasks status': json.dumps(new_sch_data)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[7][0])

        # Check tasks quantities after finishing job decision
        progress = SolvingProgress.objects.get(job_id=self.job.pk)
        self.assertEqual(progress.error, 'The job was cancelled')
        self.assertEqual(progress.tasks_total, 5)
        self.assertEqual(progress.solutions, 1)
        self.assertEqual(progress.tasks_error, 1)
        self.assertEqual(progress.tasks_processing, 0)
        self.assertEqual(progress.tasks_pending, 0)
        self.assertEqual(progress.tasks_finished, 1)
        self.assertEqual(progress.tasks_cancelled, 3)

    def test_nodes_and_sch_user(self):
        nodes_data = [
            {
                'CPU model': 'CPU_model_1',
                'CPU number': 8,
                'RAM memory': 16 * 10**9,
                'disk memory': 10**12,
                'nodes': {
                    'node1': {
                        'status': NODE_STATUS[1][0],
                        'workload': {
                            'reserved CPU number': 3,
                            'reserved RAM memory': 2 * 10**9,
                            'reserved disk memory': 10**11,
                            'running verification jobs': 2,
                            'running verification tasks': 9,
                            'available for jobs': True,
                            'available for tasks': True
                        }
                    },
                    'node2': {
                        'status': NODE_STATUS[2][0],
                        'workload': {
                            'reserved CPU number': 1,
                            'reserved RAM memory': 10 ** 9,
                            'reserved disk memory': 10 ** 9,
                            'running verification jobs': 0,
                            'running verification tasks': 15,
                            'available for jobs': False,
                            'available for tasks': True
                        }
                    },
                    'node3': {
                        'status': NODE_STATUS[3][0]
                    }
                }
            },
            {
                'CPU model': 'CPU_model_2',
                'CPU number': 8,
                'RAM memory': 12 * 10 ** 9,
                'disk memory': 5 * 10 ** 11,
                'nodes': {
                    'node4': {
                        'status': NODE_STATUS[1][0],
                        'workload': {
                            'reserved CPU number': 3,
                            'reserved RAM memory': 10 ** 9,
                            'reserved disk memory': 2 * 10 ** 11,
                            'running verification jobs': 0,
                            'running verification tasks': 0,
                            'available for jobs': False,
                            'available for tasks': False
                        }
                    },
                    'node5': {
                        'status': NODE_STATUS[0][0]
                    }
                }
            }
        ]
        response = self.controller.post('/service/update_nodes/', {
            'nodes data': json.dumps(nodes_data)
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        for n_conf in nodes_data:
            try:
                configuration = NodesConfiguration.objects.get(
                    cpu=n_conf['CPU model'], cores=n_conf['CPU number'],
                    ram=n_conf['RAM memory'], memory=n_conf['disk memory']
                )
            except ObjectDoesNotExist:
                self.fail('Nodes configuration was not created')
            for n in n_conf['nodes']:
                try:
                    node = Node.objects.get(config=configuration, hostname=n, status=n_conf['nodes'][n]['status'])
                except ObjectDoesNotExist:
                    self.fail("Node was not created")
                if 'workload' in n_conf['nodes'][n]:
                    self.assertEqual(len(Workload.objects.filter(
                        id=node.workload_id,
                        jobs=n_conf['nodes'][n]['workload']['running verification jobs'],
                        tasks=n_conf['nodes'][n]['workload']['running verification tasks'],
                        cores=n_conf['nodes'][n]['workload']['reserved CPU number'],
                        ram=n_conf['nodes'][n]['workload']['reserved RAM memory'],
                        memory=n_conf['nodes'][n]['workload']['reserved disk memory'],
                        for_jobs=n_conf['nodes'][n]['workload']['available for jobs'],
                        for_tasks=n_conf['nodes'][n]['workload']['available for tasks']
                    )), 1)
                else:
                    self.assertIsNone(node.workload)
        response = self.client.get(reverse('service:schedulers', args=[]))
        self.assertEqual(response.status_code, 200)

        response = self.client.post('/service/ajax/add_scheduler_user/', {
            'login': 'sch_user', 'password': 'sch_passwd'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(str(response.content, encoding='utf8'), '{}')
        try:
            SchedulerUser.objects.get(user__username='manager', login='sch_user', password='sch_passwd')
        except ObjectDoesNotExist:
            self.fail()
