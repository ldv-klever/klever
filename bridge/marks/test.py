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
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse

from bridge.utils import KleverTestCase, ArchiveFileContent
from bridge.vars import (
    SAFE_VERDICTS, UNSAFE_VERDICTS, MARK_SAFE, MARK_UNSAFE, MARK_STATUS, PROBLEM_DESC_FILE, ASSOCIATION_TYPE
)

from users.models import User
from jobs.models import Job
from reports.models import ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent
from marks.models import (
    MarkSafe, MarkUnsafe, MarkUnknown, MarkSafeHistory, MarkUnsafeHistory, MarkUnknownHistory,
    SafeTag, UnsafeTag, MarkSafeTag, MarkUnsafeTag, MarkSafeReport, MarkUnsafeReport, MarkUnknownReport,
    SafeAssociationLike, UnsafeAssociationLike, UnknownAssociationLike
)

from reports.test import DecideJobs, SJC_1

REPORT_ARCHIVES = os.path.join(settings.BASE_DIR, 'reports', 'test_files')


class TestMarks(KleverTestCase):
    def setUp(self):
        super(TestMarks, self).setUp()
        User.objects.create_superuser('superuser', '', 'top_secret')
        populate_users(
            manager={'username': 'manager', 'password': 'manager'},
            service={'username': 'service', 'password': 'service'}
        )
        self.client.post(reverse('users:login'), {'username': 'manager', 'password': 'manager'})
        self.client.post(reverse('population'))
        self.job = Job.objects.all().first()
        self.assertIsNotNone(self.job)
        self.client.post('/jobs/run_decision/%s/' % self.job.pk, {'mode': 'default', 'conf_name': 'development'})
        DecideJobs('service', 'service', SJC_1)

        self.safe_archive = 'test_safemark.zip'
        self.unsafe_archive = 'test_unsafemark.zip'
        self.unknown_archive = 'test_unknownmark.zip'
        self.test_tagsfile = 'test_tags.json'
        self.all_marks_arch = 'All-marks.zip'

    def test_safe(self):
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[3][0])

        # Delete populated marks
        response = self.client.post('/marks/delete/', {
            'type': 'safe', 'ids': json.dumps(list(MarkSafe.objects.values_list('id', flat=True)))
        })
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/marks/delete/', {
            'type': 'unsafe', 'ids': json.dumps(list(MarkUnsafe.objects.values_list('id', flat=True)))
        })
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/marks/delete/', {
            'type': 'unknown', 'ids': json.dumps(list(MarkUnknown.objects.values_list('id', flat=True)))
        })
        self.assertEqual(response.status_code, 200)

        # Create 5 safe tags
        created_tags = []
        response = self.client.post('/marks/tags/save_tag/', {
            'action': 'create', 'tag_type': 'safe', 'parent_id': '0', 'name': 'test:safe:tag:1',
            'description': 'Test safe tag description'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        try:
            created_tags.append(SafeTag.objects.get(tag='test:safe:tag:1'))
        except ObjectDoesNotExist:
            self.fail('Safe tag was not created')
        self.assertEqual(created_tags[0].description, 'Test safe tag description')
        self.assertEqual(created_tags[0].parent, None)

        for i in range(2, 6):
            self.client.post('/marks/tags/save_tag/', {
                'action': 'create', 'tag_type': 'safe',
                'parent_id': created_tags[i - 2].pk, 'name': 'test:safe:tag:%s' % i, 'description': ''
            })
            created_tags.append(SafeTag.objects.get(tag='test:safe:tag:%s' % i))
            self.assertEqual(created_tags[i - 1].parent, created_tags[i - 2])

        # Get tag parents for editing tag 'test:safe:tag:3'
        response = self.client.post('/marks/tags/safe/get_tag_data/', {'tag_id': created_tags[2].pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Get tag parents for creating new tag
        response = self.client.post('/marks/tags/safe/get_tag_data/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Edit 5th tag
        response = self.client.post('/marks/tags/save_tag/', {
            'action': 'edit', 'tag_type': 'safe', 'parent_id': created_tags[2].pk,
            'name': 'test:safe:tag:5', 'tag_id': created_tags[4].pk,
            'description': 'Test safe tag 5 description'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        try:
            created_tags[4] = SafeTag.objects.get(tag='test:safe:tag:5')
        except ObjectDoesNotExist:
            self.fail('Tag 5 was not found after editing')
        self.assertEqual(created_tags[4].parent, created_tags[2])
        self.assertEqual(created_tags[4].description, 'Test safe tag 5 description')

        # Remove 3d tag and check that its children (tag4 and tag5) are also removed
        response = self.client.post('/marks/tags/safe/delete/%s/' % created_tags[2].pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(
            SafeTag.objects.filter(tag__in=['test:safe:tag:3', 'test:safe:tag:4', 'test:safe:tag:5']).count(), 0
        )
        del created_tags[2:]

        # Get tags data (for edit/create mark page). Just check that there is no error in response.
        response = self.client.post('/marks/safe/tags_data/', {'selected_tags': json.dumps([created_tags[1].pk])})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Download tags
        response = self.client.get(reverse('marks:download_tags', args=['safe']))
        self.assertEqual(response.status_code, 200)
        with open(os.path.join(settings.MEDIA_ROOT, self.test_tagsfile), mode='wb') as fp:
            for chunk in response.streaming_content:
                fp.write(chunk)
        SafeTag.objects.all().delete()

        # Upload tags
        with open(os.path.join(settings.MEDIA_ROOT, self.test_tagsfile), mode='rb') as fp:
            response = self.client.post('/marks/tags/safe/upload/', {'file': fp})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        for i in range(0, len(created_tags)):
            try:
                created_tags[i] = SafeTag.objects.get(tag=created_tags[i].tag)
            except ObjectDoesNotExist:
                self.fail("Tags weren't uploaded")

        # Tags tree page
        response = self.client.get(reverse('marks:tags', args=['safe']))
        self.assertEqual(response.status_code, 200)

        # Get report
        safe = ReportSafe.objects.filter(root__job_id=self.job.pk).first()
        self.assertIsNotNone(safe)

        # Inline mark form
        response = self.client.get('/marks/safe/%s/create/inline/' % safe.id)
        self.assertEqual(response.status_code, 200)

        # Create mark page
        response = self.client.get(reverse('marks:mark_form', args=['safe', safe.pk, 'create']))
        self.assertEqual(response.status_code, 200)

        # Save mark
        compare_attrs = list({'is_compare': associate, 'attr': a_name}
                             for a_name, associate in safe.attrs.values_list('attr__name__name', 'associate'))
        response = self.client.post(reverse('marks:mark_form', args=['safe', safe.pk, 'create']), {
            'data': json.dumps({
                'description': 'Mark description',
                'is_modifiable': True,
                'verdict': MARK_SAFE[1][0],
                'status': MARK_STATUS[2][0],
                'tags': [created_tags[1].pk],
                'attrs': compare_attrs
            })
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertIsNone(res.get('error'))
        self.assertIn('cache_id', res)
        cache_id = res['cache_id']

        # Check mark's tables
        try:
            mark = MarkSafe.objects.get(job=self.job, author__username='manager')
        except ObjectDoesNotExist:
            self.fail('Mark was not created')
        self.assertEqual(mark.type, MARK_TYPE[0][0])
        self.assertEqual(mark.verdict, MARK_SAFE[1][0])
        self.assertEqual(mark.status, MARK_STATUS[2][0])
        self.assertEqual(mark.version, 1)
        self.assertEqual(mark.description, 'Mark description')
        self.assertEqual(mark.is_modifiable, True)
        self.assertEqual(len(mark.versions.all()), 1)
        mark_version = MarkSafeHistory.objects.get(mark=mark)
        self.assertEqual(mark_version.verdict, mark.verdict)
        self.assertEqual(mark_version.version, 1)
        self.assertEqual(mark_version.author.username, 'manager')
        self.assertEqual(mark_version.status, mark.status)
        self.assertEqual(mark_version.description, mark.description)
        for mark_attr in mark_version.attrs.all():
            self.assertIn({'is_compare': mark_attr.is_compare, 'attr': mark_attr.attr.name.name}, compare_attrs)
        self.assertEqual(ReportSafe.objects.get(pk=safe.pk).verdict, SAFE_VERDICTS[1][0])
        self.assertEqual(MarkSafeReport.objects.filter(mark=mark, report=safe, type=ASSOCIATION_TYPE[1][0]).count(), 1)
        self.assertEqual(len(MarkSafeTag.objects.filter(mark_version=mark_version, tag=created_tags[0])), 1)
        self.assertEqual(len(MarkSafeTag.objects.filter(mark_version=mark_version, tag=created_tags[1])), 1)
        try:
            rst = ReportSafeTag.objects.get(report__root__job=self.job, report__parent=None, tag=created_tags[0])
            self.assertEqual(rst.number, 1)
            rst = ReportSafeTag.objects.get(report__root__job=self.job, report__parent=None, tag=created_tags[1])
            self.assertEqual(rst.number, 1)
            rst = ReportSafeTag.objects.get(report__root__job=self.job, report_id=safe.parent_id, tag=created_tags[0])
            self.assertEqual(rst.number, 1)
            rst = ReportSafeTag.objects.get(report__root__job=self.job, report__id=safe.parent_id, tag=created_tags[1])
            self.assertEqual(rst.number, 1)
            srt = SafeReportTag.objects.get(report=safe, tag=created_tags[0])
            self.assertEqual(srt.number, 1)
            srt = SafeReportTag.objects.get(report=safe, tag=created_tags[1])
            self.assertEqual(srt.number, 1)
        except ObjectDoesNotExist:
            self.fail('Reports tags cache was not filled')

        # Associations changes
        response = self.client.get('/marks/safe/association_changes/%s/' % cache_id)
        self.assertEqual(response.status_code, 200)

        # Edit mark page
        response = self.client.get(reverse('marks:mark_form', args=['safe', mark.pk, 'edit']))
        self.assertEqual(response.status_code, 200)

        # Edit mark
        response = self.client.post(reverse('marks:mark_form', args=['safe', mark.pk, 'edit']), {
            'data': json.dumps({
                'description': 'New mark description',
                'is_modifiable': True,
                'verdict': MARK_SAFE[2][0],
                'status': MARK_STATUS[2][0],
                'tags': [created_tags[0].pk],
                'attrs': compare_attrs,
                'comment': 'Change 1'
            })
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertIsNone(res.get('error'))
        self.assertIn('cache_id', res)
        cache_id = res['cache_id']

        # Check mark's tables
        try:
            mark = MarkSafe.objects.get(job=self.job, author__username='manager')
        except ObjectDoesNotExist:
            self.fail('Mark was not created')
        self.assertEqual(mark.verdict, MARK_SAFE[2][0])
        self.assertEqual(mark.version, 2)
        self.assertEqual(mark.description, 'New mark description')
        self.assertEqual(mark.is_modifiable, True)
        self.assertEqual(len(mark.versions.all()), 2)
        mark_version = MarkSafeHistory.objects.filter(mark=mark).order_by('-version').first()
        self.assertEqual(mark_version.version, 2)
        self.assertEqual(mark_version.verdict, mark.verdict)
        self.assertEqual(mark_version.author.username, 'manager')
        self.assertEqual(mark_version.description, mark.description)
        self.assertEqual(mark_version.comment, 'Change 1')
        self.assertEqual(ReportSafe.objects.get(pk=safe.pk).verdict, SAFE_VERDICTS[2][0])
        self.assertEqual(len(MarkSafeReport.objects.filter(mark=mark, report=safe)), 1)
        self.assertEqual(len(MarkSafeTag.objects.filter(mark_version=mark_version, tag=created_tags[0])), 1)
        self.assertEqual(len(MarkSafeTag.objects.filter(mark_version=mark_version, tag=created_tags[1])), 0)
        self.assertEqual(len(ReportSafeTag.objects.filter(report__root__job=self.job, report__parent=None)), 1)
        self.assertEqual(len(ReportSafeTag.objects.filter(report__root__job=self.job, report__id=safe.parent_id)), 1)
        try:
            srt = SafeReportTag.objects.get(report=safe, tag=created_tags[0])
            self.assertEqual(srt.number, 1)
        except ObjectDoesNotExist:
            self.fail('Reports tags cache was not filled')
        self.assertEqual(len(SafeReportTag.objects.filter(report=safe, tag=created_tags[1])), 0)

        # Associations changes
        response = self.client.get('/marks/safe/association_changes/%s/' % cache_id)
        self.assertEqual(response.status_code, 200)

        # Safe marks list page
        response = self.client.get(reverse('marks:list', args=['safe']))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('marks:mark', args=['safe', mark.id]))
        self.assertEqual(response.status_code, 200)

        # Inline mark form
        response = self.client.get('/marks/safe/%s/edit/inline/' % mark.id)
        self.assertEqual(response.status_code, 200)

        # Confirm/unconfirm association
        # Mark is automatically associated after its changes
        self.assertEqual(MarkSafeReport.objects.filter(mark=mark, report=safe, type=ASSOCIATION_TYPE[0][0]).count(), 1)
        response = self.client.post('/marks/association/safe/%s/%s/unconfirm/' % (safe.pk, mark.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(MarkSafeReport.objects.filter(mark=mark, report=safe, type=ASSOCIATION_TYPE[2][0]).count(), 1)
        response = self.client.post('/marks/association/safe/%s/%s/confirm/' % (safe.pk, mark.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(MarkSafeReport.objects.filter(mark=mark, report=safe, type=ASSOCIATION_TYPE[1][0]).count(), 1)

        # Like/dislike association
        response = self.client.post('/marks/association/safe/%s/%s/like/' % (safe.id, mark.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(SafeAssociationLike.objects.filter(
            association__report=safe, association__mark=mark, dislike=False
        ).count(), 1)
        response = self.client.post('/marks/association/safe/%s/%s/dislike/' % (safe.id, mark.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(SafeAssociationLike.objects.filter(
            association__report=safe, association__mark=mark, dislike=True
        ).count(), 1)
        self.assertEqual(SafeAssociationLike.objects.filter(
            association__report=safe, association__mark=mark, dislike=False
        ).count(), 0)

        # Download mark
        response = self.client.get(reverse('marks:safe-download', args=[mark.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(response['Content-Type'], {'application/x-zip-compressed', 'application/zip'})
        with open(os.path.join(settings.MEDIA_ROOT, self.safe_archive), mode='wb') as fp:
            for content in response.streaming_content:
                fp.write(content)

        # Download mark in preset format
        response = self.client.get(reverse('marks:safe-download-preset', args=[mark.pk]))
        self.assertEqual(response.status_code, 200)

        # Delete mark
        response = self.client.post('/marks/delete/', {'type': 'safe', 'ids': json.dumps([mark.id])})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(MarkSafe.objects.all()), 0)
        self.assertEqual(len(MarkSafeReport.objects.all()), 0)
        self.assertEqual(ReportSafe.objects.all().first().verdict, SAFE_VERDICTS[4][0])

        # Upload mark
        with open(os.path.join(settings.MEDIA_ROOT, self.safe_archive), mode='rb') as fp:
            response = self.client.post('/marks/upload/', {'file': fp})
            fp.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertIn('id', res)
        self.assertEqual(res.get('type'), 'safe')
        self.assertEqual(len(MarkSafe.objects.all()), 1)
        try:
            newmark = MarkSafe.objects.get(pk=res['id'])
        except ObjectDoesNotExist:
            self.fail('Mark was not uploaded')
        self.assertEqual(newmark.type, MARK_TYPE[2][0])
        self.assertEqual(newmark.verdict, MARK_SAFE[2][0])
        self.assertEqual(newmark.version, 2)
        self.assertEqual(newmark.description, 'New mark description')
        self.assertEqual(newmark.is_modifiable, True)
        self.assertEqual(len(newmark.versions.all()), 2)
        newmark_version = MarkSafeHistory.objects.filter(mark=newmark).order_by('-version').first()
        self.assertEqual(newmark_version.version, 2)
        self.assertEqual(newmark_version.verdict, mark.verdict)
        self.assertEqual(newmark_version.author.username, 'manager')
        self.assertEqual(newmark_version.description, mark.description)
        self.assertEqual(newmark_version.comment, 'Change 1')
        self.assertEqual(ReportSafe.objects.get(pk=safe.pk).verdict, SAFE_VERDICTS[2][0])
        self.assertEqual(len(MarkSafeReport.objects.filter(mark=newmark, report=safe)), 1)
        self.assertEqual(len(MarkSafeReport.objects.filter(report=safe)), 1)
        self.assertEqual(len(MarkSafeTag.objects.filter(mark_version=newmark_version, tag=created_tags[0])), 1)
        self.assertEqual(len(MarkSafeTag.objects.filter(mark_version=newmark_version, tag=created_tags[1])), 0)
        self.assertEqual(len(ReportSafeTag.objects.filter(report__root__job=self.job, report__parent=None)), 1)
        self.assertEqual(len(ReportSafeTag.objects.filter(report__root__job=self.job, report__id=safe.parent_id)), 1)

        # Some more mark changes
        for i in range(3, 6):
            response = self.client.post(reverse('marks:mark_form', args=['safe', newmark.pk, 'edit']), {
                'data': json.dumps({
                    'description': 'New mark description',
                    'is_modifiable': True,
                    'verdict': MARK_SAFE[2][0],
                    'status': MARK_STATUS[2][0],
                    'tags': [created_tags[0].pk],
                    'attrs': compare_attrs,
                    'comment': 'Change %s' % i
                })
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/json')
            self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        self.assertEqual(len(MarkSafeHistory.objects.filter(mark=newmark)), 5)

        # Get 3d version data
        response = self.client.get(reverse('marks:mark_form', args=['safe', newmark.pk, 'edit']),
                                   params={'version': 3})
        self.assertEqual(response.status_code, 200)

        # Compare 1st and 4th versions
        response = self.client.post('/marks/safe/%s/compare_versions/' % newmark.pk, {'v1': 1, 'v2': 4})
        self.assertEqual(response.status_code, 200)

        # Remove 2nd and 4th versions
        response = self.client.post('/marks/safe/%s/remove_versions/' % newmark.pk, {'versions': json.dumps([2, 4])})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('success', res)
        self.assertEqual(len(MarkSafeHistory.objects.filter(mark=newmark)), 3)

        # Reports' lists pages
        root_comp = ReportComponent.objects.get(root__job_id=self.job.pk, parent=None)
        response = self.client.get('%s?tag=%s' % (reverse('reports:safes', args=[root_comp.pk]), created_tags[0].pk))
        self.assertIn(response.status_code, {200, 302})
        response = self.client.get('%s?tag=%s' % (reverse('reports:safes', args=[root_comp.pk]), created_tags[1].pk))
        self.assertIn(response.status_code, {200, 302})
        response = self.client.get(
            '%s?verdict=%s' % (reverse('reports:safes', args=[root_comp.pk]), SAFE_VERDICTS[0][0])
        )
        self.assertIn(response.status_code, {200, 302})
        response = self.client.get(
            '%s?verdict=%s' % (reverse('reports:safes', args=[root_comp.pk]), SAFE_VERDICTS[2][0])
        )
        self.assertIn(response.status_code, {200, 302})

        # Download all marks
        response = self.client.get('/marks/api/download-all/')
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response['Content-Type'], 'application/json')
        with open(os.path.join(settings.MEDIA_ROOT, self.all_marks_arch), mode='wb') as fp:
            for content in response.streaming_content:
                fp.write(content)

        # Delete all safe marks
        self.client.post('/marks/delete/', {
            'type': 'safe', 'ids': json.dumps(list(MarkSafe.objects.values_list('id', flat=True)))
        })
        self.assertEqual(MarkSafe.objects.count(), 0)

        # All verdicts must be "safe unmarked"
        self.assertEqual(
            len(ReportSafe.objects.filter(verdict=SAFE_VERDICTS[4][0])),
            len(ReportSafe.objects.all())
        )
        self.assertEqual(len(MarkSafeReport.objects.all()), 0)

        # Upload all marks
        with open(os.path.join(settings.MEDIA_ROOT, self.all_marks_arch), mode='rb') as fp:
            response = self.client.post('/marks/upload-all/', {'delete': 1, 'file': fp})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(int(json.loads(str(response.content, encoding='utf8'))['fail']), 0)
        self.assertEqual(int(json.loads(str(response.content, encoding='utf8'))['safe']), 1)

    def test_unsafe(self):
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[3][0])

        # Delete populated marks
        response = self.client.post('/marks/delete/', {
            'type': 'safe', 'ids': json.dumps(list(MarkSafe.objects.values_list('id', flat=True)))
        })
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/marks/delete/', {
            'type': 'unsafe', 'ids': json.dumps(list(MarkUnsafe.objects.values_list('id', flat=True)))
        })
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/marks/delete/', {
            'type': 'unknown', 'ids': json.dumps(list(MarkUnknown.objects.values_list('id', flat=True)))
        })
        self.assertEqual(response.status_code, 200)

        # Create 5 unsafe tags
        created_tags = []
        response = self.client.post('/marks/tags/save_tag/', {
            'action': 'create', 'tag_type': 'unsafe', 'parent_id': '0', 'name': 'test:unsafe:tag:1',
            'description': 'Test unsafe tag description'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        try:
            created_tags.append(UnsafeTag.objects.get(tag='test:unsafe:tag:1'))
        except ObjectDoesNotExist:
            self.fail('Unsafe tag was not created')
        self.assertEqual(created_tags[0].description, 'Test unsafe tag description')
        self.assertEqual(created_tags[0].parent, None)

        for i in range(2, 6):
            self.client.post('/marks/tags/save_tag/', {
                'action': 'create', 'tag_type': 'unsafe',
                'parent_id': created_tags[i - 2].pk, 'name': 'test:unsafe:tag:%s' % i, 'description': ''
            })
            created_tags.append(UnsafeTag.objects.get(tag='test:unsafe:tag:%s' % i))
            self.assertEqual(created_tags[i - 1].parent, created_tags[i - 2])

        # Get tag parents for editing tag 'test:unsafe:tag:3'
        response = self.client.post('/marks/tags/unsafe/get_tag_data/', {'tag_id': created_tags[2].pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Get tag parents for creating new tag
        response = self.client.post('/marks/tags/unsafe/get_tag_data/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Edit 5th tag
        response = self.client.post('/marks/tags/save_tag/', {
            'action': 'edit', 'tag_type': 'unsafe', 'parent_id': created_tags[2].pk,
            'name': 'test:unsafe:tag:5', 'tag_id': created_tags[4].pk,
            'description': 'Test unsafe tag 5 description'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        try:
            created_tags[4] = UnsafeTag.objects.get(tag='test:unsafe:tag:5')
        except ObjectDoesNotExist:
            self.fail('Tag 5 was not found after editing')
        self.assertEqual(created_tags[4].parent, created_tags[2])
        self.assertEqual(created_tags[4].description, 'Test unsafe tag 5 description')

        # Remove 3d tag and check that its children (tag4 and tag5) are also removed
        response = self.client.post('/marks/tags/unsafe/delete/%s/' % created_tags[2].pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(
            len(UnsafeTag.objects.filter(tag__in=['test:unsafe:tag:3', 'test:unsafe:tag:4', 'test:unsafe:tag:5'])), 0
        )
        del created_tags[2:]

        # Get tags data (for edit/create mark page). Just check that there is no error in response.
        response = self.client.post('/marks/unsafe/tags_data/', {'selected_tags': json.dumps([created_tags[1].pk])})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Download tags
        response = self.client.get(reverse('marks:download_tags', args=['unsafe']))
        self.assertEqual(response.status_code, 200)
        with open(os.path.join(settings.MEDIA_ROOT, self.test_tagsfile), mode='wb') as fp:
            for chunk in response.streaming_content:
                fp.write(chunk)
        UnsafeTag.objects.all().delete()

        # Upload tags
        with open(os.path.join(settings.MEDIA_ROOT, self.test_tagsfile), mode='rb') as fp:
            response = self.client.post('/marks/tags/unsafe/upload/', {'file': fp})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        for i in range(0, len(created_tags)):
            try:
                created_tags[i] = UnsafeTag.objects.get(tag=created_tags[i].tag)
            except ObjectDoesNotExist:
                self.fail("Tags weren't uploaded")

        # Tags tree page
        response = self.client.get(reverse('marks:tags', args=['unsafe']))
        self.assertEqual(response.status_code, 200)

        # Get report
        unsafe = ReportUnsafe.objects.filter(root__job_id=self.job.pk).first()
        self.assertIsNotNone(unsafe)

        # Inline mark form
        response = self.client.get('/marks/unsafe/%s/create/inline/' % unsafe.id)
        self.assertEqual(response.status_code, 200)

        # Create mark page
        response = self.client.get(reverse('marks:mark_form', args=['unsafe', unsafe.pk, 'create']))
        self.assertEqual(response.status_code, 200)

        # Error trace compare function description
        try:
            compare_f = MarkUnsafeCompare.objects.get(name=DEFAULT_COMPARE)
        except ObjectDoesNotExist:
            self.fail("Population hasn't created compare error trace functions")
        response = self.client.post('/marks/get_func_description/%s/' % compare_f.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Save mark
        compare_attrs = list({'is_compare': associate, 'attr': a_name}
                             for a_name, associate in unsafe.attrs.values_list('attr__name__name', 'associate'))
        response = self.client.post(reverse('marks:mark_form', args=['unsafe', unsafe.pk, 'create']), {
            'data': json.dumps({
                'compare_id': compare_f.pk,
                'description': 'Mark description',
                'is_modifiable': True,
                'verdict': MARK_UNSAFE[1][0],
                'status': MARK_STATUS[2][0],
                'tags': [created_tags[0].pk],
                'attrs': compare_attrs
            })
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('cache_id', res)
        cache_id = res['cache_id']

        # Check mark's tables
        try:
            mark = MarkUnsafe.objects.get(job=self.job, author__username='manager')
        except ObjectDoesNotExist:
            self.fail('Mark was not created')
        self.assertEqual(mark.type, MARK_TYPE[0][0])
        self.assertEqual(mark.verdict, MARK_UNSAFE[1][0])
        self.assertEqual(mark.status, MARK_STATUS[2][0])
        self.assertEqual(mark.version, 1)
        self.assertEqual(mark.description, 'Mark description')
        self.assertEqual(mark.function.name, DEFAULT_COMPARE)
        self.assertEqual(mark.is_modifiable, True)
        self.assertEqual(len(mark.versions.all()), 1)
        mark_version = MarkUnsafeHistory.objects.get(mark=mark)
        self.assertEqual(mark_version.verdict, mark.verdict)
        self.assertEqual(mark_version.version, 1)
        self.assertEqual(mark_version.author.username, 'manager')
        self.assertEqual(mark_version.status, mark.status)
        self.assertEqual(mark_version.description, mark.description)
        for mark_attr in mark_version.attrs.all().select_related('attr__name'):
            self.assertIn({'is_compare': mark_attr.is_compare, 'attr': mark_attr.attr.name.name}, compare_attrs)
        self.assertEqual(ReportUnsafe.objects.get(pk=unsafe.pk).verdict, UNSAFE_VERDICTS[1][0])
        self.assertEqual(len(MarkUnsafeReport.objects.filter(mark=mark, report=unsafe, type=ASSOCIATION_TYPE[1][0])), 1)
        self.assertEqual(len(MarkUnsafeTag.objects.filter(mark_version=mark_version, tag=created_tags[0])), 1)
        try:
            rst = ReportUnsafeTag.objects.get(report__root__job=self.job, report__parent=None, tag=created_tags[0])
            # The number of unsafes for root report with specified tag equals the number of marked unsafes
            self.assertEqual(rst.number, len(ReportUnsafe.objects.filter(verdict=UNSAFE_VERDICTS[1][0])))
            rst = ReportUnsafeTag.objects.get(
                report__root__job=self.job, report_id=unsafe.parent_id, tag=created_tags[0]
            )
            # The number of unsafes for parent report (for unsafe) with specified tag
            # equals 1 due to only one unsafe is child for report
            self.assertEqual(rst.number, 1)
            srt = UnsafeReportTag.objects.get(report=unsafe, tag=created_tags[0])
            self.assertEqual(srt.number, 1)
        except ObjectDoesNotExist:
            self.fail('Reports tags cache was not filled')

        # Associations changes
        response = self.client.get('/marks/unsafe/association_changes/%s/' % cache_id)
        self.assertEqual(response.status_code, 200)

        # Edit mark page
        response = self.client.get(reverse('marks:mark_form', args=['unsafe', mark.pk, 'edit']))
        self.assertEqual(response.status_code, 200)

        # Edit mark
        with mark_version.error_trace.file as fp:
            error_trace = fp.read().decode('utf8')
        response = self.client.post(reverse('marks:mark_form', args=['unsafe', mark.pk, 'edit']), {
            'data': json.dumps({
                'compare_id': compare_f.pk,
                'description': 'New mark description',
                'is_modifiable': True,
                'verdict': MARK_UNSAFE[2][0],
                'status': MARK_STATUS[2][0],
                'tags': [created_tags[1].pk],
                'attrs': compare_attrs,
                'comment': 'Change 1',
                'error_trace': error_trace
            })
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('cache_id', res)
        cache_id = res['cache_id']

        # Check mark's tables
        try:
            mark = MarkUnsafe.objects.get(job=self.job, author__username='manager')
        except ObjectDoesNotExist:
            self.fail('Mark was not created')
        self.assertEqual(mark.verdict, MARK_UNSAFE[2][0])
        self.assertEqual(mark.version, 2)
        self.assertEqual(mark.description, 'New mark description')
        self.assertEqual(mark.is_modifiable, True)
        self.assertEqual(len(mark.versions.all()), 2)
        mark_version = MarkUnsafeHistory.objects.filter(mark=mark).order_by('-version').first()
        self.assertEqual(mark_version.version, 2)
        self.assertEqual(mark_version.verdict, mark.verdict)
        self.assertEqual(mark_version.author.username, 'manager')
        self.assertEqual(mark_version.description, mark.description)
        self.assertEqual(mark_version.comment, 'Change 1')
        self.assertEqual(ReportUnsafe.objects.get(pk=unsafe.pk).verdict, SAFE_VERDICTS[2][0])
        self.assertEqual(len(MarkUnsafeReport.objects.filter(mark=mark, report=unsafe)), 1)
        self.assertEqual(len(MarkUnsafeTag.objects.filter(mark_version=mark_version, tag=created_tags[0])), 1)
        self.assertEqual(len(MarkUnsafeTag.objects.filter(mark_version=mark_version, tag=created_tags[1])), 1)
        self.assertEqual(len(ReportUnsafeTag.objects.filter(report__root__job=self.job, report__parent=None)), 2)
        self.assertEqual(len(
            ReportUnsafeTag.objects.filter(report__root__job=self.job, report__id=unsafe.parent_id)
        ), 2)
        try:
            urt = UnsafeReportTag.objects.get(report=unsafe, tag=created_tags[0])
            self.assertEqual(urt.number, 1)
            urt = UnsafeReportTag.objects.get(report=unsafe, tag=created_tags[1])
            self.assertEqual(urt.number, 1)
        except ObjectDoesNotExist:
            self.fail('Reports tags cache was not filled')

        # Associations changes
        response = self.client.get('/marks/unsafe/association_changes/%s/' % cache_id)
        self.assertEqual(response.status_code, 200)

        # Unsafe marks list page
        response = self.client.get(reverse('marks:list', args=['unsafe']))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('marks:mark', args=['unsafe', mark.id]))
        self.assertEqual(response.status_code, 200)

        # Inline mark form
        response = self.client.get('/marks/unsafe/%s/edit/inline/' % mark.id)
        self.assertEqual(response.status_code, 200)

        # Confirm/unconfirm association
        # Mark is automatically associated after its changes
        self.assertEqual(
            MarkUnsafeReport.objects.filter(mark=mark, report=unsafe, type=ASSOCIATION_TYPE[0][0]).count(), 1
        )
        response = self.client.post('/marks/association/unsafe/%s/%s/unconfirm/' % (unsafe.pk, mark.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(MarkUnsafeReport.objects.filter(
            mark=mark, report=unsafe, type=ASSOCIATION_TYPE[2][0]).count(), 1)
        response = self.client.post('/marks/association/unsafe/%s/%s/confirm/' % (unsafe.pk, mark.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(MarkUnsafeReport.objects.filter(
            mark=mark, report=unsafe, type=ASSOCIATION_TYPE[1][0]).count(), 1)

        # Like/dislike association
        response = self.client.post('/marks/association/unsafe/%s/%s/like/' % (unsafe.id, mark.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(UnsafeAssociationLike.objects.filter(
            association__report=unsafe, association__mark=mark, dislike=False
        ).count(), 1)
        response = self.client.post('/marks/association/unsafe/%s/%s/dislike/' % (unsafe.id, mark.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(UnsafeAssociationLike.objects.filter(
            association__report=unsafe, association__mark=mark, dislike=True
        ).count(), 1)
        self.assertEqual(UnsafeAssociationLike.objects.filter(
            association__report=unsafe, association__mark=mark, dislike=False
        ).count(), 0)

        # Download mark
        response = self.client.get(reverse('marks:unsafe-download', args=[mark.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(response['Content-Type'], {'application/x-zip-compressed', 'application/zip'})
        with open(os.path.join(settings.MEDIA_ROOT, self.unsafe_archive), mode='wb') as fp:
            for content in response.streaming_content:
                fp.write(content)

        # Download mark in preset format
        response = self.client.get(reverse('marks:unsafe-download-preset', args=[mark.pk]))
        self.assertEqual(response.status_code, 200)

        # Delete mark
        response = self.client.post('/marks/delete/', {'type': 'unsafe', 'ids': json.dumps([mark.id])})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(len(MarkUnsafe.objects.all()), 0)
        self.assertEqual(len(MarkUnsafeReport.objects.all()), 0)
        self.assertEqual(ReportUnsafe.objects.all().first().verdict, UNSAFE_VERDICTS[5][0])

        # Upload mark
        with open(os.path.join(settings.MEDIA_ROOT, self.unsafe_archive), mode='rb') as fp:
            response = self.client.post('/marks/upload/', {'file': fp})
            fp.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertIn('id', res)
        self.assertEqual(res.get('type'), 'unsafe')
        self.assertEqual(len(MarkUnsafe.objects.all()), 1)
        try:
            newmark = MarkUnsafe.objects.get(pk=res['id'])
        except ObjectDoesNotExist:
            self.fail('Mark was not uploaded')
        self.assertEqual(newmark.type, MARK_TYPE[2][0])
        self.assertEqual(newmark.verdict, MARK_UNSAFE[2][0])
        self.assertEqual(newmark.version, 2)
        self.assertEqual(newmark.description, 'New mark description')
        self.assertEqual(newmark.is_modifiable, True)
        self.assertEqual(len(newmark.versions.all()), 2)
        newmark_version = MarkUnsafeHistory.objects.filter(mark=newmark).order_by('-version').first()
        self.assertEqual(newmark_version.version, 2)
        self.assertEqual(newmark_version.verdict, mark.verdict)
        self.assertEqual(newmark_version.author.username, 'manager')
        self.assertEqual(newmark_version.description, mark.description)
        self.assertEqual(newmark_version.comment, 'Change 1')
        self.assertEqual(ReportUnsafe.objects.get(pk=unsafe.pk).verdict, UNSAFE_VERDICTS[2][0])
        self.assertEqual(len(MarkUnsafeReport.objects.filter(mark=newmark, report=unsafe)), 1)
        self.assertEqual(len(MarkUnsafeReport.objects.filter(report=unsafe)), 1)
        self.assertEqual(len(MarkUnsafeTag.objects.filter(mark_version=newmark_version, tag=created_tags[0])), 1)
        self.assertEqual(len(MarkUnsafeTag.objects.filter(mark_version=newmark_version, tag=created_tags[1])), 1)
        # The tag has parent which is also added to mark
        self.assertEqual(
            len(ReportUnsafeTag.objects.filter(report__root__job=self.job, report__parent=None)),
            len(ReportUnsafe.objects.filter(verdict=UNSAFE_VERDICTS[2][0])) * 2
        )
        self.assertEqual(len(ReportUnsafeTag.objects.filter(
            report__root__job=self.job, report__id=unsafe.parent_id
        )), 2)

        # Some more mark changes
        for i in range(3, 6):
            response = self.client.post(reverse('marks:mark_form', args=['unsafe', newmark.pk, 'edit']), {
                'data': json.dumps({
                    'compare_id': compare_f.pk,
                    'description': 'New mark description',
                    'is_modifiable': True,
                    'verdict': MARK_UNSAFE[2][0],
                    'status': MARK_STATUS[2][0],
                    'tags': [created_tags[0].pk],
                    'attrs': compare_attrs,
                    'comment': 'Change %s' % i,
                    'error_trace': error_trace
                })
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/json')
            self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(
            len(ReportUnsafeTag.objects.filter(report__root__job=self.job, report__parent=None)),
            len(ReportUnsafe.objects.filter(verdict=UNSAFE_VERDICTS[2][0]))
        )

        self.assertEqual(len(MarkUnsafeHistory.objects.filter(mark=newmark)), 5)

        # Get 3d version data
        response = self.client.get(reverse('marks:mark_form', args=['unsafe', newmark.pk, 'edit']),
                                   params={'version': 3})
        self.assertEqual(response.status_code, 200)

        # Compare 1st and 4th versions
        response = self.client.post('/marks/unsafe/%s/compare_versions/' % newmark.pk, {'v1': 1, 'v2': 4})
        self.assertEqual(response.status_code, 200)

        # Remove 2nd and 4th versions
        response = self.client.post('/marks/unsafe/%s/remove_versions/' % newmark.pk, {'versions': json.dumps([2, 4])})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('success', res)
        self.assertEqual(len(MarkUnsafeHistory.objects.filter(mark=newmark)), 3)

        # Reports' lists pages
        root_comp = ReportComponent.objects.get(root__job_id=self.job.pk, parent=None)
        response = self.client.get('%s?tag=%s' % (reverse('reports:unsafes', args=[root_comp.pk]), created_tags[0].pk))
        self.assertIn(response.status_code, {200, 302})
        response = self.client.get('%s?tag=%s' % (reverse('reports:unsafes', args=[root_comp.pk]), created_tags[1].pk))
        self.assertIn(response.status_code, {200, 302})
        response = self.client.get(
            '%s?verdict=%s' % (reverse('reports:unsafes', args=[root_comp.pk]), UNSAFE_VERDICTS[0][0])
        )
        self.assertIn(response.status_code, {200, 302})
        response = self.client.get(
            '%s?verdict=%s' % (reverse('reports:unsafes', args=[root_comp.pk]), UNSAFE_VERDICTS[2][0])
        )
        self.assertIn(response.status_code, {200, 302})

        # Download all marks
        response = self.client.get('/marks/api/download-all/')
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response['Content-Type'], 'application/json')
        with open(os.path.join(settings.MEDIA_ROOT, self.all_marks_arch), mode='wb') as fp:
            for content in response.streaming_content:
                fp.write(content)

        # Delete all unsafe marks
        self.client.post('/marks/delete/', {
            'type': 'unsafe', 'ids': json.dumps(list(MarkUnsafe.objects.values_list('id', flat=True)))
        })
        self.assertEqual(MarkUnsafe.objects.count(), 0)
        # All verdicts must be "unsafe unmarked"
        self.assertEqual(
            ReportUnsafe.objects.filter(verdict=UNSAFE_VERDICTS[5][0]).count(), ReportUnsafe.objects.all().count()
        )
        self.assertEqual(MarkUnsafeReport.objects.count(), 0)

        # Upload all marks
        with open(os.path.join(settings.MEDIA_ROOT, self.all_marks_arch), mode='rb') as fp:
            response = self.client.post('/marks/upload-all/', {'delete': 1, 'file': fp})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(int(json.loads(str(response.content, encoding='utf8'))['fail']), 0)
        self.assertEqual(int(json.loads(str(response.content, encoding='utf8'))['unsafe']), 1)

    def test_unknown(self):
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[3][0])

        # Do not remove populated safe/unsafe marks as there are no problems with uploading populated marks
        response = self.client.post('/marks/delete/', {
            'type': 'unknown', 'ids': json.dumps(list(MarkUnknown.objects.values_list('id', flat=True)))
        })
        self.assertEqual(response.status_code, 200)

        # Get report
        unknown = None

        for u in ReportUnknown.objects.filter(root__job_id=self.job.pk):
            afc = ArchiveFileContent(u, 'problem_description', PROBLEM_DESC_FILE)
            if afc.content == b'KeyError: \'attr\' was not found.':
                unknown = u
                break
        if unknown is None:
            self.fail("Unknown with needed problem description was not found in test job decision")
        parent = ReportComponent.objects.get(pk=unknown.parent_id)

        # Inline mark form
        response = self.client.get('/marks/unknown/%s/create/inline/' % unknown.id)
        self.assertEqual(response.status_code, 200)

        # Create mark page
        response = self.client.get(reverse('marks:mark_form', args=['unknown', unknown.pk, 'create']))
        self.assertEqual(response.status_code, 200)

        # Check regexp function
        response = self.client.post('/marks/check-unknown-mark/%s/' % unknown.pk, {
            'function': "KeyError:\s'(\S*)'\swas\snot\sfound\.",
            'pattern': 'KeyE: {0}',
            'is_regex': 'true'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Save mark
        response = self.client.post(reverse('marks:mark_form', args=['unknown', unknown.pk, 'create']), {
            'data': json.dumps({
                'description': 'Mark description',
                'is_modifiable': True,
                'status': MARK_STATUS[2][0],
                'function': "KeyError:\s'(\S*)'\swas\snot\sfound\.",
                'problem': 'KeyE: {0}',
                'link': 'http://mysite.com/',
                'is_regexp': True
            })
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('cache_id', res)
        cache_id = res['cache_id']

        # Check mark's tables
        try:
            mark = MarkUnknown.objects.get(job=self.job, author__username='manager')
        except ObjectDoesNotExist:
            self.fail('Mark was not created')
        self.assertEqual(mark.type, MARK_TYPE[0][0])
        self.assertEqual(mark.status, MARK_STATUS[2][0])
        self.assertEqual(mark.version, 1)
        self.assertEqual(mark.description, 'Mark description')
        self.assertEqual(mark.link, 'http://mysite.com/')
        self.assertEqual(mark.problem_pattern, 'KeyE: {0}')
        self.assertEqual(mark.function, "KeyError:\s'(\S*)'\swas\snot\sfound\.")
        self.assertEqual(mark.is_modifiable, True)
        self.assertEqual(len(mark.versions.all()), 1)
        mark_version = MarkUnknownHistory.objects.get(mark=mark)
        self.assertEqual(mark_version.version, 1)
        self.assertEqual(mark_version.author.username, 'manager')
        self.assertEqual(mark_version.status, mark.status)
        self.assertEqual(mark_version.description, mark.description)
        self.assertEqual(mark_version.link, mark.link)
        self.assertEqual(mark_version.problem_pattern, mark.problem_pattern)
        self.assertEqual(mark_version.function, mark.function)
        self.assertEqual(len(UnknownProblem.objects.filter(name='KeyE: attr')), 1)
        self.assertEqual(len(MarkUnknownReport.objects.filter(mark=mark, report=unknown)), 1)

        # Associations changes
        response = self.client.get('/marks/unknown/association_changes/%s/' % cache_id)
        self.assertEqual(response.status_code, 200)

        # Edit mark page
        response = self.client.get(reverse('marks:mark_form', args=['unknown', mark.pk, 'edit']))
        self.assertEqual(response.status_code, 200)

        # Edit mark
        response = self.client.post(reverse('marks:mark_form', args=['unknown', mark.pk, 'edit']), {
            'data': json.dumps({
                'description': 'New mark description',
                'is_modifiable': True,
                'status': MARK_STATUS[1][0],
                'function': "KeyError:\s'(\S*)'.*",
                'problem': 'KeyE: {0}',
                'link': 'http://mysite.com/',
                'is_regexp': True,
                'comment': 'Change 1'
            })
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('cache_id', res)
        cache_id = res['cache_id']

        # Check mark's tables
        try:
            mark = MarkUnknown.objects.get(job=self.job, author__username='manager')
        except ObjectDoesNotExist:
            self.fail('Mark was not created')
        self.assertEqual(mark.version, 2)
        self.assertEqual(mark.description, 'New mark description')
        self.assertEqual(mark.is_modifiable, True)
        self.assertEqual(len(mark.versions.all()), 2)
        mark_version = MarkUnknownHistory.objects.filter(mark=mark).order_by('-version').first()
        self.assertEqual(mark_version.version, 2)
        self.assertEqual(mark_version.author.username, 'manager')
        self.assertEqual(mark_version.description, mark.description)
        self.assertEqual(mark_version.comment, 'Change 1')
        self.assertEqual(mark_version.link, mark.link)
        self.assertEqual(mark_version.problem_pattern, mark.problem_pattern)
        self.assertEqual(mark_version.function, mark.function)
        self.assertEqual(len(UnknownProblem.objects.filter(name='KeyE: attr')), 1)
        self.assertEqual(len(MarkUnknownReport.objects.filter(mark=mark, report=unknown)), 1)

        # Associations changes
        response = self.client.get('/marks/unknown/association_changes/%s/' % cache_id)
        self.assertEqual(response.status_code, 200)

        # Unknown marks list page
        response = self.client.get(reverse('marks:list', args=['unknown']))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('marks:mark', args=['unknown', mark.id]))
        self.assertEqual(response.status_code, 200)

        # Inline mark eddit form
        response = self.client.get('/marks/unknown/%s/edit/inline/' % mark.id)
        self.assertEqual(response.status_code, 200)

        # Confirm/unconfirm association
        # Mark is automatically associated after its changes
        self.assertEqual(
            MarkUnknownReport.objects.filter(mark=mark, report=unknown, type=ASSOCIATION_TYPE[0][0]).count(), 1
        )
        response = self.client.post('/marks/association/unknown/%s/%s/unconfirm/' % (unknown.pk, mark.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(MarkUnknownReport.objects.filter(
            mark=mark, report=unknown, type=ASSOCIATION_TYPE[2][0]).count(), 1)
        response = self.client.post('/marks/association/unknown/%s/%s/confirm/' % (unknown.pk, mark.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(MarkUnknownReport.objects.filter(
            mark=mark, report=unknown, type=ASSOCIATION_TYPE[1][0]).count(), 1)

        # Like/dislike association
        response = self.client.post('/marks/association/unknown/%s/%s/like/' % (unknown.id, mark.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(UnknownAssociationLike.objects.filter(
            association__report=unknown, association__mark=mark, dislike=False
        ).count(), 1)
        response = self.client.post('/marks/association/unknown/%s/%s/dislike/' % (unknown.id, mark.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(UnknownAssociationLike.objects.filter(
            association__report=unknown, association__mark=mark, dislike=True
        ).count(), 1)
        self.assertEqual(UnknownAssociationLike.objects.filter(
            association__report=unknown, association__mark=mark, dislike=False
        ).count(), 0)

        # Download mark
        response = self.client.get(reverse('marks:unknown-download', args=[mark.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(response['Content-Type'], {'application/x-zip-compressed', 'application/zip'})
        with open(os.path.join(settings.MEDIA_ROOT, self.unknown_archive), mode='wb') as fp:
            for content in response.streaming_content:
                fp.write(content)

        # Download mark in preset format
        response = self.client.get(reverse('marks:unknown-download-preset', args=[mark.pk]))
        self.assertEqual(response.status_code, 200)

        # Delete mark
        response = self.client.post('/marks/delete/', {'type': 'unknown', 'ids': json.dumps([mark.id])})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(len(MarkUnknown.objects.all()), 0)
        self.assertEqual(len(MarkUnknownReport.objects.all()), 0)

        # Upload mark
        with open(os.path.join(settings.MEDIA_ROOT, self.unknown_archive), mode='rb') as fp:
            response = self.client.post('/marks/upload/', {'file': fp})
            fp.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertIn('id', res)
        self.assertEqual(res.get('type'), 'unknown')
        try:
            newmark = MarkUnknown.objects.get(pk=res['id'])
        except ObjectDoesNotExist:
            self.fail('Mark was not uploaded')
        self.assertEqual(newmark.version, 2)
        self.assertEqual(newmark.description, 'New mark description')
        self.assertEqual(newmark.is_modifiable, True)
        self.assertEqual(len(newmark.versions.all()), 2)
        newmark_version = MarkUnknownHistory.objects.filter(mark=newmark).order_by('-version').first()
        self.assertEqual(newmark_version.version, 2)
        self.assertEqual(newmark_version.author.username, 'manager')
        self.assertEqual(newmark_version.comment, 'Change 1')
        self.assertEqual(len(MarkUnknownReport.objects.filter(mark=newmark, report=unknown)), 1)
        self.assertEqual(len(MarkUnknownReport.objects.filter(report=unknown)), 1)
        self.assertEqual(len(UnknownProblem.objects.filter(name='KeyE: attr')), 1)

        # Check non-regexp function
        response = self.client.post('/marks/check-unknown-mark/%s/' % unknown.pk, {
            'function': "KeyError: 'attr' was not found.",
            'pattern': 'KeyE: attr',
            'is_regex': 'false'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Non-regexp function change
        response = self.client.post(reverse('marks:mark_form', args=['unknown', newmark.pk, 'edit']), {
            'data': json.dumps({
                'description': 'New mark description',
                'is_modifiable': True,
                'status': MARK_STATUS[2][0],
                'function': "KeyError: 'attr' was not found.",
                'problem': 'KeyE: attr',
                'link': 'http://mysite.com/',
                'is_regexp': False,
                'comment': 'Change 3'
            })
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        # Some more mark changes
        for i in range(4, 6):
            response = self.client.post(reverse('marks:mark_form', args=['unknown', newmark.pk, 'edit']), {
                'data': json.dumps({
                    'description': 'No regexp',
                    'is_modifiable': True,
                    'status': MARK_STATUS[2][0],
                    'function': "KeyError:.*'(\S*)'",
                    'problem': 'KeyE: {0}',
                    'link': 'http://mysite.com/',
                    'is_regexp': True,
                    'comment': 'Change %s' % i
                })
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/json')
            self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        self.assertEqual(len(MarkUnknownHistory.objects.filter(mark=newmark)), 5)

        # Get 3d version data
        response = self.client.get(reverse('marks:mark_form', args=['unknown', newmark.pk, 'edit']),
                                   params={'version': 3})
        self.assertEqual(response.status_code, 200)

        # Compare 1st and 4th versions
        response = self.client.post('/marks/unknown/%s/compare_versions/' % newmark.pk, {'v1': 1, 'v2': 4})
        self.assertEqual(response.status_code, 200)

        # Remove 2nd and 4th versions
        response = self.client.post('/marks/unknown/%s/remove_versions/' % newmark.pk, {'versions': json.dumps([2, 4])})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('success', res)
        self.assertEqual(len(MarkUnknownHistory.objects.filter(mark=newmark)), 3)

        # Reports' lists pages
        root_comp = ReportComponent.objects.get(root__job_id=self.job.pk, parent=None)
        response = self.client.get(
            '%s?component=%s' % (reverse('reports:unknowns', args=[root_comp.pk]), parent.component_id)
        )
        self.assertIn(response.status_code, {200, 302})
        try:
            problem_id = UnknownProblem.objects.get(name='KeyE: attr').pk
        except ObjectDoesNotExist:
            self.fail("Can't find unknown problem")
        response = self.client.get('%s?component=%s&problem=%s' % (
            reverse('reports:unknowns', args=[root_comp.pk]), parent.component_id, problem_id
        ))
        self.assertIn(response.status_code, {200, 302})

        # Download all marks
        response = self.client.get('/marks/api/download-all/')
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response['Content-Type'], 'application/json')
        with open(os.path.join(settings.MEDIA_ROOT, self.all_marks_arch), mode='wb') as fp:
            for content in response.streaming_content:
                fp.write(content)

        # Delete all marks
        self.client.post('/marks/delete/', {
            'type': 'unknown', 'ids': json.dumps(list(MarkUnknown.objects.values_list('id', flat=True)))
        })
        self.assertEqual(MarkUnknown.objects.count(), 0)

        # All verdicts must be "unknown unmarked"
        self.assertEqual(MarkUnknownReport.objects.all().count(), 0)

        # Upload all marks
        with open(os.path.join(settings.MEDIA_ROOT, self.all_marks_arch), mode='rb') as fp:
            response = self.client.post('/marks/upload-all/', {'delete': 1, 'file': fp})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(int(json.loads(str(response.content, encoding='utf8'))['fail']), 0)
        self.assertEqual(int(json.loads(str(response.content, encoding='utf8'))['unknown']), 1)

    def tearDown(self):
        if os.path.exists(os.path.join(settings.MEDIA_ROOT, self.safe_archive)):
            os.remove(os.path.join(settings.MEDIA_ROOT, self.safe_archive))
        if os.path.exists(os.path.join(settings.MEDIA_ROOT, self.unsafe_archive)):
            os.remove(os.path.join(settings.MEDIA_ROOT, self.unsafe_archive))
        if os.path.exists(os.path.join(settings.MEDIA_ROOT, self.unknown_archive)):
            os.remove(os.path.join(settings.MEDIA_ROOT, self.unknown_archive))
        if os.path.exists(os.path.join(settings.MEDIA_ROOT, self.test_tagsfile)):
            os.remove(os.path.join(settings.MEDIA_ROOT, self.test_tagsfile))
        if os.path.exists(os.path.join(settings.MEDIA_ROOT, self.all_marks_arch)):
            os.remove(os.path.join(settings.MEDIA_ROOT, self.all_marks_arch))
        super(TestMarks, self).tearDown()
