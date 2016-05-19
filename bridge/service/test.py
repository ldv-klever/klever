import os
import json
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.test import Client, TestCase
from bridge.populate import populate_users
from bridge.settings import BASE_DIR
from bridge.vars import JOB_STATUS
from reports.test import COMPUTER
from service.models import *


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

ARCHIVE_PATH = os.path.join(BASE_DIR, 'service', 'test_files')


class TestService(TestCase):
    def setUp(self):
        self.client = Client()
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
        self.client.post('/jobs/ajax/fast_run_decision/', {'job_id': self.job.pk})
        self.core = Client()
        self.core.post('/users/service_signin/', {
            'username': 'service', 'password': 'service', 'job identifier': self.job.identifier
        })

    def test_normal(self):
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
        self.assertEqual(json.loads(str(response.content, encoding='utf8')).get('error', None), None)
        self.assertEqual(Scheduler.objects.get(type=SCHEDULER_TYPE[0][0]).status, SCHEDULER_STATUS[0][0])
        self.assertEqual(Scheduler.objects.get(type=SCHEDULER_TYPE[1][0]).status, SCHEDULER_STATUS[0][0])

        # Get jobs and tasks
        sch_data = {
            'tasks': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'task errors': {},
            'task descriptions': {},
            'task solutions': {},
            'jobs': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'job errors': {},
            'job configurations': {}
        }
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertEqual(res.get('error', None), None)
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
            self.assertEqual(new_sch_data['job configurations'], {
                self.job.identifier: json.loads(self.job.solvingprogress.configuration.decode('utf8'))
            })
        except Exception as e:
            self.fail("Wrong json: %s" % e)
        response = self.core.post('/jobs/decide_job/', {'report': json.dumps({
            'type': 'start', 'id': '/', 'attrs': [{'PSI version': 'stage-2-1k123j13'}], 'comp': COMPUTER
        }), 'job format': 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/x-tar-gz')
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[2][0])

        # Schedule 10 tasks
        task_ids = []
        for i in range(0, 10):
            with open(os.path.join(ARCHIVE_PATH, 'archive.tar.gz'), mode='rb') as fp:
                response = self.core.post('/service/schedule_task/', {
                    'description': json.dumps({'priority': PRIORITY[3][0]}), 'file': fp
                })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/json')
            progress = SolvingProgress.objects.get(job_id=self.job.pk)
            self.assertEqual(json.loads(str(response.content, encoding='utf8')).get('error', None), None)
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
        self.assertEqual(json.loads(str(response.content, encoding='utf8')).get('error', None), None)
        tools = VerificationTool.objects.filter(scheduler__type=SCHEDULER_TYPE[0][0])
        self.assertEqual(len(tools), len(scheduler_tools))
        for tool in tools:
            self.assertEqual({'tool': tool.name, 'version': tool.version} in scheduler_tools, True)

        # Get tasks
        sch_data2 = sch_data.copy()
        sch_data2['jobs']['processing'].append(self.job.identifier)
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data2)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertEqual(res.get('error', None), None)
        self.assertEqual(set(json.loads(res['jobs and tasks status'])['tasks']['pending']), set(task_ids))

        # Get task status
        response = self.core.post('/service/get_task_status/', {'task id': task_ids[3]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertEqual(res.get('error', None), None)
        self.assertEqual(res['task status'], TASK_STATUS[0][0])

        # Trying to delete unfinished task
        response = self.core.post('/service/remove_task/', {'task id': task_ids[3]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertEqual(res.get('error', None), "The task is not finished")

        # Process first 5 tasks
        sch_data2['tasks']['processing'] = list(x for x in task_ids[:5])
        sch_data2['tasks']['pending'] = list(x for x in task_ids[5:])
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data2)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertEqual(res.get('error', None), None)
        self.assertEqual(set(json.loads(res['jobs and tasks status'])['tasks']['processing']), set(task_ids[:5]))
        self.assertEqual(set(json.loads(res['jobs and tasks status'])['tasks']['pending']), set(task_ids[5:]))

        # Cancel 1st and 6th tasks
        response = self.core.post('/service/cancel_task/', {'task id': task_ids[0]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertEqual(res.get('error', None), None)
        response = self.core.post('/service/cancel_task/', {'task id': task_ids[5]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertEqual(res.get('error', None), None)
        self.assertEqual(len(Task.objects.filter(id__in=[task_ids[0], task_ids[5]])), 0)
        progress = SolvingProgress.objects.get(job_id=self.job.pk)
        self.assertEqual(progress.tasks_total, 10)
        self.assertEqual(progress.tasks_pending, 4)
        self.assertEqual(progress.tasks_processing, 4)
        self.assertEqual(progress.tasks_cancelled, 2)

        # Download 2nd task
        response = self.scheduler.post('/service/download_task/', {'task id': task_ids[1]})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response['Content-Type'], 'application/json')

        # Upload solutions for 2nd and 7th tasks
        with open(os.path.join(ARCHIVE_PATH, 'archive.tar.gz'), mode='rb') as fp:
            response = self.core.post('/service/upload_solution/', {
                'task id': task_ids[1], 'file': fp, 'description': json.dumps({'solution_data': None})
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertEqual(res.get('error', None), None)
        with open(os.path.join(ARCHIVE_PATH, 'archive.tar.gz'), mode='rb') as fp:
            response = self.core.post('/service/upload_solution/', {
                'task id': task_ids[6], 'file': fp, 'description': json.dumps({'solution_data': None})
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertEqual(res.get('error', None), None)
        self.assertEqual(len(Solution.objects.filter(task_id__in=[task_ids[1], task_ids[6]])), 2)
        progress = SolvingProgress.objects.get(job_id=self.job.pk)
        self.assertEqual(progress.solutions, 2)

        # Try to download solution for 2nd task
        response = self.core.post('/service/download_solution/', {'task id': task_ids[1]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertEqual(res.get('error', None), 'The task is not finished')

        # Finish decision of 2nd and 7th tasks and finish with error for 3d and 8th tasks
        sch_data2['tasks']['processing'] = [task_ids[3], task_ids[4]]
        sch_data2['tasks']['pending'] = [task_ids[8], task_ids[9]]
        sch_data2['tasks']['finished'] = [task_ids[1], task_ids[6]]
        sch_data2['tasks']['error'] = [task_ids[2], task_ids[7]]
        sch_data2['task errors'] = {task_ids[2]: 'Task error 1', task_ids[7]: 'Task error 2'}
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data2)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertEqual(res.get('error', None), None)
        self.assertEqual(
            set(json.loads(res['jobs and tasks status'])['tasks']['processing']),
            set(sch_data['tasks']['processing'])
        )
        self.assertEqual(
            set(json.loads(res['jobs and tasks status'])['tasks']['pending']),
            set(sch_data['tasks']['pending'])
        )
        self.assertEqual(json.loads(res['jobs and tasks status'])['tasks']['error'], [])
        self.assertEqual(json.loads(res['jobs and tasks status'])['tasks']['finished'], [])
        sch_data2['task errors'] = {}

        # Donwload solutions for finished tasks
        response = self.core.post('/service/download_solution/', {'task id': task_ids[1]})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response['Content-Type'], 'application/json')
        response = self.core.post('/service/download_solution/', {'task id': task_ids[6]})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response['Content-Type'], 'application/json')
        response = self.core.post('/service/download_solution/', {'task id': task_ids[2]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(json.loads(str(response.content, encoding='utf8')).get('task error', None), 'Task error 1')
        response = self.core.post('/service/download_solution/', {'task id': task_ids[7]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(json.loads(str(response.content, encoding='utf8')).get('task error', None), 'Task error 2')

        # Delete finished tasks
        response = self.core.post('/service/remove_task/', {'task id': task_ids[1]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIsNone(json.loads(str(response.content, encoding='utf8')).get('error', None))
        response = self.core.post('/service/remove_task/', {'task id': task_ids[2]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIsNone(json.loads(str(response.content, encoding='utf8')).get('error', None))
        response = self.core.post('/service/remove_task/', {'task id': task_ids[6]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIsNone(json.loads(str(response.content, encoding='utf8')).get('error', None))
        response = self.core.post('/service/remove_task/', {'task id': task_ids[7]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIsNone(json.loads(str(response.content, encoding='utf8')).get('error', None))
        self.assertEqual(len(Task.objects.filter(id__in=[task_ids[1], task_ids[2], task_ids[6], task_ids[7]])), 0)

        # Upload finish report
        with open(os.path.join(BASE_DIR, 'reports', 'test_files', 'report.tar.gz'), mode='rb') as fp:
            response = self.core.post('/reports/upload/', {
                'report': json.dumps({
                    'id': '/', 'type': 'finish', 'resources': {
                        'CPU time': 1000, 'memory size': 5 * 10**8, 'wall time': 2000
                    },
                    'log': 'log.txt', 'desc': 'It does not matter'
                }), 'file': fp
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIsNone(json.loads(str(response.content, encoding='utf8')).get('error', None))

        sch_data3 = sch_data.copy()
        sch_data3['jobs']['finished'].append(self.job.identifier)
        response = self.scheduler.post('/service/get_jobs_and_tasks/', {
            'jobs and tasks status': json.dumps(sch_data3)
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        # Status is corrupted beacause there are unfinisheed tasks
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[5][0])

        # Check tasks quantities after finishing job decision
        progress = SolvingProgress.objects.get(job_id=self.job.pk)
        self.assertEqual(progress.tasks_total, 10)
        self.assertEqual(progress.solutions, 2)
        self.assertEqual(progress.tasks_error, 2)
        self.assertEqual(progress.tasks_processing, 2)
        self.assertEqual(progress.tasks_pending, 2)
        self.assertEqual(progress.tasks_finished, 2)
        self.assertEqual(progress.tasks_cancelled, 2)

    def __test_disconnect(self):
        # TODO
        pass

    def __test_cancel_job(self):
        # TODO
        pass

    def __test_nodes(self):
        # TODO
        pass

    def __test_success(self):
        # TODO: finish all tasks before finishing job
        pass
