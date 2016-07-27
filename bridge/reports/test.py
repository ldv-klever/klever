import os
import json
import random
from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.test import Client
from bridge.populate import populate_users
from bridge.settings import BASE_DIR
from bridge.vars import SCHEDULER_TYPE, JOB_STATUS, JOB_ROLES, JOB_CLASSES
from bridge.utils import KleverTestCase, ArchiveFileContent
from reports.models import *


LINUX_ATTR = {'Linux kernel': [{'version': '3.5.0'}, {'architecture': 'x86_64'}, {'configuration': 'allmodconfig'}]}
LKVOG_ATTR = {'LKVOG strategy': [{'name': 'separate modules'}]}
COMPUTER = [
    {"node name": "hellwig.intra.ispras.ru"},
    {"CPU model": "Intel(R) Core(TM) i7-3770 CPU @ 3.40GHz"},
    {"number of CPU cores": 8},
    {"memory size": 16808734720},
    {"Linux kernel version": "3.16.7-29-default"},
    {"architecture": "x86_64"}
]
CHUNKS1 = [
    {
        'attrs': [
            {'Verification object': 'drivers/usb/core/usb1.ko'},
            {'Rule specification': 'linux:mutex'}
        ],
        'tool_attrs': [{'Bug kind': 'unsafe bug:kind1'}],
        'tool': 'BLAST 2.7.2',
        'unsafes': ['unsafe1.tar.gz', 'unsafe2.tar.gz'],
        'unknown': 'unknown2.tar.gz'
    },
    {
        'attrs': [
            {'Verification object': 'drivers/usb/core/usb1.ko'},
            {'Rule specification': 'linux:rule1'}
        ],
        'tool_attrs': [{'Bug kind': 'unsafe bug:kind1'}],
        'tool': 'BLAST 2.7.2',
        'unsafes': ['unsafe3.tar.gz']
    },
    {
        'attrs': [
            {'Verification object': 'drivers/usb/core/usb2.ko'},
            {'Rule specification': 'linux:mutex'}
        ],
        'tool_attrs': [{'Bug kind': 'unsafe bug:kind1'}],
        'tool': 'BLAST 2.7.2',
        'safe': 'safe.tar.gz'
    },
    {
        'attrs': [
            {'Verification object': 'drivers/usb/core/usb3.ko'},
            {'Rule specification': 'linux:mutex'}
        ],
        'tool_attrs': [{'Bug kind': 'unsafe bug:kind1'}],
        'tool': 'CPAchecker',
        'unsafes': ['unsafe3.tar.gz']
    },
    {
        'attrs': [
            {'Verification object': 'drivers/usb/core/usb4.ko'},
            {'Rule specification': 'linux:rule1'}
        ],
        'fail': 'EMG',
        'unknown': 'unknown0.tar.gz'
    },
    {
        'attrs': [
            {'Verification object': 'drivers/usb/core/usb5.ko'},
            {'Rule specification': 'linux:mutex'}
        ],
        'tool_attrs': [{'Bug kind': 'unsafe bug:kind1'}],
        'tool': 'BLAST 2.7.2',
        'unsafes': ['unsafe1.tar.gz', 'unsafe2.tar.gz'],
        'unknown': 'unknown1.tar.gz'
    },
    {
        'attrs': [
            {'Verification object': 'drivers/usb/core/usb6.ko'},
            {'Rule specification': 'linux:mutex'}
        ],
        'fail': 'SA',
        'unknown': 'unknown3.tar.gz'
    }
]
CHUNKS2 = [
    {
        'attrs': [
            {'Verification object': 'drivers/usb/core/usb1.ko'},
            {'Rule specification': 'linux:mutex'}
        ],
        'tool_attrs': [{'Bug kind': 'unsafe bug:kind1'}],
        'tool': 'BLAST 2.7.2',
        'unknown': 'unknown1.tar.gz'
    },
    {
        'attrs': [
            {'Verification object': 'drivers/usb/core/usb2.ko'},
            {'Rule specification': 'linux:mutex'}
        ],
        'tool_attrs': [{'Bug kind': 'unsafe bug:kind1'}],
        'tool': 'BLAST 2.7.2',
        'safe': 'safe.tar.gz'
    },
    {
        'attrs': [
            {'Verification object': 'drivers/usb/core/usb3.ko'},
            {'Rule specification': 'linux:mutex'}
        ],
        'tool_attrs': [{'Bug kind': 'unsafe bug:kind1'}],
        'tool': 'CPAchecker',
        'unsafes': ['unsafe3.tar.gz']
    },
    {
        'attrs': [
            {'Verification object': 'drivers/usb/core/usb4.ko'},
            {'Rule specification': 'linux:rule1'}
        ],
        'tool_attrs': [{'Bug kind': 'unsafe bug:kind1'}],
        'tool': 'CPAchecker',
        'unsafes': ['unsafe1.tar.gz']
    },
    {
        'attrs': [
            {'Verification object': 'drivers/usb/core/usb5.ko'},
            {'Rule specification': 'linux:mutex'}
        ],
        'tool_attrs': [{'Bug kind': 'unsafe bug:kind1'}],
        'tool': 'BLAST 2.7.2',
        'unsafes': ['unsafe1.tar.gz', 'unsafe2.tar.gz'],
        'unknown': 'unknown1.tar.gz'
    },
    {
        'attrs': [
            {'Verification object': 'drivers/usb/core/usb6.ko'},
            {'Rule specification': 'linux:mutex'}
        ],
        'tool_attrs': [{'Bug kind': 'unsafe bug:kind1'}],
        'tool': 'BLAST 2.7.2',
        'safe': 'safe.tar.gz'
    }
]
ARCHIVE_PATH = os.path.join(BASE_DIR, 'reports', 'test_files')


def resources():
    return {
        'CPU time': random.randint(100, 10000),
        'memory size': random.randint(10**7, 10**9),
        'wall time': random.randint(100, 10000)
    }


class TestReports(KleverTestCase):
    def setUp(self):
        super(TestReports, self).setUp()
        self.service_client = Client()
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

    def test_reports(self):
        self.ids_in_use = []
        try:
            self.job = Job.objects.filter(~Q(parent=None))[0]
        except IndexError:
            self.job = Job.objects.all()[0]
        # Run decision
        self.client.post('/jobs/ajax/fast_run_decision/', {'job_id': self.job.pk})

        # Service sign in and check session parameters
        response = self.service_client.post('/users/service_signin/', {
            'username': 'service', 'password': 'service',
            'job identifier': self.job.identifier,
            'scheduler': SCHEDULER_TYPE[0][1]
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
        self.assertEqual(self.service_client.session.get('scheduler', None), SCHEDULER_TYPE[0][0])
        self.assertEqual(self.service_client.session.get('job id', None), self.job.pk)

        self.__decide_job()
        main_report = ReportComponent.objects.get(parent=None, root__job_id=self.job.pk)

        response = self.client.get(reverse('reports:component', args=[self.job.pk, main_report.pk]))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse('reports:list', args=[main_report.pk, 'unsafes']))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('reports:list', args=[main_report.pk, 'safes']))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('reports:list', args=[main_report.pk, 'unknowns']))
        self.assertEqual(response.status_code, 200)

        for report in ReportComponent.objects.filter(~Q(parent=None) & Q(root__job_id=self.job.pk)):
            response = self.client.get(reverse('reports:component', args=[self.job.pk, report.pk]))
            self.assertEqual(response.status_code, 200)
            response = self.client.get(reverse('reports:list', args=[report.pk, 'unsafes']))
            self.assertEqual(response.status_code, 200)
            response = self.client.get(reverse('reports:list', args=[report.pk, 'safes']))
            self.assertEqual(response.status_code, 200)
            response = self.client.get(reverse('reports:list', args=[report.pk, 'unknowns']))
            self.assertEqual(response.status_code, 200)
            response = self.client.get(reverse('reports:unknowns', args=[main_report.pk, report.component_id]))
            self.assertEqual(response.status_code, 200)
        for report in ReportUnknown.objects.all():
            response = self.client.get(reverse('reports:leaf', args=['unknown', report.pk]))
            self.assertEqual(response.status_code, 200)
        for report in ReportUnsafe.objects.all():
            response = self.client.get(reverse('reports:leaf', args=['unsafe', report.pk]))
            self.assertEqual(response.status_code, 200)
            response = self.client.get(reverse('reports:etv', args=[report.pk]))
            self.assertEqual(response.status_code, 200)
        for report in ReportSafe.objects.all():
            response = self.client.get(reverse('reports:leaf', args=['safe', report.pk]))
            self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('reports:download_files', args=[main_report.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/x-tar-gz')
        unsafe = ReportUnsafe.objects.all()[0]

        # TODO:
        # Next function get random file from archive, but if this file is error trace
        # then request to get source code is not tested.
        afc = ArchiveFileContent(unsafe.archive)
        self.assertEqual(afc.error, None)
        if afc._name != unsafe.error_trace:
            response = self.client.post('/reports/ajax/get_source/', {
                'report_id': unsafe.pk, 'file_name': afc._name
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/json')
            self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        response = self.client.post('/reports/logcontent/%s/' % main_report.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')

        response = self.client.post(reverse('reports:log', args=[main_report.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')

        # Collapse job
        response = self.client.post('/jobs/ajax/collapse_reports/', {'job_id': self.job.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        self.assertEqual(len(ReportSafe.objects.filter(root__job=self.job)), 0)
        self.assertEqual(
            len(ReportComponent.objects.filter(Q(root__job=self.job) & ~Q(parent__parent=None) & ~Q(parent=None))), 0
        )

        self.job = Job.objects.get(pk=self.job.pk)
        self.job.light = True
        self.job.save()
        self.client.post('/jobs/ajax/fast_run_decision/', {'job_id': self.job.pk})
        DecideJobs('service', 'service', CHUNKS1)
        self.assertEqual(len(ReportSafe.objects.filter(root__job=self.job)), 0)
        self.assertEqual(
            len(ReportComponent.objects.filter(Q(root__job=self.job) & ~Q(parent__parent=None) & ~Q(parent=None))), 0
        )

    def test_comparison(self):
        try:
            # Exclude jobs "Validation on commits" due to they need additional attribute for comparison: "Commit"
            job1 = Job.objects.filter(~Q(parent=None) & ~Q(type=JOB_CLASSES[3][0]))[0]
        except IndexError:
            job1 = Job.objects.filter(~Q(type=JOB_CLASSES[3][0]))[0]

        response = self.client.post('/jobs/ajax/savejob/', {
            'title': 'New job title',
            'description': 'Description of new job',
            'global_role': JOB_ROLES[0][0],
            'user_roles': '[]',
            'parent_identifier': job1.identifier,
            'file_data': '[]'
        })
        job2 = Job.objects.get(pk=int(json.loads(str(response.content, encoding='utf8'))['job_id']))
        self.client.post('/jobs/ajax/fast_run_decision/', {'job_id': job1.pk})
        DecideJobs('service', 'service', CHUNKS1)
        self.client.post('/jobs/ajax/fast_run_decision/', {'job_id': job2.pk})
        DecideJobs('service', 'service', CHUNKS2)
        response = self.client.post('/reports/ajax/fill_compare_cache/', {'job1': job1.pk, 'job2': job2.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        try:
            comparison = CompareJobsInfo.objects.get(
                user__username='manager', root1__job_id=job1.pk, root2__job_id=job2.pk
            )
        except ObjectDoesNotExist:
            self.fail('Comparsion cache is empty')

        # 6 modules (1 module veridfied by 2 rules)
        self.assertEqual(len(CompareJobsCache.objects.filter(info=comparison)), 7)

        response = self.client.get(reverse('reports:comparison', args=[job1.pk, job2.pk]))
        self.assertEqual(response.status_code, 200)

        response = self.client.post('/reports/ajax/get_compare_jobs_data/', {
            'info_id': comparison.pk, 'verdict': '%s_%s' % (COMPARE_VERDICT[0][0], COMPARE_VERDICT[0][0])
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')

        response = self.client.get(reverse('jobs:comparison', args=[job1.pk, job2.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')

    def __get_report_id(self, name):
        r_id = '/' + name
        while r_id in self.ids_in_use:
            r_id = '/%s%s' % (name, random.randint(1, 100))
        self.ids_in_use.append(r_id)
        return r_id

    def __upload_start_report(self, name, parent, attrs=None):
        r_id = self.__get_report_id(name)
        report = {'id': r_id, 'type': 'start', 'parent id': parent, 'name': name}
        if attrs is not None:
            report['attrs'] = attrs
        response = self.service_client.post('/reports/upload/', {'report': json.dumps(report)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(ReportComponent.objects.filter(
            root__job_id=self.job.pk,
            identifier=self.job.identifier + r_id,
            parent__identifier=self.job.identifier + parent,
            component__name=name,
            finish_date=None
        )), 1)
        return r_id

    def __upload_finish_report(self, r_id):
        with open(os.path.join(ARCHIVE_PATH, 'report.tar.gz'), mode='rb') as fp:
            response = self.service_client.post('/reports/upload/', {
                'report': json.dumps({
                    'id': r_id, 'type': 'finish', 'resources': resources(),
                    'log': 'log.txt', 'desc': 'It does not matter'
                }), 'file': fp
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(ReportComponent.objects.filter(
            Q(root__job_id=self.job.pk, identifier=self.job.identifier + r_id) & ~Q(finish_date=None)
        )), 1)

    def __upload_attrs_report(self, r_id, attrs):
        response = self.service_client.post('/reports/upload/', {
            'report': json.dumps({'id': r_id, 'type': 'attrs', 'attrs': attrs})
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

    def __upload_data_report(self, r_id, data=None):
        if data is None:
            data = {"newdata": str(random.randint(0, 100))}

        response = self.service_client.post('/reports/upload/', {
            'report': json.dumps({'id': r_id, 'type': 'data', 'data': json.dumps(data)})
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

    def __upload_verification_report(self, name, parent, attrs=None):
        r_id = self.__get_report_id(name)
        report = {
            'id': r_id, 'type': 'verification', 'parent id': parent, 'name': name,
            'resources': resources(), 'data': '{"description": "%s"}' % r_id, 'log': 'log.txt'
        }
        if isinstance(attrs, list):
            report['attrs'] = attrs

        with open(os.path.join(ARCHIVE_PATH, 'report.tar.gz'), mode='rb') as fp:
            response = self.service_client.post('/reports/upload/', {'report': json.dumps(report), 'file': fp})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(ReportComponent.objects.filter(
            Q(root__job_id=self.job.pk, identifier=self.job.identifier + r_id,
              parent__identifier=self.job.identifier + parent, component__name=name) & ~Q(finish_date=None)
        )), 1)
        return r_id

    def __upload_unknown_report(self, parent, archive):
        r_id = self.__get_report_id('unknown')
        report = {'id': r_id, 'type': 'unknown', 'parent id': parent, 'problem desc': 'problem description.txt'}
        with open(os.path.join(ARCHIVE_PATH, archive), mode='rb') as fp:
            response = self.service_client.post('/reports/upload/', {'report': json.dumps(report), 'file': fp})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(ReportUnknown.objects.filter(
            root__job_id=self.job.pk, identifier=self.job.identifier + r_id,
            parent__identifier=self.job.identifier + parent
        )), 1)

    def __upload_safe_report(self, parent, attrs, archive):
        r_id = self.__get_report_id('safe')
        with open(os.path.join(ARCHIVE_PATH, archive), mode='rb') as fp:
            response = self.service_client.post('/reports/upload/', {'report': json.dumps({
                'id': r_id, 'type': 'safe', 'parent id': parent, 'proof': 'proof.txt', 'attrs': attrs
            }), 'file': fp})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(ReportSafe.objects.filter(
            root__job_id=self.job.pk, identifier=self.job.identifier + r_id,
            parent__identifier=self.job.identifier + parent
        )), 1)

    def __upload_unsafe_report(self, parent, attrs, archive):
        r_id = self.__get_report_id('unsafe')
        with open(os.path.join(ARCHIVE_PATH, archive), mode='rb') as fp:
            response = self.service_client.post('/reports/upload/', {'report': json.dumps({
                'id': r_id, 'type': 'unsafe', 'parent id': parent,
                'error trace': 'unsafe-error-trace.graphml', 'attrs': attrs
            }), 'file': fp})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(ReportUnsafe.objects.filter(
            root__job_id=self.job.pk, identifier=self.job.identifier + r_id,
            parent__identifier=self.job.identifier + parent
        )), 1)

    def __decide_job(self):
        sch_data = {
            'tasks': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'task errors': {},
            'task descriptions': {},
            'task solutions': {},
            'jobs': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'job errors': {},
            'job configurations': {}
        }
        response = self.service_client.post('/service/get_jobs_and_tasks/', {
            'jobs and tasks status': json.dumps(sch_data)
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('jobs and tasks status', res)
        res_data = json.loads(res['jobs and tasks status'])
        try:
            self.assertIn(self.job.identifier, res_data['jobs']['pending'])
            self.assertIn(self.job.identifier, res_data['job configurations'])
        except KeyError:
            self.fail('Wrong result format')

        response = self.service_client.post('/jobs/decide_job/', {'report': json.dumps({
            'type': 'start', 'id': '/', 'attrs': [{'PSI version': 'stage-2-1k123j13'}], 'comp': COMPUTER
        }), 'job format': 1})
        self.assertEqual(response['Content-Type'], 'application/x-tar-gz')
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[2][0])

        core_data = None
        if self.job.type == JOB_CLASSES[0][0]:
            core_data = {
                'module1': {
                    'ideal verdict': 'safe',
                    'verification status': 'unsafe',
                    'comment': 'This is comment for module1'
                },
                'module2': {
                    'ideal verdict': 'safe',
                    'verification status': 'safe'
                },
                'module3': {
                    'ideal verdict': 'unsafe',
                    'verification status': 'unsafe',
                    'comment': 'This is comment for module3'
                },
                'module4': {
                    'ideal verdict': 'unsafe',
                    'verification status': 'unknown'
                }
            }
        elif self.job.type == JOB_CLASSES[3][0]:
            core_data = {
                'module1': {
                    'before fix': {'verification status': 'unsafe', 'comment': 'Comment for module1 before fix'},
                    'after fix': {'verification status': 'unsafe', 'comment': 'Comment for module1 after fix'},
                },
                'module2': {
                    'before fix': {'verification status': 'safe'},
                    'after fix': {'verification status': 'unsafe', 'comment': 'Comment for module2 after fix'},
                },
                'module3': {
                    'before fix': {'verification status': 'unsafe', 'comment': 'Comment for module3 before fix'},
                    'after fix': {'verification status': 'safe'},
                },
                'module4': {
                    'before fix': {'verification status': 'unsafe'}, 'after fix': {'verification status': 'unknown'},
                }
            }

        self.__upload_data_report('/', core_data)

        lkbce = self.__upload_start_report('LKBCE', '/')
        self.__upload_attrs_report(lkbce, [LINUX_ATTR])
        self.__upload_finish_report(lkbce)

        lkvog = self.__upload_start_report('LKVOG', '/', [LKVOG_ATTR])
        self.__upload_finish_report(lkvog)

        avtg = self.__upload_start_report('AVTG', '/', [LINUX_ATTR])
        vtg = self.__upload_start_report('VTG', '/', [LINUX_ATTR, LKVOG_ATTR])

        for chunk in CHUNKS1:
            sa = self.__upload_start_report('SA', avtg, chunk['attrs'])
            self.__upload_data_report(sa)
            self.__upload_finish_report(sa)
            if 'fail' in chunk and chunk['fail'] == 'SA':
                self.__upload_unknown_report(sa, chunk['unknown'])
                continue
            emg = self.__upload_start_report('EMG', avtg, chunk['attrs'])
            self.__upload_finish_report(emg)
            if 'fail' in chunk and chunk['fail'] == 'EMG':
                self.__upload_unknown_report(emg, chunk['unknown'])
                continue
            rsg = self.__upload_start_report('RSG', avtg, chunk['attrs'])
            self.__upload_finish_report(rsg)
            if 'fail' in chunk and chunk['fail'] == 'RSG':
                self.__upload_unknown_report(rsg, chunk['unknown'])
                continue
            abkm = self.__upload_start_report('ABKM', avtg, chunk['attrs'])
            if 'fail' in chunk and chunk['fail'] == 'ABKM':
                self.__upload_finish_report(abkm)
                self.__upload_unknown_report(sa, chunk['unknown'])
                continue
            cnt = 1
            if 'safe' in chunk:
                tool = self.__upload_verification_report(chunk['tool'], abkm, chunk['tool_attrs'])
                self.__upload_safe_report(tool, [], chunk['safe'])
            elif 'unsafes' in chunk:
                for u_arch in chunk['unsafes']:
                    tool = self.__upload_verification_report(chunk['tool'], abkm, chunk['tool_attrs'])
                    self.__upload_unsafe_report(tool, [{'entry point': 'any_function_%s' % cnt}], u_arch)
                    cnt += 1
            if 'unknown' in chunk and 'safe' not in chunk:
                tool = self.__upload_verification_report(chunk['tool'], abkm, chunk['tool_attrs'])
                self.__upload_unknown_report(tool, chunk['unknown'])
            self.__upload_finish_report(abkm)

        self.__upload_finish_report(avtg)
        self.__upload_finish_report(vtg)
        self.__upload_finish_report('/')

        new_sch_data = sch_data.copy()
        new_sch_data['jobs']['finished'].append(self.job.identifier)
        response = self.service_client.post('/service/get_jobs_and_tasks/', {
            'jobs and tasks status': json.dumps(new_sch_data)
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[3][0])


class DecideJobs(object):
    def __init__(self, username, password, reports_data):
        self.service = Client()
        self.username = username
        self.password = password
        self.reports_data = reports_data
        self.ids_in_use = []
        self.__upload_reports()

    def __upload_reports(self):
        scheduler = Client()
        scheduler.post('/users/service_signin/', {
            'username': self.username, 'password': self.password, 'scheduler': SCHEDULER_TYPE[0][1]
        })
        sch_data = {
            'tasks': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'task errors': {}, 'task descriptions': {}, 'task solutions': {},
            'jobs': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'job errors': {}, 'job configurations': {}
        }
        response = scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data)})
        res_data = json.loads(json.loads(str(response.content, encoding='utf8'))['jobs and tasks status'])

        for job_identifier in res_data['jobs']['pending']:
            self.service.post('/users/service_signin/', {
                'username': self.username, 'password': self.password, 'job identifier': job_identifier
            })
            self.__decide_job(job_identifier)
            self.service.post('/users/service_signout/')
            sch_data['jobs']['finished'].append(job_identifier)
        scheduler.post('/service/get_jobs_and_tasks/', {'jobs and tasks status': json.dumps(sch_data)})
        scheduler.post('/users/service_signout/')

    def __get_report_id(self, name):
        r_id = '/' + name
        while r_id in self.ids_in_use:
            r_id = '/%s%s' % (name, random.randint(1, 100))
        self.ids_in_use.append(r_id)
        return r_id

    def __upload_start_report(self, name, parent, attrs=None):
        r_id = self.__get_report_id(name)
        report = {'id': r_id, 'type': 'start', 'parent id': parent, 'name': name}
        if attrs is not None:
            report['attrs'] = attrs
        self.service.post('/reports/upload/', {'report': json.dumps(report)})
        return r_id

    def __upload_finish_report(self, r_id):
        with open(os.path.join(ARCHIVE_PATH, 'report.tar.gz'), mode='rb') as fp:
            self.service.post('/reports/upload/', {
                'report': json.dumps({
                    'id': r_id, 'type': 'finish', 'resources': resources(),
                    'log': 'log.txt', 'desc': 'It does not matter'
                }), 'file': fp
            })

    def __upload_attrs_report(self, r_id, attrs):
        self.service.post('/reports/upload/', {
            'report': json.dumps({'id': r_id, 'type': 'attrs', 'attrs': attrs})
        })

    def __upload_data_report(self, r_id, data=None):
        if data is None:
            data = {"newdata": str(random.randint(0, 100))}
        self.service.post('/reports/upload/', {
            'report': json.dumps({'id': r_id, 'type': 'data', 'data': json.dumps(data)})
        })

    def __upload_verification_report(self, name, parent, attrs=None):
        r_id = self.__get_report_id(name)
        report = {
            'id': r_id, 'type': 'verification', 'parent id': parent, 'name': name,
            'resources': resources(), 'data': '{"description": "%s"}' % r_id, 'log': 'log.txt'
        }
        if isinstance(attrs, list):
            report['attrs'] = attrs
        if random.randint(1, 10) > 4:
            with open(os.path.join(ARCHIVE_PATH, 'report.tar.gz'), mode='rb') as fp:
                self.service.post('/reports/upload/', {'report': json.dumps(report), 'file': fp})
        else:
            report['log'] = None
            self.service.post('/reports/upload/', {'report': json.dumps(report)})
        return r_id

    def __upload_unknown_report(self, parent, archive):
        r_id = self.__get_report_id('unknown')
        report = {'id': r_id, 'type': 'unknown', 'parent id': parent, 'problem desc': 'problem description.txt'}
        with open(os.path.join(ARCHIVE_PATH, archive), mode='rb') as fp:
            self.service.post('/reports/upload/', {'report': json.dumps(report), 'file': fp})

    def __upload_safe_report(self, parent, attrs, archive):
        r_id = self.__get_report_id('safe')
        with open(os.path.join(ARCHIVE_PATH, archive), mode='rb') as fp:
            self.service.post('/reports/upload/', {'report': json.dumps({
                'id': r_id, 'type': 'safe', 'parent id': parent, 'proof': 'proof.txt', 'attrs': attrs
            }), 'file': fp})

    def __upload_empty_safe_report(self, parent, attrs):
        self.service.post('/reports/upload/', {'report': json.dumps({
            'id': self.__get_report_id('safe'), 'type': 'safe', 'parent id': parent, 'proof': None, 'attrs': attrs
        })})

    def __upload_unsafe_report(self, parent, attrs, archive):
        r_id = self.__get_report_id('unsafe')
        with open(os.path.join(ARCHIVE_PATH, archive), mode='rb') as fp:
            self.service.post('/reports/upload/', {'report': json.dumps({
                'id': r_id, 'type': 'unsafe', 'parent id': parent,
                'error trace': 'unsafe-error-trace.graphml', 'attrs': attrs
            }), 'file': fp})

    def __decide_job(self, job_identifier):
        self.service.post('/jobs/decide_job/', {'report': json.dumps({
            'type': 'start', 'id': '/', 'attrs': [{'PSI version': 'version-1'}], 'comp': COMPUTER
        }), 'job format': 1})

        core_data = None
        job = Job.objects.get(identifier=job_identifier)
        if job.type == JOB_CLASSES[0][0]:
            core_data = {
                'module1': {
                    'ideal verdict': 'safe',
                    'verification status': 'unsafe',
                    'comment': 'This is comment for module1'
                },
                'module2': {
                    'ideal verdict': 'safe',
                    'verification status': 'safe'
                },
                'module3': {
                    'ideal verdict': 'unsafe',
                    'verification status': 'unsafe',
                    'comment': 'This is comment for module3'
                },
                'module4': {
                    'ideal verdict': 'unsafe',
                    'verification status': 'unknown'
                }
            }
        elif job.type == JOB_CLASSES[3][0]:
            core_data = {
                'module1': {
                    'before fix': {'verification status': 'unsafe', 'comment': 'Comment for module1 before fix'},
                    'after fix': {'verification status': 'unsafe', 'comment': 'Comment for module1 after fix'},
                },
                'module2': {
                    'before fix': {'verification status': 'safe'},
                    'after fix': {'verification status': 'unsafe', 'comment': 'Comment for module2 after fix'},
                },
                'module3': {
                    'before fix': {'verification status': 'unsafe', 'comment': 'Comment for module3 before fix'},
                    'after fix': {'verification status': 'safe'},
                },
                'module4': {
                    'before fix': {'verification status': 'unsafe'}, 'after fix': {'verification status': 'unknown'},
                }
            }

        self.__upload_data_report('/', core_data)

        lkbce = self.__upload_start_report('LKBCE', '/')
        self.__upload_attrs_report(lkbce, [LINUX_ATTR])
        self.__upload_finish_report(lkbce)

        lkvog = self.__upload_start_report('LKVOG', '/', [LKVOG_ATTR])
        self.__upload_finish_report(lkvog)

        avtg = self.__upload_start_report('AVTG', '/', [LINUX_ATTR])
        vtg = self.__upload_start_report('VTG', '/', [LINUX_ATTR, LKVOG_ATTR])

        for chunk in self.reports_data:
            if job.type == JOB_CLASSES[3][0]:
                chunk['attrs']['Commit'] = 'HEAD'
            sa = self.__upload_start_report('SA', avtg, chunk['attrs'])
            self.__upload_data_report(sa)
            self.__upload_finish_report(sa)
            if 'fail' in chunk and chunk['fail'] == 'SA':
                self.__upload_unknown_report(sa, chunk['unknown'])
                continue
            emg = self.__upload_start_report('EMG', avtg, chunk['attrs'])
            self.__upload_finish_report(emg)
            if 'fail' in chunk and chunk['fail'] == 'EMG':
                self.__upload_unknown_report(emg, chunk['unknown'])
                continue
            rsg = self.__upload_start_report('RSG', avtg, chunk['attrs'])
            self.__upload_finish_report(rsg)
            if 'fail' in chunk and chunk['fail'] == 'RSG':
                self.__upload_unknown_report(rsg, chunk['unknown'])
                continue
            abkm = self.__upload_start_report('ABKM', avtg, chunk['attrs'])
            if 'fail' in chunk and chunk['fail'] == 'ABKM':
                self.__upload_finish_report(abkm)
                self.__upload_unknown_report(sa, chunk['unknown'])
                continue
            cnt = 1
            if 'safe' in chunk:
                tool = self.__upload_verification_report(chunk['tool'], abkm, chunk['tool_attrs'])
                self.__upload_safe_report(tool, [], chunk['safe'])
                # self.__upload_empty_safe_report(tool, [])
            elif 'unsafes' in chunk:
                for u_arch in chunk['unsafes']:
                    tool = self.__upload_verification_report(chunk['tool'], abkm, chunk['tool_attrs'])
                    self.__upload_unsafe_report(tool, [{'entry point': 'any_function_%s' % cnt}], u_arch)
                    cnt += 1
            if 'unknown' in chunk and 'safe' not in chunk:
                tool = self.__upload_verification_report(chunk['tool'], abkm, chunk['tool_attrs'])
                self.__upload_unknown_report(tool, chunk['unknown'])
            self.__upload_finish_report(abkm)

        self.__upload_finish_report(avtg)
        self.__upload_finish_report(vtg)
        self.__upload_finish_report('/')
