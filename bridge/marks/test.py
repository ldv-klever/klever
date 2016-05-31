import os
import json
from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from bridge.populate import populate_users
from bridge.settings import BASE_DIR, MEDIA_ROOT
from bridge.utils import KleverTestCase
from bridge.vars import JOB_STATUS, MARKS_COMPARE_ATTRS, SAFE_VERDICTS, UNSAFE_VERDICTS
from reports.test import DecideJobs, CHUNKS1
from marks.CompareTrace import DEFAULT_COMPARE
from marks.ConvertTrace import DEFAULT_CONVERT
from marks.models import *


REPORT_ARCHIVES = os.path.join(BASE_DIR, 'reports', 'test_files')


class TestMarks(KleverTestCase):
    def setUp(self):
        super(TestMarks, self).setUp()
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
        try:
            self.job = Job.objects.filter(~Q(parent=None))[0]
        except IndexError:
            self.job = Job.objects.all()[0]
        self.client.post('/jobs/ajax/fast_run_decision/', {'job_id': self.job.pk})
        DecideJobs('service', 'service', CHUNKS1)
        self.safe_archive = 'test_safemark.tar.gz'
        self.unsafe_archive = 'test_unsafemark.tar.gz'
        self.unknown_archive = 'test_unknownmark.tar.gz'

    def test_safe(self):
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[3][0])

        # Get report
        try:
            safe = ReportSafe.objects.filter(root__job_id=self.job.pk)[0]
        except IndexError:
            self.fail("Test job decision does not have safe report")

        # Create mark page
        response = self.client.get(reverse('marks:create_mark', args=['safe', safe.pk]))
        self.assertEqual(response.status_code, 200)

        # Save mark
        compare_attrs = []
        for a in safe.attrs.all():
            attr_data = {'is_compare': False, 'attr': a.attr.name.name}
            if a.attr.name in MARKS_COMPARE_ATTRS[self.job.type]:
                attr_data['is_compare'] = True
            compare_attrs.append(attr_data)
        response = self.client.post('/marks/ajax/save_mark/', {
            'savedata': json.dumps({
                'report_id': safe.pk,
                'data_type': 'safe',
                'description': 'Mark description',
                'is_modifiable': True,
                'verdict': MARK_SAFE[1][0],
                'status': MARK_STATUS[2][0],
                'tags': ['safe:tag:1', 'safe:tag:2'],
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
            mark = MarkSafe.objects.get(prime=safe, job=self.job, author__username='manager')
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
        self.assertEqual(len(MarkSafeReport.objects.filter(mark=mark, report=safe)), 1)
        self.assertEqual(len(SafeTag.objects.filter(tag='safe:tag:1')), 1)
        self.assertEqual(len(SafeTag.objects.filter(tag='safe:tag:2')), 1)
        self.assertEqual(len(MarkSafeTag.objects.filter(mark_version=mark_version, tag__tag='safe:tag:1')), 1)
        self.assertEqual(len(MarkSafeTag.objects.filter(mark_version=mark_version, tag__tag='safe:tag:2')), 1)
        try:
            rst = ReportSafeTag.objects.get(report__root__job=self.job, report__parent=None, tag__tag='safe:tag:1')
            self.assertEqual(rst.number, 1)
            rst = ReportSafeTag.objects.get(report__root__job=self.job, report__parent=None, tag__tag='safe:tag:2')
            self.assertEqual(rst.number, 1)
            rst = ReportSafeTag.objects.get(report__root__job=self.job, report_id=safe.parent_id,
                                            tag__tag='safe:tag:1')
            self.assertEqual(rst.number, 1)
            rst = ReportSafeTag.objects.get(report__root__job=self.job, report__id=safe.parent_id,
                                            tag__tag='safe:tag:2')
            self.assertEqual(rst.number, 1)
            srt = SafeReportTag.objects.get(report=safe, tag__tag='safe:tag:1')
            self.assertEqual(srt.number, 1)
            srt = SafeReportTag.objects.get(report=safe, tag__tag='safe:tag:2')
            self.assertEqual(srt.number, 1)
        except ObjectDoesNotExist:
            self.fail('Reports tags cache was not filled')

        # Associations changes
        response = self.client.get('/marks/association_changes/%s/' % cache_id)
        self.assertEqual(response.status_code, 200)

        # Edit mark page
        response = self.client.get(reverse('marks:edit_mark', args=['safe', mark.pk]))
        self.assertEqual(response.status_code, 200)

        # Edit mark
        response = self.client.post('/marks/ajax/save_mark/', {
            'savedata': json.dumps({
                'mark_id': mark.pk,
                'data_type': 'safe',
                'description': 'New mark description',
                'is_modifiable': True,
                'verdict': MARK_SAFE[2][0],
                'status': MARK_STATUS[2][0],
                'tags': ['safe:tag:1'],
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
            mark = MarkSafe.objects.get(prime=safe, job=self.job, author__username='manager')
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
        self.assertEqual(len(SafeTag.objects.filter(tag='safe:tag:1')), 1)
        self.assertEqual(len(SafeTag.objects.filter(tag='safe:tag:2')), 1)
        self.assertEqual(len(MarkSafeTag.objects.filter(mark_version=mark_version, tag__tag='safe:tag:1')), 1)
        self.assertEqual(len(MarkSafeTag.objects.filter(mark_version=mark_version, tag__tag='safe:tag:2')), 0)
        self.assertEqual(len(ReportSafeTag.objects.filter(report__root__job=self.job, report__parent=None)), 1)
        self.assertEqual(len(ReportSafeTag.objects.filter(report__root__job=self.job, report__id=safe.parent_id)), 1)
        try:
            srt = SafeReportTag.objects.get(report=safe, tag__tag='safe:tag:1')
            self.assertEqual(srt.number, 1)
        except ObjectDoesNotExist:
            self.fail('Reports tags cache was not filled')
        self.assertEqual(len(SafeReportTag.objects.filter(report=safe, tag__tag='safe:tag:2')), 0)

        # Associations changes
        response = self.client.get('/marks/association_changes/%s/' % cache_id)
        self.assertEqual(response.status_code, 200)

        # Safe marks list page
        response = self.client.get(reverse('marks:mark_list', args=['safe']))
        self.assertEqual(response.status_code, 200)

        # Download mark
        response = self.client.get(reverse('marks:download_mark', args=['safe', mark.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/x-tar-gz')
        with open(os.path.join(MEDIA_ROOT, self.safe_archive), mode='wb') as fp:
            fp.write(response.content)
            fp.close()

        # Delete mark
        response = self.client.get(reverse('marks:delete_mark', args=['safe', mark.pk]))
        self.assertRedirects(response, reverse('marks:mark_list', args=['safe']))
        self.assertEqual(len(MarkSafe.objects.all()), 0)
        self.assertEqual(len(MarkSafeReport.objects.all()), 0)
        self.assertEqual(ReportSafe.objects.all().first().verdict, SAFE_VERDICTS[4][0])

        # Upload mark
        with open(os.path.join(MEDIA_ROOT, self.safe_archive), mode='rb') as fp:
            response = self.client.post('/marks/ajax/upload_marks/', {'file': fp})
            fp.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertEqual(res.get('status', None), True)
        self.assertEqual(res.get('mark_type', None), 'safe')
        self.assertEqual(len(MarkSafe.objects.all()), 1)
        try:
            newmark = MarkSafe.objects.get(pk=res.get('mark_id', 0))
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
        self.assertEqual(len(SafeTag.objects.filter(tag='safe:tag:1')), 1)
        self.assertEqual(len(SafeTag.objects.filter(tag='safe:tag:2')), 1)
        self.assertEqual(len(MarkSafeTag.objects.filter(mark_version=newmark_version, tag__tag='safe:tag:1')), 1)
        self.assertEqual(len(MarkSafeTag.objects.filter(mark_version=newmark_version, tag__tag='safe:tag:2')), 0)
        self.assertEqual(len(ReportSafeTag.objects.filter(report__root__job=self.job, report__parent=None)), 1)
        self.assertEqual(len(ReportSafeTag.objects.filter(report__root__job=self.job, report__id=safe.parent_id)), 1)

        # Some more mark changes
        for i in range(3, 6):
            response = self.client.post('/marks/ajax/save_mark/', {
                'savedata': json.dumps({
                    'mark_id': newmark.pk,
                    'data_type': 'safe',
                    'description': 'New mark description',
                    'is_modifiable': True,
                    'verdict': MARK_SAFE[2][0],
                    'status': MARK_STATUS[2][0],
                    'tags': ['safe:tag:1'],
                    'attrs': compare_attrs,
                    'comment': 'Change %s' % i
                })
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/json')
            self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        self.assertEqual(len(MarkSafeHistory.objects.filter(mark=newmark)), 5)

        # Get 3d version data
        response = self.client.post('/marks/ajax/get_mark_version_data/', {
            'type': 'safe', 'version': 3, 'mark_id': newmark.pk
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('data', res)

        # Get mark's versions
        response = self.client.post('/marks/ajax/getversions/', {'mark_type': 'safe', 'mark_id': newmark.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')

        # Remove 2nd and 4th versions
        response = self.client.post('/marks/ajax/remove_versions/', {
            'mark_type': 'safe', 'mark_id': newmark.pk, 'versions': json.dumps([2, 4])
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('message', res)
        self.assertEqual(len(MarkSafeHistory.objects.filter(mark=newmark)), 3)

        # Reports' lists pages
        root_comp = ReportComponent.objects.get(root__job_id=self.job.pk, parent=None)
        tag = SafeTag.objects.get(tag='safe:tag:1')
        response = self.client.get(reverse('reports:list_tag', args=[root_comp.pk, 'safes', tag.pk]))
        self.assertEqual(response.status_code, 200)
        tag = SafeTag.objects.get(tag='safe:tag:2')
        response = self.client.get(reverse('reports:list_tag', args=[root_comp.pk, 'safes', tag.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('reports:list_mark', args=[root_comp.pk, 'safes', newmark.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('reports:list_verdict', args=[root_comp.pk, 'safes', SAFE_VERDICTS[0][0]]))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('reports:list_verdict', args=[root_comp.pk, 'safes', SAFE_VERDICTS[2][0]]))
        self.assertEqual(response.status_code, 200)

        # Delete all marks
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/marks/ajax/delete/', {
            'type': 'safe', 'ids': json.dumps(list(x.pk for x in MarkSafe.objects.all()))
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(MarkSafe.objects.all()), 0)
        # All verdicts must be "safe unmarked"
        self.assertEqual(
            len(ReportSafe.objects.filter(verdict=SAFE_VERDICTS[4][0])),
            len(ReportSafe.objects.all())
        )
        self.assertEqual(len(MarkSafeReport.objects.all()), 0)

    def test_unsafe(self):
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[3][0])

        # Get report
        try:
            unsafe = ReportUnsafe.objects.filter(root__job_id=self.job.pk)[0]
        except IndexError:
            self.fail("Test job decision does not have unsafe report")

        # Create mark page
        response = self.client.get(reverse('marks:create_mark', args=['unsafe', unsafe.pk]))
        self.assertEqual(response.status_code, 200)

        # Error trace functions descriptions
        try:
            compare_f = MarkUnsafeCompare.objects.get(name=DEFAULT_COMPARE)
        except ObjectDoesNotExist:
            self.fail("Population hasn't created compare error trace functions")
        response = self.client.post('/marks/ajax/get_func_description/', {
            'func_id': compare_f.pk, 'func_type': 'compare'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(res.get('description', None), compare_f.description)
        try:
            convert_f = MarkUnsafeConvert.objects.get(name=DEFAULT_CONVERT)
        except ObjectDoesNotExist:
            self.fail("Population hasn't created convert error trace functions")
        response = self.client.post('/marks/ajax/get_func_description/', {
            'func_id': convert_f.pk, 'func_type': 'convert'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertEqual(res.get('description', None), convert_f.description)

        # Save mark
        compare_attrs = []
        for a in unsafe.attrs.all():
            attr_data = {'is_compare': False, 'attr': a.attr.name.name}
            if a.attr.name in MARKS_COMPARE_ATTRS[self.job.type]:
                attr_data['is_compare'] = True
            compare_attrs.append(attr_data)
        response = self.client.post('/marks/ajax/save_mark/', {
            'savedata': json.dumps({
                'convert_id': convert_f.pk,
                'compare_id': compare_f.pk,
                'report_id': unsafe.pk,
                'data_type': 'unsafe',
                'description': 'Mark description',
                'is_modifiable': True,
                'verdict': MARK_UNSAFE[1][0],
                'status': MARK_STATUS[2][0],
                'tags': ['unsafe:tag:1'],
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
            mark = MarkUnsafe.objects.get(prime=unsafe, job=self.job, author__username='manager')
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
        for mark_attr in mark_version.attrs.all():
            self.assertIn({'is_compare': mark_attr.is_compare, 'attr': mark_attr.attr.name.name}, compare_attrs)
        self.assertEqual(ReportUnsafe.objects.get(pk=unsafe.pk).verdict, UNSAFE_VERDICTS[1][0])
        self.assertEqual(len(MarkUnsafeReport.objects.filter(mark=mark, report=unsafe)), 1)
        self.assertEqual(len(UnsafeTag.objects.filter(tag='unsafe:tag:1')), 1)
        self.assertEqual(len(MarkUnsafeTag.objects.filter(mark_version=mark_version, tag__tag='unsafe:tag:1')), 1)
        try:
            rst = ReportUnsafeTag.objects.get(report__root__job=self.job, report__parent=None, tag__tag='unsafe:tag:1')
            # The number of unsafes for root report with specified tag equals the number of marked unsafes
            self.assertEqual(rst.number, len(ReportUnsafe.objects.filter(verdict=UNSAFE_VERDICTS[1][0])))
            rst = ReportUnsafeTag.objects.get(report__root__job=self.job, report_id=unsafe.parent_id,
                                              tag__tag='unsafe:tag:1')
            # The number of unsafes for parent report (for unsafe) with specified tag
            # equals 1 due to only one unsafe is child for report
            self.assertEqual(rst.number, 1)
            srt = UnsafeReportTag.objects.get(report=unsafe, tag__tag='unsafe:tag:1')
            self.assertEqual(srt.number, 1)
        except ObjectDoesNotExist:
            self.fail('Reports tags cache was not filled')

        # Associations changes
        response = self.client.get('/marks/association_changes/%s/' % cache_id)
        self.assertEqual(response.status_code, 200)

        # Edit mark page
        response = self.client.get(reverse('marks:edit_mark', args=['unsafe', mark.pk]))
        self.assertEqual(response.status_code, 200)

        # Edit mark
        response = self.client.post('/marks/ajax/save_mark/', {
            'savedata': json.dumps({
                'mark_id': mark.pk,
                'compare_id': compare_f.pk,
                'data_type': 'unsafe',
                'description': 'New mark description',
                'is_modifiable': True,
                'verdict': MARK_UNSAFE[2][0],
                'status': MARK_STATUS[2][0],
                'tags': ['unsafe:tag:1', 'unsafe:tag:2'],
                'attrs': compare_attrs,
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
            mark = MarkUnsafe.objects.get(prime=unsafe, job=self.job, author__username='manager')
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
        self.assertEqual(len(UnsafeTag.objects.filter(tag='unsafe:tag:1')), 1)
        self.assertEqual(len(UnsafeTag.objects.filter(tag='unsafe:tag:2')), 1)
        self.assertEqual(len(MarkUnsafeTag.objects.filter(mark_version=mark_version, tag__tag='unsafe:tag:1')), 1)
        self.assertEqual(len(MarkUnsafeTag.objects.filter(mark_version=mark_version, tag__tag='unsafe:tag:2')), 1)
        self.assertEqual(len(ReportUnsafeTag.objects.filter(report__root__job=self.job, report__parent=None)), 2)
        self.assertEqual(len(
            ReportUnsafeTag.objects.filter(report__root__job=self.job, report__id=unsafe.parent_id)
        ), 2)
        try:
            srt = UnsafeReportTag.objects.get(report=unsafe, tag__tag='unsafe:tag:1')
            self.assertEqual(srt.number, 1)
            srt = UnsafeReportTag.objects.get(report=unsafe, tag__tag='unsafe:tag:2')
            self.assertEqual(srt.number, 1)
        except ObjectDoesNotExist:
            self.fail('Reports tags cache was not filled')

        # Associations changes
        response = self.client.get('/marks/association_changes/%s/' % cache_id)
        self.assertEqual(response.status_code, 200)

        # Unsafe marks list page
        response = self.client.get(reverse('marks:mark_list', args=['unsafe']))
        self.assertEqual(response.status_code, 200)

        # Download mark
        response = self.client.get(reverse('marks:download_mark', args=['unsafe', mark.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/x-tar-gz')
        with open(os.path.join(MEDIA_ROOT, self.unsafe_archive), mode='wb') as fp:
            fp.write(response.content)
            fp.close()

        # Delete mark
        response = self.client.get(reverse('marks:delete_mark', args=['unsafe', mark.pk]))
        self.assertRedirects(response, reverse('marks:mark_list', args=['unsafe']))
        self.assertEqual(len(MarkUnsafe.objects.all()), 0)
        self.assertEqual(len(MarkUnsafeReport.objects.all()), 0)
        self.assertEqual(ReportUnsafe.objects.all().first().verdict, UNSAFE_VERDICTS[5][0])

        # Upload mark
        with open(os.path.join(MEDIA_ROOT, self.unsafe_archive), mode='rb') as fp:
            response = self.client.post('/marks/ajax/upload_marks/', {'file': fp})
            fp.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertEqual(res.get('status', None), True)
        self.assertEqual(res.get('mark_type', None), 'unsafe')
        self.assertEqual(len(MarkUnsafe.objects.all()), 1)
        try:
            newmark = MarkUnsafe.objects.get(pk=res.get('mark_id', 0))
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
        self.assertEqual(len(UnsafeTag.objects.filter(tag='unsafe:tag:1')), 1)
        self.assertEqual(len(UnsafeTag.objects.filter(tag='unsafe:tag:2')), 1)
        self.assertEqual(len(MarkUnsafeTag.objects.filter(mark_version=newmark_version, tag__tag='unsafe:tag:1')), 1)
        self.assertEqual(len(MarkUnsafeTag.objects.filter(mark_version=newmark_version, tag__tag='unsafe:tag:2')), 1)
        self.assertEqual(
            len(ReportUnsafeTag.objects.filter(report__root__job=self.job, report__parent=None)),
            len(ReportUnsafe.objects.filter(verdict=UNSAFE_VERDICTS[2][0]))
        )
        self.assertEqual(len(ReportUnsafeTag.objects.filter(
            report__root__job=self.job, report__id=unsafe.parent_id
        )), 2)

        # Some more mark changes
        for i in range(3, 6):
            response = self.client.post('/marks/ajax/save_mark/', {
                'savedata': json.dumps({
                    'compare_id': compare_f.pk,
                    'mark_id': newmark.pk,
                    'data_type': 'unsafe',
                    'description': 'New mark description',
                    'is_modifiable': True,
                    'verdict': MARK_UNSAFE[2][0],
                    'status': MARK_STATUS[2][0],
                    'tags': ['unsafe:tag:1'],
                    'attrs': compare_attrs,
                    'comment': 'Change %s' % i
                })
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/json')
            self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        self.assertEqual(len(MarkUnsafeHistory.objects.filter(mark=newmark)), 5)

        # Get 3d version data
        response = self.client.post('/marks/ajax/get_mark_version_data/', {
            'type': 'unsafe', 'version': 3, 'mark_id': newmark.pk
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('data', res)

        # Get mark's versions
        response = self.client.post('/marks/ajax/getversions/', {'mark_type': 'unsafe', 'mark_id': newmark.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')

        # Remove 2nd and 4th versions
        response = self.client.post('/marks/ajax/remove_versions/', {
            'mark_type': 'unsafe', 'mark_id': newmark.pk, 'versions': json.dumps([2, 4])
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('message', res)
        self.assertEqual(len(MarkUnsafeHistory.objects.filter(mark=newmark)), 3)

        # Reports' lists pages
        root_comp = ReportComponent.objects.get(root__job_id=self.job.pk, parent=None)
        tag = UnsafeTag.objects.get(tag='unsafe:tag:1')
        response = self.client.get(reverse('reports:list_tag', args=[root_comp.pk, 'unsafes', tag.pk]))
        self.assertEqual(response.status_code, 200)
        tag = UnsafeTag.objects.get(tag='unsafe:tag:2')
        response = self.client.get(reverse('reports:list_tag', args=[root_comp.pk, 'unsafes', tag.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('reports:list_mark', args=[root_comp.pk, 'unsafes', newmark.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(
            reverse('reports:list_verdict', args=[root_comp.pk, 'unsafes', UNSAFE_VERDICTS[0][0]])
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.get(
            reverse('reports:list_verdict', args=[root_comp.pk, 'unsafes', UNSAFE_VERDICTS[2][0]])
        )

        # Delete all marks
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/marks/ajax/delete/', {
            'type': 'unsafe', 'ids': json.dumps(list(x.pk for x in MarkUnsafe.objects.all()))
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(MarkUnsafe.objects.all()), 0)
        # All verdicts must be "unsafe unmarked"
        self.assertEqual(
            len(ReportUnsafe.objects.filter(verdict=UNSAFE_VERDICTS[5][0])),
            len(ReportUnsafe.objects.all())
        )
        self.assertEqual(len(MarkUnsafeReport.objects.all()), 0)

    def test_unknown(self):
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, JOB_STATUS[3][0])

        # Get report
        unknown = None
        for u in ReportUnknown.objects.filter(root__job_id=self.job.pk):
            problem_desc = u.problem_description.file.read()
            u.problem_description.file.close()
            if problem_desc == b"ValueError: got wrong attribute: 'rule'.":
                unknown = u
        parent = ReportComponent.objects.get(pk=unknown.parent_id)
        if unknown is None:
            self.fail("Unknown with needed problem description was not found in test job decision")

        # Create mark page
        response = self.client.get(reverse('marks:create_mark', args=['unknown', unknown.pk]))
        self.assertEqual(response.status_code, 200)

        # Save mark
        response = self.client.post('/marks/ajax/save_mark/', {
            'savedata': json.dumps({
                'report_id': unknown.pk,
                'data_type': 'unknown',
                'description': 'Mark description',
                'is_modifiable': True,
                'status': MARK_STATUS[2][0],
                'function': "ValueError:\sgot\swrong\sattribute:\s'(\S*)'",
                'problem': 'EVal: {0}',
                'link': 'http://mysite.com/'
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
            mark = MarkUnknown.objects.get(prime=unknown, job=self.job, author__username='manager')
        except ObjectDoesNotExist:
            self.fail('Mark was not created')
        self.assertEqual(mark.type, MARK_TYPE[0][0])
        self.assertEqual(mark.status, MARK_STATUS[2][0])
        self.assertEqual(mark.version, 1)
        self.assertEqual(mark.description, 'Mark description')
        self.assertEqual(mark.link, 'http://mysite.com/')
        self.assertEqual(mark.problem_pattern, 'EVal: {0}')
        self.assertEqual(mark.function, "ValueError:\sgot\swrong\sattribute:\s'(\S*)'")
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
        self.assertEqual(len(UnknownProblem.objects.filter(name='EVal: rule')), 1)
        self.assertEqual(len(MarkUnknownReport.objects.filter(mark=mark, report=unknown)), 1)

        try:
            cmup = ComponentMarkUnknownProblem.objects.get(
                Q(report__parent=None, report__root__job=self.job) & ~Q(problem=None)
            )
            self.assertEqual(cmup.component, parent.component)
            self.assertEqual(cmup.problem.name, 'EVal: rule')
            self.assertEqual(cmup.number, 1)
            cmup = ComponentMarkUnknownProblem.objects.get(Q(report=parent) & ~Q(problem=None))
            self.assertEqual(cmup.component, parent.component)
            self.assertEqual(cmup.problem.name, 'EVal: rule')
            self.assertEqual(cmup.number, 1)
        except ObjectDoesNotExist:
            self.fail('Reports cache was not filled')

        # Associations changes
        response = self.client.get('/marks/association_changes/%s/' % cache_id)
        self.assertEqual(response.status_code, 200)

        # Edit mark page
        response = self.client.get(reverse('marks:edit_mark', args=['unknown', mark.pk]))
        self.assertEqual(response.status_code, 200)

        # Edit mark
        response = self.client.post('/marks/ajax/save_mark/', {
            'savedata': json.dumps({
                'mark_id': mark.pk,
                'data_type': 'unknown',
                'description': 'New mark description',
                'is_modifiable': True,
                'status': MARK_STATUS[1][0],
                'function': "ValueError:.*'(\S*)'",
                'problem': 'EVal: {0}',
                'link': 'http://mysite.com/',
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
            mark = MarkUnknown.objects.get(prime=unknown, job=self.job, author__username='manager')
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
        self.assertEqual(len(UnknownProblem.objects.filter(name='EVal: rule')), 1)
        self.assertEqual(len(MarkUnknownReport.objects.filter(mark=mark, report=unknown)), 1)

        try:
            cmup = ComponentMarkUnknownProblem.objects.get(
                Q(report__parent=None, report__root__job=self.job) & ~Q(problem=None)
            )
            self.assertEqual(cmup.component, parent.component)
            self.assertEqual(cmup.problem.name, 'EVal: rule')
            self.assertEqual(cmup.number, 1)
            cmup = ComponentMarkUnknownProblem.objects.get(Q(report=parent) & ~Q(problem=None))
            self.assertEqual(cmup.component, parent.component)
            self.assertEqual(cmup.problem.name, 'EVal: rule')
            self.assertEqual(cmup.number, 1)
        except ObjectDoesNotExist:
            self.fail('Reports tags cache was not filled')

        # Associations changes
        response = self.client.get('/marks/association_changes/%s/' % cache_id)
        self.assertEqual(response.status_code, 200)

        # Unknown marks list page
        response = self.client.get(reverse('marks:mark_list', args=['unknown']))
        self.assertEqual(response.status_code, 200)

        # Download mark
        response = self.client.get(reverse('marks:download_mark', args=['unknown', mark.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/x-tar-gz')
        with open(os.path.join(MEDIA_ROOT, self.unknown_archive), mode='wb') as fp:
            fp.write(response.content)
            fp.close()

        # Delete mark
        response = self.client.get(reverse('marks:delete_mark', args=['unknown', mark.pk]))
        self.assertRedirects(response, reverse('marks:mark_list', args=['unknown']))
        self.assertEqual(len(MarkUnknown.objects.filter(prime=unknown)), 0)
        self.assertEqual(len(MarkUnknownReport.objects.all()), 0)
        self.assertEqual(len(ComponentMarkUnknownProblem.objects.filter(problem__name='EVal: rule')), 0)

        # Upload mark
        with open(os.path.join(MEDIA_ROOT, self.unknown_archive), mode='rb') as fp:
            response = self.client.post('/marks/ajax/upload_marks/', {'file': fp})
            fp.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertEqual(res.get('status', None), True)
        self.assertEqual(res.get('mark_type', None), 'unknown')
        try:
            newmark = MarkUnknown.objects.get(pk=res.get('mark_id', 0))
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
        self.assertEqual(len(UnknownProblem.objects.filter(name='EVal: rule')), 1)

        try:
            cmup = ComponentMarkUnknownProblem.objects.get(
                Q(report__parent=None, report__root__job=self.job) & ~Q(problem=None)
            )
            self.assertEqual(cmup.component, parent.component)
            self.assertEqual(cmup.problem.name, 'EVal: rule')
            self.assertEqual(cmup.number, 1)
            cmup = ComponentMarkUnknownProblem.objects.get(Q(report=parent) & ~Q(problem=None))
            self.assertEqual(cmup.component, parent.component)
            self.assertEqual(cmup.problem.name, 'EVal: rule')
            self.assertEqual(cmup.number, 1)
        except ObjectDoesNotExist:
            self.fail('Reports tags cache was not filled')

        # Some more mark changes
        for i in range(3, 6):
            response = self.client.post('/marks/ajax/save_mark/', {
                'savedata': json.dumps({
                    'mark_id': newmark.pk,
                    'data_type': 'unknown',
                    'description': 'New mark description',
                    'is_modifiable': True,
                    'status': MARK_STATUS[2][0],
                    'function': "ValueError:.*'(\S*)'",
                    'problem': 'EVal: {0}',
                    'link': 'http://mysite.com/',
                    'comment': 'Change %s' % i
                })
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/json')
            self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))

        self.assertEqual(len(MarkUnknownHistory.objects.filter(mark=newmark)), 5)

        # Get 3d version data
        response = self.client.post('/marks/ajax/get_mark_version_data/', {
            'type': 'unknown', 'version': 3, 'mark_id': newmark.pk
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('data', res)

        # Get mark's versions
        response = self.client.post('/marks/ajax/getversions/', {'mark_type': 'unknown', 'mark_id': newmark.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')

        # Remove 2nd and 4th versions
        response = self.client.post('/marks/ajax/remove_versions/', {
            'mark_type': 'unknown', 'mark_id': newmark.pk, 'versions': json.dumps([2, 4])
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        res = json.loads(str(response.content, encoding='utf8'))
        self.assertNotIn('error', res)
        self.assertIn('message', res)
        self.assertEqual(len(MarkUnknownHistory.objects.filter(mark=newmark)), 3)

        # Reports' lists pages
        root_comp = ReportComponent.objects.get(root__job_id=self.job.pk, parent=None)
        response = self.client.get(reverse('reports:list_mark', args=[root_comp.pk, 'unknowns', newmark.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('reports:unknowns', args=[root_comp.pk, parent.component_id]))
        self.assertEqual(response.status_code, 200)
        try:
            problem_id = UnknownProblem.objects.get(name='EVal: rule').pk
        except ObjectDoesNotExist:
            self.fail("Can't find unknown problem")
        response = self.client.get(
            reverse('reports:unknowns_problem', args=[root_comp.pk, parent.component_id, problem_id])
        )
        self.assertEqual(response.status_code, 200)

        # Delete all marks
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/marks/ajax/delete/', {
            'type': 'unknown', 'ids': json.dumps([newmark.pk])
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertNotIn('error', json.loads(str(response.content, encoding='utf8')))
        self.assertEqual(len(MarkUnknown.objects.filter(pk=newmark.pk)), 0)
        self.assertEqual(len(MarkUnknownReport.objects.filter(problem__name='EVal: rule')), 0)

    def tearDown(self):
        if os.path.exists(os.path.join(MEDIA_ROOT, self.safe_archive)):
            os.remove(os.path.join(MEDIA_ROOT, self.safe_archive))
        if os.path.exists(os.path.join(MEDIA_ROOT, self.unsafe_archive)):
            os.remove(os.path.join(MEDIA_ROOT, self.unsafe_archive))
        if os.path.exists(os.path.join(MEDIA_ROOT, self.unknown_archive)):
            os.remove(os.path.join(MEDIA_ROOT, self.unknown_archive))
        super(TestMarks, self).tearDown()
