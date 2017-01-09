#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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

from io import BytesIO
from urllib.parse import quote
from wsgiref.util import FileWrapper
from django.contrib.auth.decorators import login_required
from django.core.exceptions import MultipleObjectsReturned
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, StreamingHttpResponse
from django.shortcuts import render
from django.utils.translation import ugettext as _, activate, string_concat
from django.template.defaulttags import register
from bridge.vars import JOB_STATUS
from bridge.utils import unparallel_group, ArchiveFileContent
from jobs.ViewJobData import ViewJobData
from jobs.utils import JobAccess
from marks.tables import ReportMarkTable
from marks.utils import MarkAccess
from marks.models import UnsafeTag, SafeTag, MarkSafe, MarkUnsafe
from reports.UploadReport import UploadReport
from reports.models import *
from reports.utils import *
from reports.etv import GetSource, GetETV
from reports.comparison import CompareTree, ComparisonTableData, ComparisonData, can_compare


# These filters are used for visualization component specific data. They should not be used for any other purposes.
@register.filter
def get_dict_val(d, key):
    return d.get(key)


@register.filter
def sort_list(l):
    return sorted(l)


@register.filter
def sort_bugs_list(l):
    return sorted(l, key=lambda bug: bug[12:].lstrip('~'))


@login_required
@unparallel_group(['ReportComponent'])
def report_component(request, job_id, report_id):
    activate(request.user.extended.language)

    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[404]))

    if not JobAccess(request.user, job).can_view():
        return HttpResponseRedirect(reverse('error', args=[400]))
    try:
        report = ReportComponent.objects.get(pk=int(report_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[504]))

    duration = None
    status = 1
    if report.finish_date is not None:
        duration = report.finish_date - report.start_date
        status = 2

    view_args = [request.user, report]
    report_attrs_data = [request.user, report]
    if request.method == 'POST':
        view_type = request.POST.get('view_type', None)
        if view_type == '2':
            view_args.append(request.POST.get('view', None))
            view_args.append(request.POST.get('view_id', None))
        elif view_type == '3':
            report_attrs_data.append(request.POST.get('view', None))
            report_attrs_data.append(request.POST.get('view_id', None))

    unknown_href = None
    try:
        unknown_href = reverse('reports:leaf', args=[
            'unknown', ReportUnknown.objects.get(parent=report, component=report.component).pk
        ])
        status = 3
    except ObjectDoesNotExist:
        pass
    except MultipleObjectsReturned:
        status = 4

    report_data = None
    if report.data:
        try:
            with report.data.file as fp:
                report_data = json.loads(fp.read().decode('utf8'))
        except Exception as e:
            logger.exception("Json parsing error: %s" % e, stack_info=True)

    return render(
        request,
        'reports/ReportMain.html',
        {
            'report': report,
            'duration': duration,
            'resources': report_resources(report, request.user),
            'computer': computer_description(report.computer.description),
            'reportdata': ViewJobData(*view_args),
            'parents': get_parents(report),
            'SelfAttrsData': ReportTable(*report_attrs_data).table_data,
            'TableData': ReportTable(*report_attrs_data, table_type='3'),
            'status': status,
            'unknown': unknown_href,
            'data': report_data
        }
    )


@login_required
@unparallel_group(['ReportComponent', 'ReportSafe', 'ReportUnsafe', 'ReportUnknown'])
def report_list(request, report_id, ltype, component_id=None,
                verdict=None, tag=None, problem=None, mark=None, attr=None):
    activate(request.user.extended.language)

    try:
        report = ReportComponent.objects.get(pk=int(report_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[504]))

    if not JobAccess(request.user, report.root.job).can_view():
        return HttpResponseRedirect(reverse('error', args=[400]))

    list_types = {
        'unsafes': '4',
        'safes': '5',
        'unknowns': '6'
    }

    if ltype == 'safes':
        title = _("All safes")
        if tag is not None:
            title = string_concat(_("Safes"), ': ', tag)
        elif verdict is not None:
            for s in SAFE_VERDICTS:
                if s[0] == verdict:
                    title = string_concat(_("Safes"), ': ', s[1])
                    break
        elif mark is not None:
            title = _('Safes marked by')
        elif attr is not None:
            title = _('Safes where %(a_name)s is %(a_val)s') % {'a_name': attr.name.name, 'a_val': attr.value}
    elif ltype == 'unsafes':
        title = _("All unsafes")
        if tag is not None:
            title = string_concat(_("Unsafes"), ': ', tag)
        elif verdict is not None:
            for s in UNSAFE_VERDICTS:
                if s[0] == verdict:
                    title = string_concat(_("Unsafes"), ': ', s[1])
                    break
        elif mark is not None:
            title = _('Unsafes marked by')
        elif attr is not None:
            title = _('Unsafes where %(a_name)s is %(a_val)s') % {'a_name': attr.name.name, 'a_val': attr.value}
    else:
        title = _("All unknowns")
        if isinstance(problem, UnknownProblem):
            title = string_concat(_("Unknowns"), ': ', problem.name)
        elif problem == 0:
            title = string_concat(_("Unknowns without marks"))
        elif mark is not None:
            title = _('Unknowns marked by')
        elif attr is not None:
            title = _('Unknowns where %(a_name)s is %(a_val)s') % {'a_name': attr.name.name, 'a_val': attr.value}
    if mark is not None:
        title = string_concat(title, mark.identifier[:10])

    report_attrs_data = [request.user, report]
    if request.method == 'POST':
        if request.POST.get('view_type', None) == list_types[ltype]:
            report_attrs_data.append(request.POST.get('view', None))
            report_attrs_data.append(request.POST.get('view_id', None))

    table_data = ReportTable(
        *report_attrs_data, table_type=list_types[ltype],
        component_id=component_id, verdict=verdict, tag=tag, problem=problem, mark=mark, attr=attr
    )
    # If there is only one element in table, and first column of table is link, redirect to this link
    if len(table_data.table_data['values']) == 1 and isinstance(table_data.table_data['values'][0], list) \
            and len(table_data.table_data['values'][0]) > 0 and 'href' in table_data.table_data['values'][0][0] \
            and table_data.table_data['values'][0][0]['href']:
        return HttpResponseRedirect(table_data.table_data['values'][0][0]['href'])
    return render(
        request,
        'reports/report_list.html',
        {
            'report': report,
            'parents': get_parents(report),
            'TableData': table_data,
            'view_type': list_types[ltype],
            'title': title
        }
    )


@login_required
@unparallel_group(['UnsafeTag', 'SafeTag'])
def report_list_tag(request, report_id, ltype, tag_id):
    try:
        if ltype == 'unsafes':
            tag = UnsafeTag.objects.get(pk=int(tag_id))
        else:
            tag = SafeTag.objects.get(pk=int(tag_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[509]))
    return report_list(request, report_id, ltype, tag=tag.tag)


@login_required
def report_list_by_verdict(request, report_id, ltype, verdict):
    return report_list(request, report_id, ltype, verdict=verdict)


@login_required
@unparallel_group(['MarkSafe', 'MarkUnsafe', 'MarkUnknown'])
def report_list_by_mark(request, report_id, ltype, mark_id):
    tables = {
        'safes': MarkSafe,
        'unsafes': MarkUnsafe,
        'unknowns': MarkUnknown
    }
    try:
        return report_list(request, report_id, ltype, mark=tables[ltype].objects.get(pk=mark_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[604]))


@login_required
@unparallel_group(['Attr'])
def report_list_by_attr(request, report_id, ltype, attr_id):
    try:
        return report_list(request, report_id, ltype, attr=Attr.objects.get(pk=attr_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[704]))


@login_required
def report_unknowns(request, report_id, component_id):
    return report_list(request, report_id, 'unknowns', component_id=component_id)


@login_required
@unparallel_group(['UnknownProblem'])
def report_unknowns_by_problem(request, report_id, component_id, problem_id):
    problem_id = int(problem_id)
    if problem_id == 0:
        problem = 0
    else:
        try:
            problem = UnknownProblem.objects.get(pk=problem_id)
        except ObjectDoesNotExist:
            return HttpResponseRedirect(reverse('error', args=[508]))
    return report_list(request, report_id, 'unknowns', component_id=component_id, problem=problem)


@login_required
@unparallel_group(['ReportUnsafe', 'ReportSafe', 'ReportUnknown'])
def report_leaf(request, leaf_type, report_id):
    activate(request.user.extended.language)

    tables = {
        'unknown': ReportUnknown,
        'safe': ReportSafe,
        'unsafe': ReportUnsafe
    }
    if leaf_type not in tables:
        return HttpResponseRedirect(reverse('error', args=[500]))

    try:
        report = tables[leaf_type].objects.get(pk=int(report_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[504]))

    if not JobAccess(request.user, report.root.job).can_view():
        return HttpResponseRedirect(reverse('error', args=[400]))

    template = 'reports/report_leaf.html'
    etv = None
    main_file_content = None
    if leaf_type == 'unsafe':
        template = 'reports/report_unsafe.html'
        try:
            etv = GetETV(ArchiveFileContent(report, report.error_trace).content.decode('utf8'), request.user)
        except Exception as e:
            logger.exception(e, stack_info=True)
            return HttpResponseRedirect(reverse('error', args=[505]))
    elif leaf_type == 'safe':
        main_file_content = None
        if report.archive and report.proof:
            try:
                main_file_content = ArchiveFileContent(report, report.proof).content.decode('utf8')
            except Exception as e:
                logger.exception("Couldn't extract proof from archive: %s" % e)
                return HttpResponseRedirect(reverse('error', args=[500]))
    elif leaf_type == 'unknown':
        try:
            main_file_content = ArchiveFileContent(report, report.problem_description).content.decode('utf8')
        except Exception as e:
            logger.exception("Couldn't extract problem description from archive: %s" % e)
            return HttpResponseRedirect(reverse('error', args=[500]))
    try:
        return render(
            request, template,
            {
                'type': leaf_type,
                'report': report,
                'parents': get_parents(report),
                'SelfAttrsData': ReportTable(request.user, report).table_data,
                'MarkTable': ReportMarkTable(request.user, report),
                'etv': etv,
                'can_mark': MarkAccess(request.user, report=report).can_create(),
                'main_content': main_file_content,
                'include_assumptions': request.user.extended.assumptions
            }
        )
    except Exception as e:
        logger.exception("Error while visualizing error trace: %s" % e, stack_info=True)
        return HttpResponseRedirect(reverse('error', args=[500]))


@login_required
@unparallel_group(['ReportUnsafe'])
def report_etv_full(request, report_id):
    activate(request.user.extended.language)

    try:
        report = ReportUnsafe.objects.get(pk=int(report_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[504]))

    if not JobAccess(request.user, report.root.job).can_view():
        return HttpResponseRedirect(reverse('error', args=[400]))
    try:
        return render(request, 'reports/etv_fullscreen.html', {
            'report': report,
            'etv': GetETV(ArchiveFileContent(report, report.error_trace).content.decode('utf8'), request.user),
            'include_assumptions': request.user.extended.assumptions
        })
    except Exception as e:
        logger.exception(e, stack_info=True)
        return HttpResponseRedirect(reverse('error', args=[505]))


@unparallel_group([ReportRoot, AttrName])
def upload_report(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signed in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Get request is not supported'})
    if 'job id' not in request.session:
        return JsonResponse({'error': 'The job id was not found in session'})
    try:
        job = Job.objects.get(pk=int(request.session['job id']))
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'The job was not found'})
    except ValueError:
        return JsonResponse({'error': 'Unknown error'})
    if not JobAccess(request.user, job).klever_core_access():
        return JsonResponse({
            'error': "User '%s' don't have access to upload report for job '%s'" %
                     (request.user.username, job.identifier)
        })
    if job.status != JOB_STATUS[2][0]:
        return JsonResponse({'error': 'Reports can be uploaded only for processing jobs'})
    try:
        data = json.loads(request.POST.get('report', '{}'))
    except Exception as e:
        logger.exception("Json parsing error: %s" % e, stack_info=True)
        return JsonResponse({'error': 'Can not parse json data'})
    archive = None
    for f in request.FILES.getlist('file'):
        archive = f
    err = UploadReport(job, data, archive).error
    if err is not None:
        return JsonResponse({'error': err})
    return JsonResponse({})


@login_required
@unparallel_group(['ReportComponent'])
def get_component_log(request, report_id):
    report_id = int(report_id)
    try:
        report = ReportComponent.objects.get(pk=int(report_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[504]))

    if not JobAccess(request.user, report.root.job).can_view():
        return HttpResponseRedirect(reverse('error', args=[400]))

    if report.log is None:
        return HttpResponseRedirect(reverse('error', args=[500]))
    logname = '%s-log.txt' % report.component.name

    try:
        content = ArchiveFileContent(report, report.log).content
    except Exception as e:
        logger.exception(str(e))
        return HttpResponseRedirect(reverse('error', args=[500]))

    response = StreamingHttpResponse(FileWrapper(BytesIO(content), 8192), content_type='text/plain')
    response['Content-Length'] = len(content)
    response['Content-Disposition'] = 'attachment; filename="%s"' % quote(logname)
    return response


@login_required
@unparallel_group(['ReportComponent'])
def get_log_content(request, report_id):
    report_id = int(report_id)
    try:
        report = ReportComponent.objects.get(pk=int(report_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[504]))

    if not JobAccess(request.user, report.root.job).can_view():
        return HttpResponseRedirect(reverse('error', args=[400]))

    if report.log is None:
        return HttpResponseRedirect(reverse('error', args=[500]))

    try:
        content = ArchiveFileContent(report, report.log).content
    except Exception as e:
        logger.exception(str(e))
        return HttpResponse(str(_('Extraction of the component log from archive failed')))

    if len(content) > 10**5:
        return HttpResponse(str(_('The component log is huge and can not be showed but you can download it')))
    return HttpResponse(content.decode('utf8'))


@login_required
@unparallel_group(['ReportUnsafe'])
def get_source_code(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    if 'report_id' not in request.POST:
        return JsonResponse({'error': 'Unknown error'})
    if 'file_name' not in request.POST:
        return JsonResponse({'error': 'Unknown error'})

    result = GetSource(request.POST['report_id'], request.POST['file_name'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    filename = request.POST['file_name']
    if len(filename) > 50:
        filename = '.../' + filename[-50:].split('/', 1)[-1]
    return JsonResponse({
        'content': result.data, 'name': filename, 'fullname': request.POST['file_name']
    })


@login_required
@unparallel_group(['Job', 'ReportRoot', CompareJobsInfo])
def fill_compare_cache(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    try:
        j1 = Job.objects.get(pk=request.POST.get('job1', 0))
        j2 = Job.objects.get(pk=request.POST.get('job2', 0))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('One of the selected jobs was not found, please reload page')})
    if not can_compare(request.user, j1, j2):
        return JsonResponse({'error': _("You can't compare the selected jobs")})
    try:
        CompareTree(request.user, j1, j2)
    except Exception as e:
        logger.exception("Comparison of reports' trees failed: %s" % e, stack_info=True)
        return JsonResponse({'error': 'Unknown error while filling comparison cache'})
    return JsonResponse({})


@login_required
@unparallel_group([CompareJobsInfo])
def jobs_comparison(request, job1_id, job2_id):
    activate(request.user.extended.language)
    try:
        job1 = Job.objects.get(pk=job1_id)
        job2 = Job.objects.get(pk=job2_id)
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[405]))
    if not can_compare(request.user, job1, job2):
        return HttpResponseRedirect(reverse('error', args=[507]))
    tabledata = ComparisonTableData(request.user, job1, job2)
    if tabledata.error is not None:
        return HttpResponseRedirect(reverse('error', args=[506]))
    return render(
        request, 'reports/comparison.html',
        {
            'job1': job1,
            'job2': job2,
            'tabledata': tabledata.data,
            'compare_info': tabledata.info,
            'attrs': tabledata.attrs
        }
    )


@login_required
@unparallel_group([CompareJobsInfo])
def get_compare_jobs_data(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    if 'info_id' not in request.POST:
        return JsonResponse({'error': 'Unknown error'})
    if all(x not in request.POST for x in ['verdict', 'attrs']):
        return JsonResponse({'error': 'Unknown error'})
    result = ComparisonData(
        request.POST['info_id'],
        int(request.POST.get('page_num', 1)),
        True if 'hide_attrs' in request.POST else False,
        True if 'hide_components' in request.POST else False,
        request.POST.get('verdict', None),
        request.POST.get('attrs', None)
    )
    if result.error is not None:
        return JsonResponse({'error': str(result.error)})
    v1 = result.v1
    v2 = result.v2
    for v in COMPARE_VERDICT:
        if result.v1 == v[0]:
            v1 = v[1]
        if result.v2 == v[0]:
            v2 = v[1]
    return render(
        request, 'reports/comparisonData.html',
        {
            'verdict1': v1,
            'verdict2': v2,
            'job1': result.info.root1.job,
            'job2': result.info.root2.job,
            'data': result.data,
            'pages': result.pages,
            'verdict': request.POST.get('verdict', None),
            'attrs': request.POST.get('attrs', None)
        }
    )


@login_required
@unparallel_group(['ReportComponent'])
def download_report_files(request, report_id):
    try:
        report = ReportComponent.objects.get(pk=int(report_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[504]))
    if not report.archive:
        return HttpResponseRedirect(reverse('error', args=[500]))

    response = StreamingHttpResponse(FileWrapper(report.archive.file, 8192), content_type='application/x-tar-gz')
    response['Content-Length'] = len(report.archive.file)
    response['Content-Disposition'] = 'attachment; filename="%s files.zip"' % report.component.name
    return response


@login_required
@unparallel_group(['ReportUnsafe'])
def download_error_trace(request, report_id):
    if request.method != 'GET':
        return HttpResponseRedirect(reverse('error', args=[500]))
    try:
        report = ReportUnsafe.objects.get(id=report_id)
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[504]))
    content = ArchiveFileContent(report, report.error_trace).content
    response = StreamingHttpResponse(FileWrapper(BytesIO(content), 8192), content_type='application/x-tar-gz')
    response['Content-Length'] = len(content)
    response['Content-Disposition'] = 'attachment; filename="error-trace.json"'
    return response
