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
import re
import json
from multiprocessing import Process, Pipe
import random
import requests
import time
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.test import Client
from django.urls import reverse

from bridge.vars import SCHEDULER_TYPE, JOB_ROLES
from bridge.utils import KleverTestCase, logger, RMQConnect


LINUX_ATTR = {'name': 'Linux kernel', 'value': [
    {'name': 'Version', 'value': '3.5.0'},
    {'name': 'Architecture', 'value': 'x86_64'},
    {'name': 'Configuration', 'value': 'allmodconfig'}
]}
LKVOG_ATTR = {'name': 'LKVOG strategy', 'value': [{'name': 'Name', 'value': 'separate modules'}]}
COMPUTER = {
    'identifier': 'hellwig.intra.ispras.ru',
    'display': 'hellwig.intra.ispras.ru',
    'data': [
        {"node name": "hellwig.intra.ispras.ru"},
        {"CPU model": "Intel(R) Core(TM) i7-3770 CPU @ 3.40GHz"},
        {"number of CPU cores": 8},
        {"memory size": 16808734720},
        {"Linux kernel version": "3.16.7-29-default"},
        {"architecture": "x86_64"}
    ]
}

# Only components ['VTGW', 'ASE', 'EMG', 'FVTP', 'RSG', 'SA', 'TR', 'Weaver', 'RP'] can be "failed"
SJC_1 = [
    {
        'requirement': 'linux:mutex',
        'chunks': [
            {
                'module': 'drivers/usb/core/usb1.ko',
                'tool': 'BLAST 2.7.2', 'log': True,
                'additional_sources': 'sources12.zip',
                'unsafes': ['unsafe1.zip', 'unsafe2.zip'],
                'unknown': 'unknown2.zip'
            },
            {
                'module': 'drivers/usb/core/usb2.ko',
                'tool': 'CPAchecker', 'log': False,
                'additional_sources': 'sources3.zip',
                'unsafes': ['unsafe3.zip']
            },
            {
                'module': 'drivers/usb/core/usb3.ko',
                'tool': 'CPAchecker', 'log': False,
                'safe': 'safe.zip'
            },
            {
                'module': 'drivers/usb/core/usb4.ko',
                'tool': 'CPAchecker', 'log': True,
                'unknown': 'unknown0.zip'
            }
        ]
    },
    {
        'requirement': 'linux:rule1',
        'chunks': [
            {
                'module': 'drivers/usb/core/usb1.ko',
                'tool': 'BLAST 2.7.2', 'log': True,
                'safe': 'safe.zip'
            },
            {
                'module': 'drivers/usb/core/usb2.ko',
                'tool': 'CPAchecker', 'log': False,
                'additional_sources': 'sources4.zip',
                'unsafes': ['unsafe4.zip']
            },
            {
                'module': 'drivers/usb/core/usb3.ko',
                'tool': 'CPAchecker', 'log': False,
                'additional_sources': 'sources5.zip',
                'unsafes': ['unsafe5.zip']
            },
            {
                'module': 'drivers/usb/core/usb4.ko',
                'tool': 'CPAchecker', 'log': True,
                'additional_sources': 'sources13.zip',
                'coverage': 'coverage13.zip',
                'safe': 'safe.zip'
            },
            {
                'module': 'drivers/usb/core/usb5.ko',
                'tool': 'CPAchecker', 'log': False,
                'additional_sources': 'sources6.zip',
                'unsafes': ['unsafe6.zip']
            }
        ]
    },
    {
        'requirement': 'linux:rule2',
        'chunks': [
            {
                'module': 'drivers/usb/core/usb6.ko',
                'tool': 'CPAchecker', 'log': False,
                'safe': 'safe.zip'
            },
            {
                'module': 'drivers/usb/core/usb7.ko',
                'tool': 'CPAchecker', 'log': True,
                'additional_sources': 'sources10.zip',
                'unsafes': ['unsafe10.zip']
            }
        ]
    }
]

SJC_2 = [
    {
        'requirement': 'linux:mutex',
        'chunks': [
            {
                'module': 'drivers/usb/core/usb2.ko',
                'tool': 'CPAchecker', 'log': True,
                'additional_sources': 'sources14.zip',
                'coverage': 'coverage14.zip',
                'safe': 'safe.zip'
            }
        ]
    }
]

SJC_3 = [
    {
        'requirement': 'linux:mutex',
        'chunks': [
            {
                'module': 'drivers/usb/core/usb0.ko',
                'tool': 'CPAchecker', 'log': True,
                'additional_sources': 'sources1.zip',
                'safe': 'safe.zip'
            },
            {
                'requirement': 'linux:mutex',
                'module': 'drivers/usb/core/usb1.ko',
                'tool': 'BLAST 2.7.2', 'log': False,
                'additional_sources': 'sources12.zip',
                'unsafes': ['unsafe1.zip', 'unsafe2.zip'],
                'unknown': 'unknown2.zip'
            },
            {
                'requirement': 'linux:mutex',
                'module': 'drivers/usb/core/usb2.ko',
                'tool': 'CPAchecker', 'log': True,
                'additional_sources': 'sources3.zip',
                'unsafes': ['unsafe3.zip']
            },
            {
                'requirement': 'linux:mutex',
                'module': 'drivers/usb/core/usb3.ko',
                'tool': 'CPAchecker', 'log': False,
                'safe': 'safe.zip'
            },
            {
                'requirement': 'linux:mutex',
                'module': 'drivers/usb/core/usb4.ko',
                'tool': 'CPAchecker', 'log': True,
                'unknown': 'unknown0.zip'
            },
            {
                'requirement': 'linux:mutex',
                'module': 'drivers/usb/core/usb5.ko',
                'fail': 'RP',
                'unknown': 'unknown3.zip'
            }
        ]
    }
]

SJC_4 = [
    {
        'requirement': 'linux:alloc:irq',
        'chunks': [
            {
                'module': 'drivers/usb/core/usb1.ko',
                'tool': 'BLAST 2.7.2', 'log': True,
                'additional_sources': 'sources12.zip',
                'unsafes': ['unsafe1.zip', 'unsafe2.zip'],
                'unknown': 'unknown2.zip'
            },
            {
                'module': 'drivers/usb/core/usb2.ko',
                'tool': 'CPAchecker', 'log': False,
                'additional_sources': 'sources3.zip',
                'unsafes': ['unsafe3.zip']
            },
            {
                'module': 'drivers/usb/core/usb3.ko',
                'tool': 'CPAchecker', 'log': False,
                'safe': 'safe.zip'
            },
            {
                'module': 'drivers/usb/core/usb4.ko',
                'tool': 'CPAchecker', 'log': True,
                'unknown': 'unknown0.zip'
            }
        ]
    },
    {
        'requirement': 'linux:arch:io',
        'chunks': [
            {
                'module': 'drivers/usb/core/usb1.ko',
                'tool': 'BLAST 2.7.2', 'log': True,
                'safe': 'safe.zip'
            },
            {
                'module': 'drivers/usb/core/usb2.ko',
                'tool': 'CPAchecker', 'log': False,
                'additional_sources': 'sources4.zip',
                'unsafes': ['unsafe4.zip']
            },
            {
                'module': 'drivers/usb/core/usb3.ko',
                'tool': 'CPAchecker', 'log': False,
                'additional_sources': 'sources5.zip',
                'unsafes': ['unsafe5.zip']
            },
            {
                'module': 'drivers/usb/core/usb4.ko',
                'tool': 'CPAchecker', 'log': True,
                'additional_sources': 'sources13.zip',
                'coverage': 'coverage13.zip',
                'safe': 'safe.zip'
            },
            {
                'module': 'drivers/usb/core/usb5.ko',
                'tool': 'CPAchecker', 'log': False,
                'additional_sources': 'sources6.zip',
                'unsafes': ['unsafe6.zip']
            }
        ]
    },
    {
        'requirement': 'linux:alloc:usb lock',
        'chunks': [
            {
                'module': 'drivers/usb/core/usb6.ko',
                'tool': 'CPAchecker', 'log': False,
                'safe': 'safe.zip'
            },
            {
                'module': 'drivers/usb/core/usb7.ko',
                'tool': 'CPAchecker', 'log': True,
                'additional_sources': 'sources10.zip',
                'unsafes': ['unsafe10.zip']
            }
        ]
    }
]

NSJC_1 = [
    {
        'requirement': 'linux:mutex',
        'module': 'drivers/usb/core/usb1.ko',
        'tool': 'BLAST 2.7.2', 'log': False,
        'additional_sources': 'sources12.zip',
        'unsafes': ['unsafe1.zip', 'unsafe2.zip'],
        'unknown': 'unknown2.zip'
    },
    {
        'requirement': 'linux:mutex',
        'module': 'drivers/usb/core/usb2.ko',
        'tool': 'CPAchecker', 'log': True,
        'additional_sources': 'sources3.zip',
        'unsafes': ['unsafe3.zip']
    },
    {
        'requirement': 'linux:mutex',
        'module': 'drivers/usb/core/usb3.ko',
        'tool': 'CPAchecker', 'log': False,
        'safe': 'safe.zip'
    },
    {
        'requirement': 'linux:mutex',
        'module': 'drivers/usb/core/usb4.ko',
        'tool': 'CPAchecker', 'log': True,
        'unknown': 'unknown0.zip'
    }
]

NSJC_2 = [
    {
        'requirement': 'linux:mutex',
        'module': 'drivers/usb/core/usb2.ko',
        'tool': 'CPAchecker', 'log': True,
        'unsafes': ['unsafe11.zip']
    }
]

NSJC_3 = [
    {
        'requirement': 'linux:mutex',
        'module': 'drivers/usb/core/usb3.ko',
        'tool': 'CPAchecker', 'log': False,
        'safe': 'safe.zip'
    },
    {
        'requirement': 'linux:mutex',
        'module': 'drivers/usb/core/usb4.ko',
        'tool': 'CPAchecker', 'log': True,
        'additional_sources': 'sources2.zip',
        'unknown': 'unknown0.zip'
    },
    {
        'requirement': 'linux:mutex',
        'module': 'drivers/usb/core/usb5.ko',
        'fail': 'ASE',  # No verdicts will be uploaded as component failed before it
        'unknown': 'unknown3.zip'
    }
]

ARCHIVE_PATH = os.path.join(settings.BASE_DIR, 'tests', 'reports')


def resources():
    return {
        'cpu_time': random.randint(100, 10000),
        'memory': random.randint(10**7, 10**9),
        'wall_time': random.randint(100, 10000)
    }


class DecisionError(Exception):
    pass


class TestReports(KleverTestCase):
    def setUp(self):
        super().setUp()
        self.service_client = Client()
        User.objects.create_superuser('superuser', '', 'top_secret')
        populate_users(
            manager={'username': 'manager', 'password': 'manager'},
            service={'username': 'service', 'password': 'service'}
        )
        self.client.post(reverse('users:login'), {'username': 'manager', 'password': 'manager'})
        self.client.post(reverse('population'))
        self.job_archive = 'test_job_archive.zip'

    def test_reports(self):
        self.ids_in_use = []
        self.cmp_stack = []
        self.job = Job.objects.order_by('parent').first()
        if self.job is None:
            self.fail('Jobs are not populated')

        # Run decision with default configuration
        self.client.post('/jobs/run_decision/%s/' % self.job.pk, {'mode': 'default', 'conf_name': 'development'})

        # Service sign in and check session parameters
        response = self.service_client.post('/users/service_signin/', {
            'username': 'service', 'password': 'service',
            'job identifier': self.job.identifier, 'scheduler': SCHEDULER_TYPE[0][1]
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
        self.assertEqual(self.service_client.session.get('scheduler'), SCHEDULER_TYPE[0][0])
        self.assertEqual(self.service_client.session.get('job id'), self.job.pk)

        # Decide the job
        self.__decide_job(SJC_1)

        try:
            main_report = ReportComponent.objects.get(parent=None, root__job_id=self.job.pk)
        except ObjectDoesNotExist:
            self.fail("The job decision didn't create core report")

        response = self.client.get(reverse('reports:component', args=[main_report.pk]))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse('reports:unsafes', args=[main_report.pk]))
        if ReportUnsafe.objects.count() == 1:
            self.assertRedirects(response, reverse('reports:unsafe', args=[ReportUnsafe.objects.first().trace_id]))
        else:
            self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('reports:safes', args=[main_report.pk]))
        if ReportSafe.objects.count() == 1:
            self.assertRedirects(response, reverse('reports:safe', args=[ReportSafe.objects.first().id]))
        else:
            self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('reports:unknowns', args=[main_report.pk]))
        if ReportUnknown.objects.count() == 1:
            self.assertRedirects(response, reverse('reports:unknown', args=[ReportUnknown.objects.first().id]))
        else:
            self.assertEqual(response.status_code, 200)

        for report in ReportComponent.objects.filter(~Q(parent=None) & Q(root__job_id=self.job.pk)):
            response = self.client.get(reverse('reports:component', args=[report.pk]))
            self.assertEqual(response.status_code, 200)

        for unsafe in ReportUnsafe.objects.all():
            response = self.client.get(reverse('reports:unsafe', args=[unsafe.trace_id]))
            self.assertEqual(response.status_code, 200)
            response = self.client.get(reverse('reports:unsafe_fullscreen', args=[unsafe.trace_id]))
            self.assertEqual(response.status_code, 200)

        for report in ReportUnknown.objects.all():
            response = self.client.get(reverse('reports:unknown', args=[report.pk]))
            self.assertEqual(response.status_code, 200)

        for report in ReportSafe.objects.all():
            response = self.client.get(reverse('reports:safe', args=[report.pk]))
            self.assertEqual(response.status_code, 200)

        ver_report = ReportComponent.objects.filter(verification=True).first()
        response = self.client.get(reverse('reports:download_files', args=[ver_report.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')

        unsafe = ReportUnsafe.objects.first()
        response = self.client.get(reverse('reports:download_error_trace', args=[unsafe.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        mem = BytesIO()
        for chunk in response.streaming_content:
            mem.write(chunk)
        mem.seek(0)
        first_fname = json.loads(str(mem.read().decode('utf8')))['files'][0]

        response = self.client.post('/reports/get_source/%s/' % unsafe.pk, {'file_name': first_fname})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        response = self.client.get('/reports/logcontent/%s/' % main_report.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('content', res)

        response = self.client.get(reverse('reports:log', args=[main_report.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')

        # Get decision results
        response = self.client.get('/jobs/decision_results_json/%s/' % self.job.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('data', res)

        # Collapse job
        response = self.client.post('/jobs/collapse_reports/%s/' % self.job.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Test verifier input files
        report = ReportComponent.objects.exclude(root__job_id=self.job.pk, verifier_files='').first()
        self.assertIsNotNone(report)

        response = self.client.post(reverse('jobs:download_verifier_input_files', args=[self.job.pk]),
                                    {'filters': json.dumps(['u', 's'])})
        self.assertEqual(response.status_code, 200)
        self.assertIn(response['Content-Type'], {'application/x-zip-compressed', 'application/zip'})

        response = self.client.get(reverse('reports:download_files', args=[report.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(response['Content-Type'], {'application/x-zip-compressed', 'application/zip'})

        # Clear verifier input files
        response = self.client.post('/reports/clear_verifier_files/%s/' % self.job.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(ReportComponent.objects.filter(root=self.job.reportroot, verification=True)
                         .exclude(verifier_files='').count(), 0)

    def test_coverage(self):
        self.job = Job.objects.order_by('parent').first()
        if self.job is None:
            self.fail('Jobs are not populated')
        self.client.post('/jobs/run_decision/%s/' % self.job.pk, {'mode': 'default', 'conf_name': 'development'})

        DecideJobs('service', 'service', SJC_1, with_full_coverage=True)

        # Test coverage pages for verification report
        report = ReportComponent.objects.filter(verification=True, covnum__gt=0).first()
        self.assertIsNotNone(report)
        response = self.client.get(reverse('reports:coverage', args=[report.id]))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('reports:coverage_light', args=[report.id]))
        self.assertEqual(response.status_code, 200)

        # Test downloading coverage
        carch = CoverageArchive.objects.filter(report=report).first()
        self.assertIsNotNone(carch)
        response = self.client.get(reverse('reports:download_coverage', args=[carch.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(response['Content-Type'], {'application/x-zip-compressed', 'application/zip'})

        # Test coverage pages for non-verification report
        report = ReportComponent.objects.filter(verification=False, covnum__gt=0).first()
        self.assertIsNotNone(report)
        response = self.client.get(reverse('reports:coverage', args=[report.id]))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('reports:coverage_light', args=[report.id]))
        self.assertEqual(response.status_code, 200)

        # Get source code for coverage
        cfile = CoverageFile.objects.filter(archive=carch).first()
        self.assertIsNotNone(cfile)
        # Get with data
        response = self.client.post('/reports/get-coverage-src/%s/' % carch.id,
                                    {'filename': cfile.name, 'with_data': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(set(res), {'content', 'data', 'legend'})
        # Get without data
        response = self.client.post('/reports/get-coverage-src/%s/' % carch.id,
                                    {'filename': cfile.name, 'with_data': '0'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(set(res), {'content', 'data', 'legend'})

    def test_comparison(self):
        try:
            job1 = Job.objects.filter(parent=None)[0]
        except IndexError:
            job1 = Job.objects.filter()[0]

        response = self.client.post(reverse('jobs:form', args=[job1.pk, 'copy']), {
            'name': 'New job title', 'description': 'Description of new job',
            'global_role': JOB_ROLES[0][0], 'user_roles': '[]',
            'parent': job1.identifier, 'file_data': '[{"type": "root", "text": "Files", "children": []}]'
        })
        job2 = Job.objects.get(pk=int(json.loads(str(response.content, encoding='utf8'))['job_id']))
        self.client.post('/jobs/run_decision/%s/' % job1.pk, {'mode': 'default', 'conf_name': 'development'})
        DecideJobs('service', 'service', SJC_1)
        self.client.post('/jobs/run_decision/%s/' % job2.pk, {'mode': 'default', 'conf_name': 'development'})
        DecideJobs('service', 'service', SJC_2)

        response = self.client.post('/jobs/check_compare_access/', {'job1': job1.pk, 'job2': job2.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Filling comparison cache
        response = self.client.post('/reports/fill_compare_cache/%s/%s/' % (job1.pk, job2.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        try:
            comparison = CompareJobsInfo.objects.get(
                user__username='manager', root1__job_id=job1.pk, root2__job_id=job2.pk
            )
        except ObjectDoesNotExist:
            self.fail('Comparsion cache is empty')

        # Comparison page
        response = self.client.get(reverse('reports:comparison', args=[job1.pk, job2.pk]))
        self.assertEqual(response.status_code, 200)

        compare_cache = CompareJobsCache.objects.filter(info__root1__job=job1, info__root2__job=job2).first()
        self.assertIsNotNone(compare_cache)
        response = self.client.post('/reports/get_compare_jobs_data/%s/' % comparison.pk, {
            'verdict': '%s_%s' % (compare_cache.verdict1, compare_cache.verdict2)
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')

        response = self.client.get(reverse('jobs:comparison', args=[job1.pk, job2.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')

    def test_upload_reports(self):
        self.job = Job.objects.order_by('parent').first()
        if self.job is None:
            self.fail('Jobs are not populated')
        presets_dir = os.path.join(settings.BASE_DIR, 'reports', 'test_files', 'decisions')
        for archname in [os.path.join(presets_dir, x) for x in os.listdir(presets_dir)]:
            with open(archname, mode='rb') as fp:
                response = self.client.post('/jobs/upload_reports/%s/' % self.job.pk, {'archive': fp})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/json')
            self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

    def test_upload_decided_job(self):
        job = Job.objects.first()
        self.assertIsNotNone(job)
        self.client.post('/jobs/run_decision/%s/' % job.pk, {'mode': 'default', 'conf_name': 'development'})

        # This class uploads attrs data for verification reports
        DecideJobs('service', 'service', SJC_1)

        # Test attr data
        attrs = ReportAttr.objects.filter(report__root=job.reportroot).exclude(data=None)
        self.assertGreater(attrs.count(), 0, 'There are no attributes with data')
        attr_with_data = attrs.first()

        # Test download attr data file
        response = self.client.get('/reports/attrdata/%s/' % attr_with_data.pk)
        self.assertEqual(response.status_code, 200)

        # Test content of attr data file
        response = self.client.get('/reports/attrdata-content/%s/' % attr_with_data.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('content', res)

        # Download decided job
        response = self.client.get('/jobs/downloadjob/%s/' % job.pk)
        self.assertEqual(response.status_code, 200)
        with open(os.path.join(settings.MEDIA_ROOT, self.job_archive), mode='wb') as fp:
            for content in response.streaming_content:
                fp.write(content)

        # Remove decided job
        response = self.client.post('/jobs/api/%s/remove/' % job.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

        # Get parent for uploading
        if job.parent is None:
            parent = Job.objects.first()
            self.assertIsNotNone(parent)
        else:
            parent = Job.objects.get(id=job.parent_id)

        # Upload downloaded job
        with open(os.path.join(settings.MEDIA_ROOT, self.job_archive), mode='rb') as fp:
            response = self.client.post('/jobs/upload_jobs/%s/' % parent.identifier, {'file': fp})
            fp.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertJSONEqual(str(response.content, encoding='utf8'), '{}')
        try:
            Job.objects.get(parent=parent, identifier=job.identifier)
        except ObjectDoesNotExist:
            self.fail('The job was not found after upload')

    def __get_report_id(self, name):
        r_id = '/' + name
        while r_id in self.ids_in_use:
            r_id = '/%s%s' % (name, random.randint(1, 100))
        self.ids_in_use.append(r_id)
        return r_id

    def __upload_start_report(self, name, parent, attrs=None, failed=False):
        r_id = self.__get_report_id(name)
        report = {'id': r_id, 'type': 'start', 'parent id': parent, 'name': name}
        if attrs is not None:
            report['attrs'] = attrs

        response = self.service_client.post('/reports/upload/', {'report': json.dumps(report)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(ReportComponent.objects.filter(
            root__job_id=self.job.pk, identifier=self.job.identifier + r_id,
            parent__identifier=self.job.identifier + parent, component__name=name, finish_date=None
        )), 1)

        self.cmp_stack.append(r_id)
        if failed:
            self.__upload_unknown_report(r_id, 'unknown0.zip')
            while len(self.cmp_stack) > 0:
                self.__upload_finish_report(self.cmp_stack[-1])
            raise DecisionError('Component %s failed!' % name)
        return r_id

    def __upload_finish_report(self, r_id):
        report = {'id': r_id, 'type': 'finish', 'resources': resources(), 'desc': 'Description text', 'log': 'log.zip'}
        with open(os.path.join(ARCHIVE_PATH, 'log.zip'), mode='rb') as fp:
            response = self.service_client.post('/reports/upload/', {'report': json.dumps(report), 'file': [fp]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertIsNotNone(ReportComponent.objects.get(identifier=self.job.identifier + r_id).finish_date)

        if len(self.cmp_stack) > 0:
            self.cmp_stack.pop()

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
            'report': json.dumps({'id': r_id, 'type': 'data', 'data': data})
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

    def __upload_verification_report(self, name, parent, attrs=None, coverage=None, log=True):
        r_id = self.__get_report_id(name)
        if not isinstance(attrs, list):
            attrs = []
        report = {
            'id': r_id, 'type': 'verification', 'parent id': parent, 'name': name, 'attrs': attrs,
            'resources': resources(), 'data': {'description': str(r_id)}
        }

        files = []
        if coverage is not None:
            files.append(open(os.path.join(ARCHIVE_PATH, coverage), mode='rb'))
            report['coverage'] = coverage
        if log:
            files.append(open(os.path.join(ARCHIVE_PATH, 'log.zip'), mode='rb'))
            report['log'] = 'log.zip'
        try:
            response = self.service_client.post('/reports/upload/', {'report': json.dumps(report), 'file': files})
        except Exception:
            for f in files:
                f.close()
            raise

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        report = ReportComponent.objects.filter(
            root__job_id=self.job.pk, identifier=self.job.identifier + r_id, verification=True,
            parent__identifier=self.job.identifier + parent, component__name=name, finish_date=None
        ).first()
        self.assertIsNotNone(report)
        if log:
            self.assertNotEqual(report.log, '')
        else:
            self.assertEqual(report.log, '')
        if verifier_files:
            self.assertNotEqual(report.verifier_files, '')
        else:
            self.assertEqual(report.verifier_files, '')
        return r_id

    def __upload_progress(self, ts, sj=None, start=False, finish=False):
        data = {
            'total tasks to be generated': ts[0],
            'failed tasks': ts[1],
            'solved tasks': ts[2],
            'expected time for solving tasks': ts[3],
            'start tasks solution': start,
            'finish tasks solution': finish,
        }
        if sj is not None:
            data.update({
                'total subjobs to be solved': sj[0],
                'failed subjobs': sj[1],
                'solved subjobs': sj[2],
                'expected time for solving subjobs': sj[3],
                'start subjobs solution': start,
                'finish subjobs solution': finish
            })
        response = self.service_client.post('/service/update_progress/', {'progress': json.dumps(data)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

    def __upload_finish_verification_report(self, r_id):
        response = self.service_client.post('/reports/upload/', {
            'report': json.dumps({'id': r_id, 'type': 'verification finish'})
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(ReportComponent.objects.filter(
            Q(root__job_id=self.job.pk, identifier=self.job.identifier + r_id, verification=True) & ~Q(finish_date=None)
        )), 1)

    def __upload_unknown_report(self, parent, archive):
        r_id = self.__get_report_id('unknown')
        with open(os.path.join(ARCHIVE_PATH, archive), mode='rb') as fp:
            response = self.service_client.post('/reports/upload/', {
                'report': json.dumps({
                    'id': r_id, 'type': 'unknown', 'parent id': parent, 'problem_description': os.path.basename(fp.name)
                }), 'file': fp
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(ReportUnknown.objects.filter(
            root__job_id=self.job.pk, identifier=self.job.identifier + r_id,
            parent__identifier=self.job.identifier + parent
        ).count(), 1)

    def __upload_safe_report(self, parent, attrs, archive):
        r_id = self.__get_report_id('safe')
        response = self.service_client.post('/reports/upload/', {'report': json.dumps({
            'id': r_id, 'type': 'safe', 'parent id': parent, 'attrs': attrs
        })})
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
                'id': r_id, 'type': 'unsafe', 'parent id': parent, 'attrs': attrs,
                'sources': os.path.basename(fp.name), 'error traces': [os.path.basename(fp.name)]
            }), 'file': fp})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(ReportUnsafe.objects.filter(
            root__job_id=self.job.pk, identifier__startswith=self.job.identifier + r_id,
            parent__identifier=self.job.identifier + parent
        )), 1)

    def __upload_job_coverage(self, r_id, coverage):
        report = {'id': r_id, 'type': 'job coverage', 'coverage': coverage}
        files = []
        for carch in coverage.values():
            files.append(open(os.path.join(ARCHIVE_PATH, carch), mode='rb'))
        try:
            response = self.service_client.post('/reports/upload/', {'report': json.dumps(report), 'file': files})
        except Exception:
            for fp in files:
                fp.close()
            raise
        else:
            for fp in files:
                fp.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

    def __decide_job(self, reports_data):
        sch_data = {
            'tasks': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'task errors': {}, 'task descriptions': {}, 'task solutions': {},
            'jobs': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'job errors': {}, 'job configurations': {}
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
            'type': 'start', 'id': '/', 'attrs': [{'name': 'Klever Core version', 'value': 'latest'}], 'comp': COMPUTER
        })})
        self.assertIn(response['Content-Type'], {'application/x-zip-compressed', 'application/zip'})
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[2][0])

        self.__upload_data_report('/', {
            'module1': {'ideal verdict': 'safe', 'verdict': 'unsafe', 'comment': 'This is comment for module1'},
            'module2': {'ideal verdict': 'safe', 'verdict': 'safe'}
        })
        self.__upload_data_report('/', {
            'module3': {'ideal verdict': 'unsafe', 'verdict': 'unsafe', 'comment': 'This is comment for module3'},
            'module4': {'ideal verdict': 'unsafe', 'verdict': 'unknown'}
        })

        core_coverage = {}
        if any('chunks' in chunk for chunk in reports_data):
            progress_sj = [len(reports_data), 0, 0, 100 * len(reports_data) + 10]
            progress_ts = [len(reports_data) * 2, 0, 0, 100 * len(reports_data)]
            self.__upload_progress(progress_ts, progress_sj, True, False)
            for subjob in reports_data:
                if 'chunks' in subjob:
                    try:
                        core_coverage.update(self.__upload_subjob(subjob))
                    except DecisionError:
                        pass
                progress_sj[2] += 1
                progress_sj[3] -= 100
                progress_ts[2] += 2
                progress_ts[3] -= 100
                self.__upload_progress(progress_ts, progress_sj, False, False)
            self.__upload_progress(progress_ts, progress_sj, False, True)
        else:
            try:
                self.__upload_chunks(reports_data)
            except DecisionError:
                pass

        if len(core_coverage) > 0:
            self.__upload_job_coverage('/', core_coverage)

        self.__upload_finish_report('/')

        new_sch_data = sch_data.copy()
        new_sch_data['jobs']['finished'].append(self.job.identifier)
        response = self.service_client.post('/service/get_jobs_and_tasks/', {
            'jobs and tasks status': json.dumps(new_sch_data)
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[3][0])

    def __upload_subjob(self, subjob):
        sj = self.__upload_start_report('Subjob', '/',
                                        [{'name': 'Name',
                                          'value': 'test/dir/and/some/other/text:%s' % subjob['requirement']}])
        lkbce = self.__upload_start_report('LKBCE', sj)
        self.__upload_attrs_report(lkbce, [LINUX_ATTR])
        self.__upload_finish_report(lkbce)

        lkvog = self.__upload_start_report('LKVOG', sj, [LKVOG_ATTR])
        self.__upload_finish_report(lkvog)

        vtg = self.__upload_start_report('VTG', sj, [LINUX_ATTR, LKVOG_ATTR])
        for chunk in subjob['chunks']:
            vtgw = self.__upload_start_report('VTGW', vtg, [
                {'name': 'Requirement', 'value': subjob['requirement']},
                {'name': 'Program fragment', 'value': chunk['module']}
            ], failed=(chunk.get('fail') == 'VTGW'))
            for cmp in ['ASE', 'EMG', 'FVTP', 'RSG', 'SA', 'TR', 'Weaver']:
                cmp_id = self.__upload_start_report(cmp, vtgw, failed=(chunk.get('fail') == cmp))
                self.__upload_finish_report(cmp_id)
            self.__upload_finish_report(vtgw)
        self.__upload_finish_report(vtg)

        vrp = self.__upload_start_report('VRP', sj, [LINUX_ATTR, LKVOG_ATTR])
        for chunk in subjob['chunks']:
            rp = self.__upload_start_report('RP', vrp, [
                {'name': 'Requirement', 'value': subjob['requirement']},
                {'name': 'Program fragment', 'value': chunk['module']}
            ], failed=(chunk.get('fail') == 'RP'))
            self.__upload_verdicts(rp, chunk)
            self.__upload_finish_report(rp)
        self.__upload_finish_report(vrp)

        sj_coverage = {subjob['requirement']: 'Core_coverage.zip'}
        self.__upload_job_coverage(sj, sj_coverage)
        self.__upload_finish_report(sj)
        return sj_coverage

    def __upload_chunks(self, reports_data):
        lkbce = self.__upload_start_report('LKBCE', '/')
        self.__upload_attrs_report(lkbce, [LINUX_ATTR])
        self.__upload_finish_report(lkbce)

        lkvog = self.__upload_start_report('LKVOG', '/', [LKVOG_ATTR])
        self.__upload_finish_report(lkvog)

        vtg = self.__upload_start_report('VTG', '/', [LINUX_ATTR, LKVOG_ATTR])
        for chunk in reports_data:
            vtgw = self.__upload_start_report('VTGW', vtg, [
                {'name': 'Requirement', 'value': chunk['requirement']},
                {'name': 'Program fragment', 'value': chunk['module']}
            ], failed=(chunk.get('fail') == 'VTGW'))
            for cmp in ['ASE', 'EMG', 'FVTP', 'RSG', 'SA', 'TR', 'Weaver']:
                cmp_id = self.__upload_start_report(cmp, vtgw, failed=(chunk.get('fail') == cmp))
                self.__upload_finish_report(cmp_id)
            self.__upload_finish_report(vtgw)
        self.__upload_finish_report(vtg)

        progress_ts = [len(reports_data), 0, 0, 100 * len(reports_data)]
        self.__upload_progress(progress_ts, None, True, False)
        vrp = self.__upload_start_report('VRP', '/', [LINUX_ATTR, LKVOG_ATTR])
        for chunk in reports_data:
            rp = self.__upload_start_report('RP', vrp, [
                {'name': 'Requirement', 'value': chunk['requirement']},
                {'name': 'Program fragment', 'value': chunk['module']}
            ], failed=(chunk.get('fail') == 'RP'))
            self.__upload_verdicts(rp, chunk)
            self.__upload_finish_report(rp)
            progress_ts[2] += 1
            progress_ts[3] -= 100
            self.__upload_progress(progress_ts, None, False, False)
        self.__upload_finish_report(vrp)
        self.__upload_progress(progress_ts, None, False, True)

    def __upload_verdicts(self, parent, chunk):
        if 'unsafes' in chunk:
            coverage = 'partially_coverage.zip'
        else:
            coverage = None
        tool = self.__upload_verification_report(
            chunk['tool'], parent, coverage=coverage,
            verifier_files=chunk.get('verifier_files', False), log=chunk.get('log', False)
        )
        if 'safe' in chunk:
            self.__upload_safe_report(tool, [], chunk['safe'])
        elif 'unsafes' in chunk:
            cnt = 1
            for u in chunk['unsafes']:
                self.__upload_unsafe_report(tool, [{'name': 'entry point', 'value': 'func_%s' % cnt}], u)
                cnt += 1
        if 'unknown' in chunk and 'safe' not in chunk:
            self.__upload_unknown_report(tool, chunk['unknown'])
        self.__upload_finish_verification_report(tool)

    def tearDown(self):
        if os.path.exists(os.path.join(settings.MEDIA_ROOT, self.job_archive)):
            os.remove(os.path.join(settings.MEDIA_ROOT, self.job_archive))
        super().tearDown()


class ResponseError(Exception):
    pass


class DecideJobs:
    def __init__(self, data, **kwargs):
        self._base_url = 'http://127.0.0.1:{}'.format(kwargs.get('port') or 8998)
        self._data = data
        self._username = kwargs.get('username', 'service')
        self._password = kwargs.get('password', 'service')
        self._full_coverage = bool(kwargs.get('with_full_coverage'))
        self._progress = bool(kwargs.get('with_progress'))
        self._queue_name = kwargs.get('queue_name') or settings.RABBIT_MQ_QUEUE

        self.session = self.__login()
        self.__start()

    def __start(self):
        conn_producer, conn_consumer = Pipe()
        rmq_reader = Process(target=self.read_queue, args=(conn_producer,))
        msg_processor = Process(target=self.process_message, args=(conn_consumer,))

        rmq_reader.start()
        msg_processor.start()
        try:
            rmq_reader.join()
            msg_processor.join()
        except KeyboardInterrupt:
            rmq_reader.terminate()
            msg_processor.terminate()

    def __login(self):
        session = requests.Session()
        resp = session.post(self._base_url + '/service/get_token/', data={
            'username': self._username, 'password': self._password
        })
        if resp.status_code != 200:
            raise ResponseError(resp.json())
        session.headers.update({'Authorization': 'Token {}'.format(resp.json()['token'])})
        return session

    def __request(self, url, **kwargs):
        method = kwargs.pop('method', 'POST')
        try:
            resp = self.session.request(method, self._base_url + url, **kwargs)
        except Exception as e:
            logger.exception(e)
            return None
        if resp.status_code != 200:
            try:
                logger.error(resp.json())
            except Exception as e:
                logger.error(resp.content)
            return None
        return resp

    def read_queue(self, conn):
        def callback(ch, method, properties, body):
            ch.basic_ack(delivery_tag=method.delivery_tag)
            res = body.decode('utf-8')
            logger.info('Read: {}'.format(res))
            conn.send(res)

        with RMQConnect() as channel:
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(self._queue_name, callback)
            channel.start_consuming()

    def __decide(self, job_uuid):
        try:
            logger.info('Downloading the job {}'.format(job_uuid))
            self.__request('/jobs/api/download-files/{}/'.format(job_uuid), method='GET')

            DecideJob(
                job_uuid, self._username, self._password, self._data,
                with_full_coverage=self._full_coverage,
                with_progress=self._progress, base_url=self._base_url
            )
        except Exception as e:
            logger.exception(e)

    def __cancel_job(self, job_id):
        logger.info('Cancelling the job: {}'.format(job_id))
        try:
            self.__request('/service/decision-status/{}/'.format(job_id), method='PATCH', data={'status': '7'})
        except Exception as e:
            logger.exception(e)

    def process_message(self, conn):
        while True:
            msg = conn.recv()
            m_type, m_id, m_status, m_sch_type = msg.split()
            if m_type != 'job':
                continue
            if m_status == '1':
                self.__decide(m_id)
            elif m_status == '5':
                logger.info('The job "{}" is corrupted'.format(m_id))
            elif m_status == '6':
                self.__cancel_job(m_id)


class DecideJob:
    def __init__(self,
                 job_uuid, username, password, reports_data,
                 with_full_coverage=False, with_progress=False, base_url=None):
        self.base_url = base_url or 'http://127.0.0.1:8998'
        self._job_uuid = job_uuid
        self.session = self.__login(username, password)

        self._progress_url = '/service/progress/{}/'.format(self._job_uuid)
        self._upload_url = '/reports/api/upload/{}/'.format(self._job_uuid)
        self._original_sources = '22c00d3c-c129-42fe-91bd-a24b6a67b23e'

        self.reports_data = reports_data
        self.full_coverage = with_full_coverage
        self._progress = with_progress
        self.ids_in_use = []
        self._cmp_stack = []
        self._progress_data = {}
        try:
            self.__decide_job()
        except DecisionError as e:
            self.__request(
                url='/service/decision-status/{}/'.format(self._job_uuid), method='PATCH',
                data={'status': '4', 'error': str(e)}
            )

    def __login(self, username, password):
        session = requests.Session()
        resp = session.post(self.base_url + '/service/get_token/', data={'username': username, 'password': password})
        if resp.status_code != 200:
            raise ResponseError(resp.json())
        session.headers.update({'Authorization': 'Token {}'.format(resp.json()['token'])})
        return session

    def __request(self, **kwargs):
        method = kwargs.pop('method', 'POST')
        url = kwargs.pop('url', self._upload_url)
        cnt = 0
        while True:
            try:
                resp = self.session.request(method, self.base_url + url, **kwargs)
            except Exception as e:
                # logger.exception(e)
                logger.error(str(e))
            else:
                break
            time.sleep(1)
            cnt += 1
            if cnt > 5:
                raise ResponseError('Connection max tries exceeded')

        status_code = str(resp.status_code)
        if not status_code.startswith('2'):
            try:
                logger.error(resp.json())
            except Exception as e:
                print(e)
                logger.error(resp.content)
            resp.close()
            raise ResponseError('Unexpected status code returned: {}'.format(status_code))
        return resp

    def __upload_reports(self, reports, archives):
        time.sleep(0.1)
        logger.info(str(list('{}: {}'.format(r.get('type'), r.get('identifier')) for r in reports)) + str(archives))
        archives_fp = {}
        try:
            for a_name in archives:
                archives_fp[os.path.basename(a_name)] = open(os.path.join(ARCHIVE_PATH, a_name), mode='rb')
            self.__request(data={
                'reports': json.dumps(reports), 'archives': json.dumps(list(archives_fp))
            }, files=archives_fp)
        finally:
            for fp in archives_fp.values():
                fp.close()

    def __get_report_id(self, name):
        r_id = '/' + name
        while r_id in self.ids_in_use:
            r_id = '/%s%s' % (name, random.randint(1, 100))
        self.ids_in_use.append(r_id)
        return r_id

    def __upload_start_report(self, name, parent, attrs=None, failed=False, finish=False, **kwargs):
        r_id = self.__get_report_id(name)
        files = set()
        report_data = {
            'identifier': r_id, 'type': 'start', 'parent': parent, 'component': name
        }
        report_data.update(kwargs)
        reports = [report_data]
        if attrs is not None:
            reports[0]['attrs'] = attrs
        self._cmp_stack.append(r_id)

        if failed:
            files.add('unknown0.zip')
            reports.append({'type': 'unknown', 'parent': r_id, 'problem_description': 'unknown0.zip'})
            while len(self._cmp_stack) > 1:
                f_rep, logname = self.__get_finish_report(self._cmp_stack[-1])
                files.add(logname)
                reports.append(f_rep)
            self.__upload_reports(reports, files)
            raise DecisionError('Component %s failed!' % name)

        if finish:
            f_rep, logname = self.__get_finish_report(r_id)
            reports.append(f_rep)
            files.add(logname)

        self.__upload_reports(reports, files)
        return r_id

    def __get_finish_report(self, r_id):
        report = {'identifier': r_id, 'type': 'finish', 'log': 'log.zip'}
        report.update(resources())
        if len(self._cmp_stack) > 0:
            self._cmp_stack.pop()
        return report, 'log.zip'

    def __upload_finish_report(self, r_id):
        f_rep, logname = self.__get_finish_report(r_id)
        self.__upload_reports([f_rep], [logname])

    def __upload_patch_report(self, r_id, **kwargs):
        archives = []
        report = {'identifier': r_id, 'type': 'patch'}

        # Report data
        if kwargs.get('data'):
            report['data'] = kwargs['data']

        # Report original sources
        if kwargs.get('original_sources'):
            report['original_sources'] = self._original_sources

        # Report additional sources
        if kwargs.get('additional_sources'):
            report['additional_sources'] = kwargs['additional_sources']
            archives.append(kwargs['additional_sources'])

        # Report attributes with its data if provided
        if kwargs.get('attrs'):
            report['attrs'] = kwargs['attrs']
            if kwargs.get('attr_data'):
                report['attr_data'] = kwargs['attr_data']
                archives.append(kwargs['attr_data'])

        self.__upload_reports([report], archives)

    def __init_progress(self):
        tasks = 0
        subjobs = None
        if any('chunks' in chunk for chunk in self.reports_data):
            subjobs = len(self.reports_data)
            for chunk in self.reports_data:
                tasks += len(chunk['chunks'])
        else:
            tasks = len(self.reports_data)

        self._progress_data['tasks'] = {
            'total': tasks, 'solved': 0, 'failed': 0, 'time': 100, 'start': False, 'finish': False
        }
        if subjobs:
            self._progress_data['subjobs'] = {
                'total': subjobs, 'solved': 0, 'failed': 0, 'time': 400, 'start': False, 'finish': False
            }
        self.__upload_progress()

    def __upload_progress(self):
        if not self._progress:
            return
        self.__request(url=self._progress_url, data=self.__get_progress(), method='PATCH')
        time.sleep(1)

    def __get_progress(self):
        if not self._progress_data['tasks']['start']:
            self._progress_data['tasks']['start'] = True
            data = {
                'total_ts': self._progress_data['tasks']['total'],
                'failed_ts': 0, 'solved_ts': 0,
                'gag_text_ts': 'Calculating time',
                'tasks_started': True
            }
            if 'subjobs' not in self._progress_data:
                return data
            self._progress_data['subjobs']['start'] = True
            data.update({
                'total_sj': self._progress_data['subjobs']['total'],
                'failed_sj': 0, 'solved_sj': 0,
                'gag_text_sj': 'Calculating time',
                'subjobs_started': True
            })
            return data

        data = {}
        if not self._progress_data['tasks']['finish']:
            tasks_left = self._progress_data['tasks']['total'] - \
                         self._progress_data['tasks']['solved'] - \
                         self._progress_data['tasks']['failed']
            data = {}
            if tasks_left == 0 and not self._progress_data['tasks']['finish']:
                self._progress_data['tasks']['finish'] = True
                data.update({
                    'failed_ts': self._progress_data['tasks']['failed'],
                    'solved_ts': self._progress_data['tasks']['solved'],
                    'expected_time_ts': 0,
                    'tasks_finished': True
                })
            else:
                data.update({
                    'failed_ts': self._progress_data['tasks']['failed'],
                    'solved_ts': self._progress_data['tasks']['solved'],
                    'expected_time_ts': tasks_left * self._progress_data['tasks']['time']
                })

        if 'subjobs' not in self._progress_data:
            return data
        subjobs_left = (self._progress_data['subjobs']['total'] -
                        self._progress_data['subjobs']['solved'] -
                        self._progress_data['subjobs']['failed'])
        if subjobs_left == 0 and not self._progress_data['subjobs']['finish']:
            self._progress_data['subjobs']['finish'] = True
            data.update({
                'failed_sj': self._progress_data['subjobs']['failed'],
                'solved_sj': self._progress_data['subjobs']['solved'],
                'expected_time_sj': 0,
                'subjobs_finished': True
            })
        else:
            data.update({
                'failed_sj': self._progress_data['subjobs']['failed'],
                'solved_sj': self._progress_data['subjobs']['solved'],
                'expected_time_sj': subjobs_left * self._progress_data['subjobs']['time']
            })
        return data

    def __upload_job_coverage(self, r_id, coverage):
        report = {'identifier': r_id, 'type': 'coverage', 'coverage': coverage}
        cov_files = {}
        for carch in coverage.values():
            cov_files[os.path.basename(carch)] = open(os.path.join(ARCHIVE_PATH, carch), mode='rb')
        try:
            self.__request(data={
                'reports': json.dumps([report]), 'archives': json.dumps(list(cov_files))
            }, files=cov_files)
        finally:
            for fp in cov_files.values():
                fp.close()

    def __upload_original_sources(self):
        # Upload original sources if not exists
        resp = self.__request(
            url='/reports/api/has-sources/', method='GET', params={'identifier': self._original_sources}
        )
        if not resp.json()['exists']:
            with open(os.path.join(ARCHIVE_PATH, 'linux.zip'), mode='rb') as fp:
                self.__request(url='/reports/api/upload-sources/',
                               data={'identifier': self._original_sources},
                               files=[('archive', fp)])

    def __decide_job(self):
        logger.info('Start {} deciding'.format(self._job_uuid))
        self.__upload_original_sources()

        core_id = self.__upload_start_report(
            'Core', None, attrs=[{'name': 'Klever Core version', 'value': 'latest'}], computer=COMPUTER
        )

        core_data_1 = {
            'module1': {'ideal verdict': 'safe', 'verdict': 'unsafe', 'comment': 'This is comment for module1'},
            'module2': {'ideal verdict': 'safe', 'verdict': 'safe'}
        }
        core_data_2 = {
            'module3': {'ideal verdict': 'unsafe', 'verdict': 'unsafe', 'comment': 'This is comment for module3'},
            'module4': {'ideal verdict': 'unsafe', 'verdict': 'unknown'}
        }
        self.__upload_patch_report(core_id, data=core_data_1)
        self.__upload_patch_report(core_id, data=core_data_2)

        self.__init_progress()
        if any('chunks' in chunk for chunk in self.reports_data):
            for subjob in self.reports_data:
                self.__upload_subjob(subjob, core_id)
                self._progress_data['subjobs']['solved'] += 1
                self.__upload_progress()
        else:
            self.__upload_chunks(core_id)
            if self.full_coverage:
                self.__upload_patch_report(core_id, original_sources=True)
                self.__upload_job_coverage(core_id, {'no:subjobs': 'linux-coverage.zip'})

        self.__upload_progress()
        self.__upload_finish_report(core_id)
        self.__request(url='/service/decision-status/{}/'.format(self._job_uuid), method='PATCH', data={'status': '3'})

    def __upload_subjob(self, subjob, core_id):
        sj = self.__upload_start_report('Subjob', core_id, [{
            'name': 'Name', 'value': 'test/dir/and/some/other/text:{0}'.format(subjob['requirement'])
        }])
        lkbce = self.__upload_start_report('LKBCE', sj)
        self.__upload_patch_report(lkbce, attrs=[LINUX_ATTR])
        self.__upload_finish_report(lkbce)

        self.__upload_start_report('LKVOG', sj, [LKVOG_ATTR], finish=True)

        vtg = self.__upload_start_report('VTG', sj, [LINUX_ATTR, LKVOG_ATTR])
        for chunk in subjob['chunks']:
            vtgw = self.__upload_start_report('VTGW', vtg, [
                {'name': 'Requirement', 'value': subjob['requirement'], 'compare': True, 'associate': True},
                {'name': 'Program fragment', 'value': chunk['module'], 'compare': True, 'associate': True}
            ], failed=(chunk.get('fail') == 'VTGW'))
            for cmp in ['ASE', 'EMG', 'FVTP', 'RSG', 'SA', 'TR', 'Weaver']:
                self.__upload_start_report(cmp, vtgw, failed=(chunk.get('fail') == cmp), finish=True)
            self.__upload_finish_report(vtgw)
        self.__upload_finish_report(vtg)

        vrp = self.__upload_start_report('VRP', sj, [LINUX_ATTR, LKVOG_ATTR])
        for chunk in subjob['chunks']:
            rp = self.__upload_start_report('RP', vrp, [
                {'name': 'Requirement', 'value': subjob['requirement'], 'compare': True, 'associate': True},
                {'name': 'Program fragment', 'value': chunk['module'], 'compare': True, 'associate': True}
            ], failed=(chunk.get('fail') == 'RP'))
            self.__upload_verdicts(rp, chunk)
            self.__upload_finish_report(rp)
            self._progress_data['tasks']['solved'] += 1
            self.__upload_progress()
        self.__upload_finish_report(vrp)

        if self.full_coverage:
            self.__upload_patch_report(sj, original_sources=True)
            self.__upload_job_coverage(sj, {subjob['requirement']: 'linux-coverage.zip'})

        self.__upload_finish_report(sj)

    def __upload_chunks(self, core_id):
        lkbce = self.__upload_start_report('LKBCE', core_id)
        self.__upload_patch_report(lkbce, attrs=[LINUX_ATTR])
        self.__upload_finish_report(lkbce)

        self.__upload_start_report('LKVOG', core_id, [LKVOG_ATTR], finish=True)

        vtg = self.__upload_start_report('VTG', core_id, [LINUX_ATTR, LKVOG_ATTR])
        for chunk in self.reports_data:
            vtgw = self.__upload_start_report('VTGW', vtg, [
                {'name': 'Requirement', 'value': chunk['requirement'], 'compare': True, 'associate': True},
                {'name': 'Program fragment', 'value': chunk['module'], 'compare': True, 'associate': True}
            ], failed=(chunk.get('fail') == 'VTGW'))
            for cmp in ['ASE', 'EMG', 'FVTP', 'RSG', 'SA', 'TR', 'Weaver']:
                self.__upload_start_report(cmp, vtgw, failed=(chunk.get('fail') == cmp), finish=True)
            self.__upload_finish_report(vtgw)
        self.__upload_finish_report(vtg)

        vrp = self.__upload_start_report('VRP', core_id, [LINUX_ATTR, LKVOG_ATTR])
        for chunk in self.reports_data:
            rp = self.__upload_start_report('RP', vrp, [
                {'name': 'Requirement', 'value': chunk['requirement'], 'compare': True, 'associate': True},
                {'name': 'Program fragment', 'value': chunk['module'], 'compare': True, 'associate': True}
            ], failed=(chunk.get('fail') == 'RP'))
            self.__upload_verdicts(rp, chunk)
            self.__upload_finish_report(rp)
            self._progress_data['tasks']['solved'] += 1
            self.__upload_progress()
        self.__upload_finish_report(vrp)

    def __upload_verdicts(self, parent, chunk):
        cnt = 0
        verification = {
            'identifier': self.__get_report_id(chunk['tool']),
            'type': 'verification', 'parent': parent, 'component': chunk['tool'],
            'attrs': [{'name': 'Test', 'value': 'test value', 'data': 'attrdata.txt'}],
            'data': {'description': str(chunk['tool'])}, 'original_sources': self._original_sources,
            'attr_data': 'attrdata.zip'
        }
        verification.update(resources())

        files = ['attrdata.zip']
        if chunk.get('log', False):
            files.append('log.zip')
            verification['log'] = 'log.zip'
        if chunk.get('coverage'):
            files.append(chunk['coverage'])
            verification['coverage'] = chunk['coverage']

        reports = [verification]
        if 'additional_sources' in chunk:
            files.append(chunk['additional_sources'])
            reports.append({
                'identifier': verification['identifier'],
                'type': 'patch',
                'additional_sources': chunk['additional_sources']
            })
        if 'safe' in chunk:
            cnt += 1
            files.append(chunk['safe'])
            reports.append({
                'identifier': '{}/safe'.format(verification['identifier']),
                'type': 'safe', 'parent': verification['identifier'], 'attrs': []
            })
        elif 'unsafes' in chunk:
            cnt = 1
            for unsafe_archive in chunk['unsafes']:
                files.append(unsafe_archive)
                cnt += 1
                reports.append({
                    'identifier': '{}/unsafe/{}'.format(verification['identifier'], cnt),
                    'type': 'unsafe', 'parent': verification['identifier'],
                    'attrs': [{'name': 'entry point', 'value': 'func_%s' % cnt}],
                    'error_trace': unsafe_archive
                })
                cnt += 1
        if 'unknown' in chunk and 'safe' not in chunk:
            files.append(chunk['unknown'])
            reports.append({
                'identifier': '{}/unknown'.format(verification['identifier']),
                'type': 'unknown', 'parent': verification['identifier'],
                'problem_description': chunk['unknown']
            })
        reports.append({'identifier': verification['identifier'], 'type': 'verification finish'})
        self.__upload_reports(reports, files)

    def __is_not_used(self):
        pass


class UploadRawReports:
    base_url = 'http://127.0.0.1:8998'
    orig_sources_uuid = "936d4726-6d0b-4244-a63e-bb1133706555"

    def __init__(self, decision_uuid, reports_dir):
        self._upload_url = '/reports/api/upload/{}/'.format(decision_uuid)
        self._reports_dir = os.path.abspath(reports_dir)
        assert os.path.isdir(self._reports_dir), 'Reports directory not found!'
        self.session = requests.Session()
        self.__login()
        self.__decide_job(decision_uuid)

    def __login(self):
        resp = self.__request('/service/get_token/', data={'username': 'service', 'password': 'service'})
        self.session.headers.update({'Authorization': 'Token {}'.format(resp.json()['token'])})

    def __decide_job(self, decision_uuid):
        self.__request('/jobs/api/download-files/{}/'.format(decision_uuid), method='GET')
        self.__send_reports()
        self.__request('/service/decision-status/{}/'.format(decision_uuid), method='PATCH', data={'status': '3'})

    def __send_reports(self):
        all_archives = list(f for f in os.listdir(self._reports_dir) if f.endswith('.zip'))
        cnt = 1
        while True:
            report_json = os.path.join(self._reports_dir, '{}.json'.format(cnt))
            if not os.path.isfile(report_json):
                logger.info('{}.json not found!'.format(cnt))
                return
            with open(report_json, mode='r', encoding='utf-8') as fp:
                report = json.load(fp)
            report_archives = []
            for a_name in all_archives:
                if a_name.startswith('{}-'.format(cnt)) or a_name.startswith('{} '.format(cnt)):
                    report_archives.append(a_name)
            self.__upload_report(report, report_archives)
            cnt += 1
            time.sleep(0.01)

    def __upload_report(self, report, archives):
        if report.get('original_sources'):
            report['original_sources'] = self.orig_sources_uuid
        report.pop('task', None)

        logger.info('{}: {}; '.format(report.get('type'), report.get('identifier')) + str(archives))
        archives_fp = {}
        try:
            for a_name in archives:
                archives_fp[os.path.basename(a_name)] = open(os.path.join(self._reports_dir, a_name), mode='rb')
            self.__request(self._upload_url, data={'report': json.dumps(report)}, files=archives_fp)
        finally:
            for fp in archives_fp.values():
                fp.close()

    def __request(self, url, method='POST', **kwargs):
        cnt = 0
        while True:
            try:
                resp = self.session.request(method, self.base_url + url, **kwargs)
            except Exception as e:
                logger.error(str(e))
            else:
                break
            time.sleep(1)
            cnt += 1
            if cnt > 3:
                raise ResponseError('Connection max tries exceeded')

        if not 200 <= resp.status_code < 300:
            try:
                error_str = str(resp.json())
            except Exception as e:
                print(e)
                error_str = resp.content
            logger.error(error_str)
            resp.close()
            raise ResponseError('Unexpected status code returned: {}'.format(resp.status_code))
        return resp


class GetReportsPacks:
    def __init__(self, filename):
        self._file = filename
        self.data = [[]]
        self._collect_files = False

    def analyze(self):
        with open(self._file, mode='r', encoding='utf-8') as fp:
            for line in fp:
                self.__parse_line(line)

    def __parse_line(self, line):
        if self._collect_files:
            m = re.match(r'^.*/(.*?\.zip).*$', line)
            if m:
                self.data[-1][-1]['files'].append(m.group(1))
                return
            self._collect_files = False
        m = re.match(r'^.*Send\s"POST"\srequest.*api/upload.*$', line)
        if m:
            self.data.append([])
            return
        m = re.match(r'^.*Upload\sreport\sfile.*/(\d+\.json)(.*)$', line)
        if m:
            self.data[-1].append({'report': m.group(1), 'files': []})
            if 'archives:' in m.group(2):
                self._collect_files = True


class UploadRawReportsPacks:
    base_url = 'http://127.0.0.1'

    def __init__(self, job_uuid, reports_log, original_sources):
        self.original_sources = original_sources
        self._upload_url = '/reports/api/upload/{}/'.format(job_uuid)
        self._reports_log = os.path.abspath(reports_log)
        assert os.path.isfile(self._reports_log), 'Reports log not found!'
        self.session = requests.Session()
        self.__login()
        self.__decide_job(job_uuid)

    def __login(self):
        resp = self.__request('/service/get_token/', data={'username': 'service', 'password': 'service'})
        self.session.headers.update({'Authorization': 'Token {}'.format(resp.json()['token'])})

    def __decide_job(self, job_uuid):
        self.__request('/jobs/api/download-files/{}/'.format(job_uuid), method='GET')
        self.__send_reports()
        self.__request('/service/decision-status/{}/'.format(job_uuid), method='PATCH', data={'status': '3'})

    def __send_reports(self):
        reports_dir = os.path.join(os.path.dirname(self._reports_log), 'reports')
        packs = GetReportsPacks(self._reports_log)
        packs.analyze()
        total_exec = 0
        for reports_pack in packs.data:
            reports = []
            archives = []
            report_types = []
            for report_data in reports_pack:
                with open(os.path.join(reports_dir, report_data['report']), mode='r', encoding='utf-8') as fp:
                    report = json.load(fp)
                    self.__fix_report(report)
                    report_types.append(report.get('type', 'UNKNOWN'))
                    reports.append(report)
                    for arch_name in report_data['files']:
                        archives.append(os.path.join(reports_dir, arch_name))
            exec_time = self.__upload_reports(reports, archives)
            total_exec += exec_time
            logger.info('{} ({}): {};'.format('+'.join(report_types), len(archives), exec_time))
            time.sleep(0.01)
        logger.info('Total exec: {}'.format(total_exec))

    def __fix_report(self, report):
        if report.get('original_sources'):
            report['original_sources'] = self.original_sources
        report.pop('task', None)

    def __upload_reports(self, reports, archives):
        archives_fp = {}
        try:
            for a_name in archives:
                archives_fp[os.path.basename(a_name)] = open(a_name, mode='rb')
            t1 = time.time()
            self.__request(self._upload_url, data={'reports': json.dumps(reports)}, files=archives_fp)
            exec_time = time.time() - t1
        finally:
            for fp in archives_fp.values():
                fp.close()
        return exec_time

    def __request(self, url, method='POST', **kwargs):
        cnt = 0
        while True:
            try:
                resp = self.session.request(method, self.base_url + url, **kwargs)
            except Exception as e:
                logger.error(str(e))
            else:
                break
            time.sleep(1)
            cnt += 1
            if cnt > 3:
                raise ResponseError('Connection max tries exceeded')

        if not 200 <= resp.status_code < 300:
            try:
                error_str = str(resp.json())
            except Exception as e:
                print(e)
                error_str = resp.content
            logger.error(error_str)
            resp.close()
            raise ResponseError('Unexpected status code returned: {}'.format(resp.status_code))
        return resp


def upload_sources(port=None):
    base_url = "http://127.0.0.1"
    if port:
        base_url += ':{}'.format(port)

    session = requests.Session()
    resp = session.post('{}/service/get_token/'.format(base_url), data={'username': 'service', 'password': 'service'})
    session.headers.update({'Authorization': 'Token {}'.format(resp.json()['token'])})
    with open('reports/test_files/linux.zip', mode='rb') as fp:
        resp = session.post(
            '{}/reports/api/upload-sources/'.format(base_url),
            data={'identifier': '936d4726-6d0b-4244-a63e-bb1133706555'}, files=[('archive', fp)]
        )
        print(resp.json())

# UploadRawReportsPacks('6b2ab3c7-1367-4cb2-8841-fff0fc2f6f85', 'S:/Work/temp/logs/log.txt',
# '6b2ab3c7-1367-4cb2-8841-fff0fc2f6f85')


class ReportsLogging:
    filename = "reports.log"

    def __init__(self, decision_id):
        self._decision = decision_id
        self._enabled = settings.ENABLE_UPLOAD_REPORTS_LOGS

    def log(self, action, *args):
        if not self._enabled:
            return
        message = "##".join(str(a) if a else 'NULL' for a in args)

        with open(os.path.join(settings.LOGS_DIR, self.filename), mode="a", encoding="utf-8") as fp:
            fp.write("{}-{}-{}: {}\n".format(time.time(), self._decision, action, message))


class TestCreateImages:
    base_url = 'http://127.0.0.1:8998'

    def __init__(self):
        self.session = requests.Session()
        self.root_dir = os.path.join(settings.MEDIA_ROOT, 'images')

        # Authenticate
        resp = self.__request('/service/get_token/', data={'username': 'service', 'password': 'service'})
        self.session.headers.update({'Authorization': 'Token {}'.format(resp.json()['token'])})
        self.create_images()

    def create_images(self):
        for root, _, filenames in os.walk(self.root_dir):
            for fname in filenames:
                if os.path.splitext(fname)[-1] != '.dot':
                    continue
                data_path = os.path.join(root, fname)
                image_path = os.path.join(root, fname + '.png')
                if os.path.isfile(image_path):
                    self.__create_image(image_path, data_path)

    def __create_image(self, image_path, data_path):
        data = {
            'decision': '6f63d646-26e8-4925-923b-aa36cfd24755',
            'report': '/Job',
            'title': os.path.splitext(os.path.basename(data_path))[0]
        }
        with open(image_path, mode='rb') as image_file:
            with open(data_path, mode='rb') as data_file:
                resp = self.__request(
                    '/reports/api/component/images-create/',
                    method='POST', data=data,
                    files=[('image', image_file), ('data', data_file)]
                )
                print(resp)

    def __request(self, url, method='POST', **kwargs):
        cnt = 0
        while True:
            try:
                resp = self.session.request(method, self.base_url + url, **kwargs)
            except Exception as e:
                logger.error(str(e))
            else:
                break
            time.sleep(1)
            cnt += 1
            if cnt > 3:
                raise ResponseError('Connection max tries exceeded')

        if not 200 <= resp.status_code < 300:
            try:
                error_str = str(resp.json())
            except Exception as e:
                print(e)
                error_str = resp.content
            logger.error(error_str)
            resp.close()
            raise ResponseError('Unexpected status code returned: {}'.format(resp.status_code))
        return resp
