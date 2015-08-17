from io import BytesIO
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import activate
from jobs.ViewJobData import ViewJobData
from jobs.utils import JobAccess
from jobs.models import Job
from marks.utils import ReportMarkTable
from reports.UploadReport import UploadReport
from reports.models import *
from reports.utils import *


@login_required
def report_component(request, job_id, report_id):
    activate(request.user.extended.language)

    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('jobs:error', args=[404]))

    if not JobAccess(request.user, job).can_view():
        return HttpResponseRedirect(reverse('jobs:error', args=[400]))
    try:
        report = ReportComponent.objects.get(pk=int(report_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('jobs:error', args=[504]))

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
        unknown = ReportUnknown.objects.get(parent=report)
        unknown_href = reverse('reports:leaf',
                               args=['unknown', unknown.pk])
        status = 3
    except ObjectDoesNotExist:
        pass

    children_data = ReportTable(*report_attrs_data, table_type='3')
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
            'ChildrenAttrsData': children_data.table_data,
            'attr_filters': children_data,
            'status': status,
            'unknown': unknown_href,
        }
    )


@login_required
def report_list(request, report_id, ltype, component_id=None, verdict=None):
    activate(request.user.extended.language)

    try:
        report = ReportComponent.objects.get(pk=int(report_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('jobs:error', args=[504]))

    if not JobAccess(request.user, report.root.job).can_view():
        return HttpResponseRedirect(reverse('jobs:error', args=[400]))

    list_types = {
        'unsafes': '4',
        'safes': '5',
        'unknowns': '6'
    }
    report_attrs_data = [request.user, report]
    if request.method == 'POST':
        if request.POST.get('view_type', None) == list_types[ltype]:
            report_attrs_data.append(request.POST.get('view', None))
            report_attrs_data.append(request.POST.get('view_id', None))

    list_data = ReportTable(*report_attrs_data, table_type=list_types[ltype],
                            component_id=component_id, verdict=verdict)
    return render(
        request,
        'reports/report_list.html',
        {
            'report': report,
            'parents': get_parents(report),
            'SelfAttrsData': ReportTable(*report_attrs_data).table_data,
            'ChildrenAttrsData': list_data.table_data,
            'attr_filters': list_data,
            'view_type': list_types[ltype],
        }
    )


@login_required
def report_list_by_verdict(request, report_id, ltype, verdict):
    return report_list(request, report_id, ltype, verdict)


@login_required
def report_unknowns(request, report_id, component_id):
    activate(request.user.extended.language)
    return report_list(request, report_id, 'unknowns', component_id)


@login_required
def report_leaf(request, leaf_type, report_id):
    activate(request.user.extended.language)

    tables = {
        'unknown': ReportUnknown,
        'safe': ReportSafe,
        'unsafe': ReportUnsafe
    }
    if leaf_type not in tables:
        return HttpResponseRedirect(reverse('jobs:error', args=[500]))

    try:
        report = tables[leaf_type].objects.get(pk=int(report_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('jobs:error', args=[504]))

    if not JobAccess(request.user, report.root.job).can_view():
        return HttpResponseRedirect(reverse('jobs:error', args=[400]))

    return render(
        request,
        'reports/report_leaf.html',
        {
            'type': leaf_type,
            'title': report.identifier.split('##')[-1],
            'report': report,
            'parents': get_parents(report),
            'SelfAttrsData': ReportTable(request.user, report).table_data,
            'MarkTable': ReportMarkTable(report)
        }
    )


@login_required
def upload_report(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Get request is not supported'})
    try:
        job = Job.objects.get(pk=int(request.session['job_id']))
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'The job was not found'})

    error = UploadReport(request.user, job,
                         json.loads(request.POST.get('report', '{}'))).error
    if error is not None:
        return JsonResponse({'error': error})
    return JsonResponse({})


@login_required
def clear_tables(request):
    cnt1 = 0
    for res in Resource.objects.all():
        if len(res.resource_report_set.all()) == \
                len(res.resource_cache_set.all()) == 0:
            cnt1 += 1
            res.delete()
    deleted1 = []
    for component in Component.objects.all():
        if len(component.component_reports.all()) == \
                len(component.component_cache1_set.all()) == \
                len(component.component_cache2_set.all()) == \
                len(component.component_cache3_set.all()) == 0:
            deleted1.append(component.name)
            component.delete()

    deleted2 = []
    for computer in Computer.objects.all():
        if len(computer.computer_reports.all()) == 0:
            deleted2.append(computer.description)
            computer.delete()
    response = ''
    if cnt1 > 0:
        response += '<h3>Number of deleted resources: %s </h1>' % str(cnt1)
    if len(deleted1) > 0:
        response += '<h3>Deleted components:</h3><ul>'
        for d in deleted1:
            response += "<li>%s</li>" % str(d)
        response += '</ul>'
    if len(deleted2) > 0:
        response += '<h3>Deleted computers:</h3><ul>'
        for d in deleted2:
            response += "<li>%s</li>" % str(d)
        response += '</ul>'
    if len(response) == 0:
        response = '<h3>Tables are already cleared.</h3>'
    return HttpResponse(response)


@login_required
def get_component_log(request, report_id):
    report_id = int(report_id)
    try:
        report = ReportComponent.objects.get(pk=int(report_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('jobs:error', args=[504]))

    if not JobAccess(request.user, report.root.job).can_view():
        return HttpResponseRedirect(reverse('jobs:error', args=[400]))

    if report.log is None or len(report.log) == 0:
        return HttpResponseRedirect(reverse('jobs:error', args=[500]))
    new_file = BytesIO(report.log)
    response = HttpResponse(new_file.read(), content_type='text/plain')
    response['Content-Disposition'] = 'attachment; filename="log"'
    return response


@login_required
def get_log_content(request, report_id):
    report_id = int(report_id)
    try:
        report = ReportComponent.objects.get(pk=int(report_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('jobs:error', args=[504]))

    if not JobAccess(request.user, report.root.job).can_view():
        return HttpResponseRedirect(reverse('jobs:error', args=[400]))

    if report.log is None or len(report.log) == 0:
        return HttpResponseRedirect(reverse('jobs:error', args=[500]))
    return HttpResponse(report.log)
