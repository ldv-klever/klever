from io import BytesIO
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import activate, ugettext as _
from reports.models import *
from reports.UploadReport import UploadReport
from reports.utils import *
from jobs.ViewJobData import ViewJobData


@login_required
def report_component(request, job_id, report_id):
    activate(request.user.extended.language)

    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('jobs:error', args=[404]))

    if not job_f.JobAccess(request.user, job).can_view():
        return HttpResponseRedirect(reverse('jobs:error', args=[400]))
    try:
        report = ReportComponent.objects.get(pk=int(report_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('jobs:error', args=[504]))

    duration = None
    if report.finish_date is not None:
        duration = report.finish_date - report.start_date

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

    unknown = None
    try:
        unknown = ReportUnknown.objects.get(parent=report).problem_description
    except ObjectDoesNotExist:
        pass

    children_data = ReportAttrs(*report_attrs_data)
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
            'SalfAttrsData': ReportAttrs(request.user, report).get_table_data(),
            'ChildrenAttrsData': children_data.get_table_data(True),
            'attr_filters': children_data,
            'unknown': unknown,
        }
    )


@login_required
def report_unsafes(request, report_id):
    activate(request.user.extended.language)
    user_tz = request.user.extended.timezone

    # Node which we intend to get all unsafes leaves for.
    report = ReportComponent.objects.get(pk=int(report_id))

    # Get all leaves..
    unsafes_id = ReportComponentLeaf.objects.filter(
        Q(report=report) & ~Q(unsafe=None))

    # List of Unsafes.
    unsafes = []
    for unsafe_id in unsafes_id:
        try:
            unsafes.append(ReportUnsafe.objects.get(pk=int(unsafe_id.unsafe.pk)))
        except ObjectDoesNotExist:
            pass

    attrs = []
    for unsafe in unsafes:
        attr = ReportAttr.objects.filter(report_id=unsafe.id)
        for attr in attr:
            attrs.append(attr.attr)
    attrs = list(set(attrs))

    unsafes_values = {}
    for unsafe in unsafes:
        attr_values = []
        report_attr = ReportAttr.objects.filter(report_id=unsafe.id)
        for attr in attrs:
            attr_values.append(report_attr.filter(attr=attr))
        unsafes_values[unsafe] = attr_values

    return render(
        request,
        'reports/report_list.html',
        {
            'user_tz': user_tz,
            'attrs': attrs,
            'reports_values': unsafes_values,
            'title': _('Unsafes')
        }
    )


@login_required
def report_safes(request, report_id):
    activate(request.user.extended.language)
    user_tz = request.user.extended.timezone

    # Node which we intend to get all safes leaves for.
    report = ReportComponent.objects.get(pk=int(report_id))

    # Get all leaves..
    safes_id = ReportComponentLeaf.objects.filter(report=report)

    # List of safes.
    safes = []
    for safe_id in safes_id:
        try:
            report_safe = ReportSafe.objects.get(pk=int(safe_id.leaf_id))
            safes.append(report_safe)
        except Exception:
            pass

    attrs = []
    for safe in safes:
        attr = ReportAttr.objects.filter(report_id=safe.id)
        for attr in attr:
            attrs.append(attr.attr)
    attrs = list(set(attrs))

    safes_values = {}
    for safe in safes:
        attr_values = []
        report_attr = ReportAttr.objects.filter(report_id=safe.id)
        for attr in attrs:
            attr_values.append(report_attr.filter(attr=attr))
        safes_values[safe] = attr_values

    return render(
        request,
        'reports/report_list.html',
        {
            'user_tz': user_tz,
            'attrs': attrs,
            'reports_values': safes_values,
            'title': _('Safes')
        }
    )


@login_required
def report_unknowns(request, report_id):
    activate(request.user.extended.language)
    user_tz = request.user.extended.timezone

    # Node which we intend to get all unknowns leaves for.
    report = ReportComponent.objects.get(pk=int(report_id))

    # Get all leaves.
    unknowns_id = ReportComponentLeaf.objects.filter(report=report)

    # List of unknowns.
    unknowns = []
    for unknown_id in unknowns_id:
        try:
            report_unknown = ReportUnknown.objects.get(pk=int(unknown_id.leaf_id))
            unknowns.append(report_unknown)
        except Exception:
            pass

    attrs = []
    for unknown in unknowns:
        attr = ReportAttr.objects.filter(report_id=unknown.id)
        for attr in attr:
            attrs.append(attr.attr)
    attrs = list(set(attrs))

    unknowns_values = {}
    for unknown in unknowns:
        attr_values = []
        report_attr = ReportAttr.objects.filter(report_id=unknown.id)
        for attr in attrs:
            attr_values.append(report_attr.filter(attr=attr))
        unknowns_values[unknown] = attr_values

    return render(
        request,
        'reports/report_list.html',
        {
            'user_tz': user_tz,
            'attrs': attrs,
            'reports_values': unknowns_values,
            'title': _('Unknowns')
        }
    )


@login_required
def report_unsafe(request, report_id):
    activate(request.user.extended.language)
    user_tz = request.user.extended.timezone

    unsafe = ReportUnsafe.objects.get(pk=int(report_id))

    parents = {}
    parents_attr = []
    cur_report = unsafe.parent
    while cur_report:
        attrs = cur_report.attr.all()
        for attr in attrs:
            parents_attr.append(attr.name)
        cur_report = cur_report.parent
    parents_attr = set(parents_attr)
    cur_report = unsafe.parent
    while cur_report:
        attr_values = []
        for attr in parents_attr:
            attr_values.append(cur_report.attr.all().filter(name=attr))
        parents[ReportComponent.objects.get(pk=cur_report.id)] = attr_values
        cur_report = cur_report.parent

    attrs = ReportAttr.objects.filter(report=unsafe)

    return render(
        request,
        'reports/report_unsafe.html',
        {
            'user_tz': user_tz,
            'attrs': attrs,
            'unsafe': unsafe,
            'parents': parents,
            'parents_attr': parents_attr,
        }
    )


@login_required
def report_safe(request, report_id):
    activate(request.user.extended.language)
    user_tz = request.user.extended.timezone

    safe = ReportSafe.objects.get(pk=int(report_id))

    parents = {}
    parents_attr = []
    cur_report = safe.parent
    while cur_report:
        attrs = cur_report.attr.all()
        for attr in attrs:
            parents_attr.append(attr.name)
        cur_report = cur_report.parent
    parents_attr = set(parents_attr)
    cur_report = safe.parent
    while cur_report:
        attr_values = []
        for attr in parents_attr:
            attr_values.append(cur_report.attr.all().filter(name=attr))
        parents[ReportComponent.objects.get(pk=cur_report.id)] = attr_values
        cur_report = cur_report.parent

    attrs = ReportAttr.objects.filter(report=safe)

    return render(
        request,
        'reports/report_safe.html',
        {
            'user_tz': user_tz,
            'attrs': attrs,
            'safe': safe,
            'parents': parents,
            'parents_attr': parents_attr,
        }
    )


@login_required
def report_unknown(request, report_id):
    activate(request.user.extended.language)
    user_tz = request.user.extended.timezone

    unknown = ReportUnknown.objects.get(pk=int(report_id))

    parents = {}
    parents_attr = []
    cur_report = unknown.parent
    while cur_report:
        attrs = cur_report.attr.all()
        for attr in attrs:
            parents_attr.append(attr.name)
        cur_report = cur_report.parent
    parents_attr = set(parents_attr)
    cur_report = unknown.parent
    while cur_report:
        attr_values = []
        for attr in parents_attr:
            attr_values.append(cur_report.attr.all().filter(name=attr))
        parents[ReportComponent.objects.get(pk=cur_report.id)] = attr_values
        cur_report = cur_report.parent

    attrs = ReportAttr.objects.filter(report=unknown)

    return render(
        request,
        'reports/report_unknown.html',
        {
            'user_tz': user_tz,
            'attrs': attrs,
            'unknown': unknown,
            'parents': parents,
            'parents_attr': parents_attr,
        }
    )


@login_required
def upload_report(request):
    # TODO: check that session has job_id
    if request.method != 'POST':
        return JsonResponse({'error': 'Get request is not supported'})
    try:
        job = Job.objects.get(pk=int(request.session['job_id']))
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'The job was not found'})

    error = UploadReport(request.user, job,
                         json.loads(request.POST.get('report', '{}'))).error
    if error is not None:
        print(error)
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

    if not job_f.JobAccess(request.user, report.root.job).can_view():
        return HttpResponseRedirect(reverse('jobs:error', args=[400]))

    if report.log is None or len(report.log) == 0:
        return HttpResponseRedirect(reverse('jobs:error', args=[500]))
    new_file = BytesIO(report.log)
    response = HttpResponse(new_file.read(), content_type='text/plain')
    response['Content-Disposition'] = 'attachment; filename="log"'
    return response
