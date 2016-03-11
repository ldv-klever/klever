import re
import json
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _
from bridge.vars import JOB_STATUS, JOBS_COMPARE_ATTRS
from bridge.utils import print_err
from jobs.utils import JobAccess, CompareFileSet
from reports.models import *
from marks.models import MarkUnsafeReport, MarkSafeReport, MarkUnknownReport
from marks.tables import UNSAFE_COLOR, SAFE_COLOR


def can_compare(user, job1, job2):
    if not isinstance(job1, Job) or not isinstance(job2, Job) or not isinstance(user, User):
        return False
    if job1.type != job2.type:
        return False
    if not JobAccess(user, job1).can_view() or job1.status != JOB_STATUS[3][0]:
        return False
    if not JobAccess(user, job2).can_view() or job2.status != JOB_STATUS[3][0]:
        return False
    return True


class ReportTree(object):
    def __init__(self, job):
        self.job = job
        self.attrs = JOBS_COMPARE_ATTRS[job.type]
        self.reports = {}
        self.attr_values = {}
        self.__get_tree()

    def __get_tree(self):
        for u in ReportUnsafe.objects.filter(root__job=self.job):
            main_attrs = u.attrs.filter(attr__name__name__in=self.attrs)
            if len(main_attrs) != len(self.attrs):
                continue
            attr_values = {}
            for ma in main_attrs:
                if ma.attr.name.name in self.attrs:
                    attr_values[ma.attr.name.name] = ma.attr.value
            attrs_id = json.dumps(list(attr_values[x] for x in self.attrs))
            if attrs_id not in self.attr_values:
                self.attr_values[attrs_id] = {
                    'ids': [u.pk],
                    'verdict': COMPARE_VERDICT[1][0]
                }
            else:
                self.attr_values[attrs_id]['ids'].append(u.pk)
            self.reports[u.pk] = {
                'type': 'u',
                'parent': u.parent_id
            }
            for leaf in ReportComponentLeaf.objects.filter(Q(unsafe=u) & ~Q(report_id__in=list(self.reports))):
                self.reports[leaf.report_id] = {
                    'type': 'c',
                    'parent': leaf.report.parent_id
                }
        for s in ReportSafe.objects.filter(root__job=self.job):
            main_attrs = s.attrs.filter(attr__name__name__in=self.attrs)
            if len(main_attrs) != len(self.attrs):
                continue
            attr_values = {}
            for ma in main_attrs:
                if ma.attr.name.name in self.attrs:
                    attr_values[ma.attr.name.name] = ma.attr.value
            attrs_id = json.dumps(list(attr_values[x] for x in self.attrs))
            if attrs_id not in self.attr_values:
                self.attr_values[attrs_id] = {
                    'ids': [s.pk],
                    'verdict': COMPARE_VERDICT[0][0]
                }
            else:
                raise ValueError('Too many leaf reports for "%s"' % attrs_id)
            self.reports[s.pk] = {
                'type': 's',
                'parent': s.parent_id
            }
            for leaf in ReportComponentLeaf.objects.filter(Q(safe=s) & ~Q(report_id__in=list(self.reports))):
                self.reports[leaf.report_id] = {
                    'type': 'c',
                    'parent': leaf.report.parent_id
                }
        for f in ReportUnknown.objects.filter(root__job=self.job):
            main_attrs = f.attrs.filter(attr__name__name__in=self.attrs)
            if len(main_attrs) != len(self.attrs):
                continue
            attr_values = {}
            for ma in main_attrs:
                if ma.attr.name.name in self.attrs:
                    attr_values[ma.attr.name.name] = ma.attr.value
            attrs_id = json.dumps(list(attr_values[x] for x in self.attrs))
            if attrs_id not in self.attr_values:
                self.attr_values[attrs_id] = {
                    'ids': [f.pk],
                    'verdict': COMPARE_VERDICT[3][0]
                }
            else:
                for r_id in self.attr_values[attrs_id]['ids']:
                    if r_id not in self.reports or self.reports[r_id]['type'] != 'u':
                        raise ValueError('Too many leaf reports for "%s"' % attrs_id)
                else:
                    self.attr_values[attrs_id]['verdict'] = COMPARE_VERDICT[2][0]
                    self.attr_values[attrs_id]['ids'].append(f.pk)
            self.reports[f.pk] = {
                'type': 'f',
                'parent': f.parent_id
            }
            for leaf in ReportComponentLeaf.objects.filter(Q(unknown=f) & ~Q(report_id__in=list(self.reports))):
                self.reports[leaf.report_id] = {
                    'type': 'c',
                    'parent': leaf.report.parent_id
                }


class CompareTree(object):
    def __init__(self, user, j1, j2):
        self.user = user
        self.tree1 = ReportTree(j1)
        self.tree2 = ReportTree(j2)
        self.attr_values = {}
        self.__compare_values()
        self.__fill_cache(j1, j2)

    def __compare_values(self):
        for a_id in self.tree1.attr_values:
            self.attr_values[a_id] = {
                'v1': self.tree1.attr_values[a_id]['verdict'],
                'v2': COMPARE_VERDICT[4][0],
                'ids1': self.tree1.attr_values[a_id]['ids'],
                'ids2': []
            }
            if a_id in self.tree2.attr_values:
                self.attr_values[a_id]['v2'] = self.tree2.attr_values[a_id]['verdict']
                self.attr_values[a_id]['ids2'] = self.tree2.attr_values[a_id]['ids']
        for a_id in self.tree2.attr_values:
            if a_id not in self.tree1.attr_values:
                self.attr_values[a_id] = {
                    'v1': COMPARE_VERDICT[4][0],
                    'v2': self.tree2.attr_values[a_id]['verdict'],
                    'ids1': [],
                    'ids2': self.tree2.attr_values[a_id]['ids']
                }

    def __fill_cache(self, j1, j2):
        CompareJobsInfo.objects.filter(user=self.user).delete()
        info = CompareJobsInfo.objects.create(
            user=self.user, root1=j1.reportroot, root2=j2.reportroot,
            files_diff=json.dumps(CompareFileSet(j1, j2).data)
        )
        for_cache = []
        for x in self.attr_values:
            ids1 = []
            for r_id in self.attr_values[x]['ids1']:
                branch_ids = []
                if r_id in self.tree1.reports:
                    parent = r_id
                    while parent is not None and parent in self.tree1.reports:
                        branch_ids.insert(0, (self.tree1.reports[parent]['type'], parent))
                        parent = self.tree1.reports[parent]['parent']
                if len(branch_ids) > 0:
                    ids1.append(branch_ids)
            ids2 = []
            for r_id in self.attr_values[x]['ids2']:
                branch_ids = []
                if r_id in self.tree2.reports:
                    parent = r_id
                    while parent is not None and parent in self.tree2.reports:
                        branch_ids.insert(0, (self.tree2.reports[parent]['type'], parent))
                        parent = self.tree2.reports[parent]['parent']
                if len(branch_ids) > 0:
                    ids2.append(branch_ids)
            for_cache.append(CompareJobsCache(
                info=info, attr_values=x,
                verdict1=self.attr_values[x]['v1'], verdict2=self.attr_values[x]['v2'],
                reports1=json.dumps(ids1), reports2=json.dumps(ids2)
            ))
        CompareJobsCache.objects.bulk_create(for_cache)


class ComparisonTableData(object):
    def __init__(self, user, j1, j2):
        self.job1 = j1
        self.job2 = j2
        self.user = user
        self.data = []
        self.error = None
        self.info = 0
        self.attrs = []
        self.__get_data()

    def __get_data(self):
        try:
            info = CompareJobsInfo.objects.get(user=self.user, root1=self.job1.reportroot, root2=self.job2.reportroot)
        except ObjectDoesNotExist:
            self.error = _('The comparison cache was not found')
            return
        self.info = info.pk
        for v1 in COMPARE_VERDICT:
            row_data = []
            for v2 in COMPARE_VERDICT:
                num = len(CompareJobsCache.objects.filter(info=info, verdict1=v1[0], verdict2=v2[0]))
                if num == 0:
                    num = '-'
                else:
                    num = (num, v2[0])
                row_data.append(num)
            self.data.append(row_data)
        all_attrs = {}
        for compare in info.comparejobscache_set.all():
            try:
                attr_values = json.loads(compare.attr_values)
            except Exception as e:
                print_err(e)
                self.error = 'Unknown error'
                return
            if len(attr_values) != len(JOBS_COMPARE_ATTRS[info.root1.job.type]):
                self.error = 'Unknown error'
                return
            for i in range(0, len(attr_values)):
                if JOBS_COMPARE_ATTRS[info.root1.job.type][i] not in all_attrs:
                    all_attrs[JOBS_COMPARE_ATTRS[info.root1.job.type][i]] = []
                if attr_values[i] not in all_attrs[JOBS_COMPARE_ATTRS[info.root1.job.type][i]]:
                    all_attrs[JOBS_COMPARE_ATTRS[info.root1.job.type][i]].append(attr_values[i])

        for a in JOBS_COMPARE_ATTRS[info.root1.job.type]:
            if a in all_attrs:
                self.attrs.append({'name': a, 'values': list(sorted(all_attrs[a]))})


class ComparisonData(object):
    def __init__(self, info_id, page_num, hide_attrs, hide_components, verdict=None, attrs=None):
        self.error = None
        try:
            self.info = CompareJobsInfo.objects.get(pk=info_id)
        except ObjectDoesNotExist:
            self.error = _("The comparison cache was not found")
            return
        self.v1 = self.v2 = None
        self.hide_attrs = hide_attrs
        self.hide_components = hide_components
        self.attr_search = False
        self.pages = {
            'backward': True,
            'forward': True,
            'num': page_num,
            'total': 0
        }
        self.data = self.__get_data(verdict, attrs)

    def __get_verdicts(self, verdict):
        m = re.match('^(\d)_(\d)$', verdict)
        if m is None:
            self.error = 'Unknown error'
            return None, None
        v1 = m.group(1)
        v2 = m.group(2)
        if any(v not in list(x[0] for x in COMPARE_VERDICT) for v in [v1, v2]):
            self.error = 'Unknown error'
            return None, None
        return v1, v2

    def __get_data(self, verdict=None, search_attrs=None):
        if search_attrs is not None:
            try:
                search_attrs = json.dumps(json.loads(search_attrs))
            except ValueError:
                self.error = 'Unknown error'
                return None
            data = self.info.comparejobscache_set.filter(attr_values=search_attrs).order_by('id')
            self.attr_search = True
        elif verdict is not None:
            (v1, v2) = self.__get_verdicts(verdict)
            data = self.info.comparejobscache_set.filter(verdict1=v1, verdict2=v2).order_by('id')
        else:
            self.error = 'Unknown error'
            return None
        self.pages['total'] = len(data)
        if self.pages['total'] < self.pages['num']:
            self.error = _('Required reports were not found')
            return None
        self.pages['backward'] = (self.pages['num'] > 1)
        self.pages['forward'] = (self.pages['num'] < self.pages['total'])
        data = data[self.pages['num'] - 1]
        self.v1 = data.verdict1
        self.v2 = data.verdict2

        branches = self.__compare_reports(data)
        if branches is None:
            if self.error is None:
                self.error = 'Unknown error'
            return None

        final_data = []
        for branch in branches:
            ordered = []
            for i in sorted(list(branch)):
                if len(branch[i]) > 0:
                    ordered.append(branch[i])
            final_data.append(ordered)
        return final_data

    def __compare_reports(self, c):
        data1 = self.__get_reports_data(json.loads(c.reports1))
        if data1 is None:
            if self.error is None:
                self.error = 'Unknown error'
            return None
        data2 = self.__get_reports_data(json.loads(c.reports2))
        if data2 is None:
            if self.error is None:
                self.error = 'Unknown error'
            return None
        for i in sorted(list(data1)):
            if i not in data2:
                break
            blocks = self.__compare_lists(data1[i], data2[i])
            if isinstance(blocks, list) and len(blocks) == 2:
                data1[i] = blocks[0]
                data2[i] = blocks[1]
        return [data1, data2]

    def __compare_lists(self, blocks1, blocks2):
        for b1 in blocks1:
            for b2 in blocks2:
                if b1.block_class != b2.block_class or b1.type == 'mark':
                    continue
                for a1 in b1.list:
                    if a1['name'] not in list(x['name'] for x in b2.list):
                        a1['color'] = '#c60806'
                    for a2 in b2.list:
                        if a2['name'] not in list(x['name'] for x in b1.list):
                            a2['color'] = '#c60806'
                        if a1['name'] == a2['name'] and a1['value'] != a2['value']:
                            a1['color'] = a2['color'] = '#af49bd'
        if self.hide_attrs:
            for b1 in blocks1:
                for b2 in blocks2:
                    if b1.block_class != b2.block_class or b1.type == 'mark':
                        continue
                    for b in [b1, b2]:
                        new_list = []
                        for a in b.list:
                            if 'color' in a:
                                new_list.append(a)
                        b.list = new_list
        if self.hide_components:
            for_del = {
                'b1': [],
                'b2': []
            }
            for i in range(0, len(blocks1)):
                for j in range(0, len(blocks2)):
                    if blocks1[i].block_class != blocks2[j].block_class or blocks1[i].type != 'component':
                        continue
                    if blocks1[i].list == blocks2[j].list and blocks1[i].add_info == blocks2[j].add_info:
                        for_del['b1'].append(i)
                        for_del['b2'].append(j)
            new_blocks1 = []
            for i in range(0, len(blocks1)):
                if i not in for_del['b1']:
                    new_blocks1.append(blocks1[i])
            new_blocks2 = []
            for i in range(0, len(blocks2)):
                if i not in for_del['b1']:
                    new_blocks2.append(blocks2[i])
            return [new_blocks1, new_blocks2]
        return None

    def __get_reports_data(self, reports):
        branch_data = {}
        for branch in reports:
            cnt = 1
            parent = None
            for rdata in branch:
                if cnt not in branch_data:
                    branch_data[cnt] = []
                if cnt in branch_data and rdata[1] in list(int(re.sub('.*_', '', x.id)) for x in branch_data[cnt]):
                    pass
                elif rdata[0] == 'c':
                    block = self.__component_data(rdata[1], parent)
                    if self.error is not None:
                        return None
                    branch_data[cnt].append(block)
                elif rdata[0] == 'u':
                    block = self.__unsafe_data(rdata[1], parent)
                    if self.error is not None:
                        return None
                    branch_data[cnt].append(block)
                    if self.v1 == self.v2:
                        cnt += 1
                        blocks = self.__unsafe_mark_data(rdata[1])
                        for b in blocks:
                            if cnt not in branch_data:
                                branch_data[cnt] = []
                            if b.id not in list(x.id for x in branch_data[cnt]):
                                branch_data[cnt].append(b)
                            else:
                                for i in range(0, len(branch_data[cnt])):
                                    if b.id == branch_data[cnt][i].id:
                                        branch_data[cnt][i].parents.extend(b.parents)
                                        break
                    break
                elif rdata[0] == 's':
                    block = self.__safe_data(rdata[1], parent)
                    if self.error is not None:
                        return None
                    branch_data[cnt].append(block)
                    if self.v1 == self.v2:
                        cnt += 1
                        blocks = self.__safe_mark_data(rdata[1])
                        for b in blocks:
                            if cnt not in branch_data:
                                branch_data[cnt] = []
                            if b.id not in list(x.id for x in branch_data[cnt]):
                                branch_data[cnt].append(b)
                            else:
                                for i in range(0, len(branch_data[cnt])):
                                    if b.id == branch_data[cnt][i].id:
                                        branch_data[cnt][i].parents.extend(b.parents)
                                        break
                    break
                elif rdata[0] == 'f':
                    block = self.__unknown_data(rdata[1], parent)
                    if self.error is not None:
                        return None
                    branch_data[cnt].append(block)
                    if self.v1 == self.v2:
                        cnt += 1
                        blocks = self.__unknown_mark_data(rdata[1])
                        for b in blocks:
                            if cnt not in branch_data:
                                branch_data[cnt] = []
                            if b.id not in list(x.id for x in branch_data[cnt]):
                                branch_data[cnt].append(b)
                            else:
                                for i in range(0, len(branch_data[cnt])):
                                    if b.id == branch_data[cnt][i].id:
                                        if b.add_info[0]['value'] == branch_data[cnt][i].add_info[0]['value']:
                                            branch_data[cnt][i].parents.extend(b.parents)
                                        else:
                                            branch_data[cnt].append(b)
                                        break
                    break
                parent = rdata[1]
                cnt += 1
        return branch_data

    def __component_data(self, report_id, parent_id):
        try:
            report = ReportComponent.objects.get(pk=report_id)
        except ObjectDoesNotExist:
            self.error = _('The report was not found, please recalculate the comparison cache')
            return None
        block = CompareBlock('c_%s' % report_id, 'component', report.component.name, 'comp_%s' % report.component.name)
        if parent_id is not None:
            block.parents.append('c_%s' % parent_id)
        for a in report.attrs.order_by('attr__name__name'):
            attr_data = {
                'name': a.attr.name.name,
                'value': a.attr.value
            }
            if attr_data['name'] in JOBS_COMPARE_ATTRS[self.info.root1.job.type]:
                attr_data['color'] = '#8bb72c'
            block.list.append(attr_data)
        block.href = reverse('reports:component', args=[report.root.job_id, report.pk])
        return block

    def __unsafe_data(self, report_id, parent_id):
        try:
            report = ReportUnsafe.objects.get(pk=report_id)
        except ObjectDoesNotExist:
            self.error = _('The report was not found, please recalculate the comparison cache')
            return None
        block = CompareBlock('u_%s' % report_id, 'unsafe', _('Unsafe'), 'unsafe')
        block.parents.append('c_%s' % parent_id)
        block.add_info = {'value': report.get_verdict_display(), 'color': UNSAFE_COLOR[report.verdict]}
        for a in report.attrs.order_by('attr__name__name'):
            attr_data = {
                'name': a.attr.name.name,
                'value': a.attr.value
            }
            if attr_data['name'] in JOBS_COMPARE_ATTRS[self.info.root1.job.type]:
                attr_data['color'] = '#8bb72c'
            block.list.append(attr_data)
        block.href = reverse('reports:leaf', args=['unsafe', report.pk])
        return block

    def __safe_data(self, report_id, parent_id):
        try:
            report = ReportSafe.objects.get(pk=report_id)
        except ObjectDoesNotExist:
            self.error = _('The report was not found, please recalculate the comparison cache')
            return None
        block = CompareBlock('s_%s' % report_id, 'safe', _('Safe'), 'safe')
        block.parents.append('c_%s' % parent_id)
        block.add_info = {'value': report.get_verdict_display(), 'color': SAFE_COLOR[report.verdict]}
        for a in report.attrs.order_by('attr__name__name'):
            attr_data = {
                'name': a.attr.name.name,
                'value': a.attr.value
            }
            if attr_data['name'] in JOBS_COMPARE_ATTRS[self.info.root1.job.type]:
                attr_data['color'] = '#8bb72c'
            block.list.append(attr_data)
        block.href = reverse('reports:leaf', args=['safe', report.pk])
        return block

    def __unknown_data(self, report_id, parent_id):
        try:
            report = ReportUnknown.objects.get(pk=report_id)
        except ObjectDoesNotExist:
            self.error = _('The report was not found, please recalculate the comparison cache')
            return None
        block = CompareBlock('f_%s' % report_id, 'unknown', _('Unknown'), 'unknown-%s' % report.component.name)
        block.parents.append('c_%s' % parent_id)
        problems = list(x.problem.name for x in report.markreport_set.order_by('id'))
        if len(problems) > 0:
            block.add_info = {
                'value': '; '.join(problems),
                'color': '#c60806'
            }
        else:
            block.add_info = {'value': _('Without marks')}
        for a in report.attrs.order_by('attr__name__name'):
            attr_data = {
                'name': a.attr.name.name,
                'value': a.attr.value
            }
            if attr_data['name'] in JOBS_COMPARE_ATTRS[self.info.root1.job.type]:
                attr_data['color'] = '#8bb72c'
            block.list.append(attr_data)
        block.href = reverse('reports:leaf', args=['unknown', report.pk])
        return block

    def __unsafe_mark_data(self, report_id):
        self.ccc = 0
        marks = MarkUnsafeReport.objects.filter(report_id=report_id)
        data = []
        for mark in marks:
            block = CompareBlock('um_%s' % mark.mark_id, 'mark', _('Unsafes mark'))
            block.parents.append('u_%s' % report_id)
            block.add_info = {'value': mark.mark.get_verdict_display(), 'color': UNSAFE_COLOR[mark.mark.verdict]}
            block.href = reverse('marks:edit_mark', args=['unsafe', mark.mark_id])
            for t in mark.mark.versions.order_by('-version')[0].tags.all():
                block.list.append({'name': None, 'value': t.tag.tag})
            data.append(block)
        return data

    def __safe_mark_data(self, report_id):
        self.ccc = 0
        marks = MarkSafeReport.objects.filter(report_id=report_id)
        data = []
        for mark in marks:
            block = CompareBlock('sm_%s' % mark.mark_id, 'mark', _('Safes mark'))
            block.parents.append('s_%s' % report_id)
            block.add_info = {'value': mark.mark.get_verdict_display(), 'color': SAFE_COLOR[mark.mark.verdict]}
            block.href = reverse('marks:edit_mark', args=['safe', mark.mark_id])
            data.append(block)
        return data

    def __unknown_mark_data(self, report_id):
        self.ccc = 0
        marks = MarkUnknownReport.objects.filter(report_id=report_id)
        data = []
        for mark in marks:
            block = CompareBlock("fm_%s" % mark.mark_id, 'mark', _('Unknowns mark'))
            block.parents.append('f_%s' % report_id)
            block.add_info = {'value': mark.problem.name}
            block.href = reverse('marks:edit_mark', args=['unknown', mark.mark_id])
            data.append(block)
        return data


class CompareBlock(object):
    def __init__(self, block_id, block_type, title, block_class=None):
        self.id = block_id
        self.block_class = block_class if block_class is not None else self.id
        self.type = block_type
        self.title = title
        self.parents = []
        self.list = []
        self.add_info = None
        self.href = None
