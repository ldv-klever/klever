from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.translation import activate
from reports.models import *
import jobs.job_functions as job_f
from django.utils.translation import ugettext as _
from _datetime import datetime
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
import json


@login_required
def report_root(request, report_id):
    activate(request.user.extended.language)
    report = ReportRoot.objects.get(pk=int(report_id))
    user_tz = request.user.extended.timezone
    delta = None
    if report.finish_date and report.start_date:
        delta = report.finish_date - report.start_date
    resources = ComponentResource.objects.filter(report=report)
    current_resource = ComponentResource()
    if report.resource:
        current_resource.resource = report.resource
        current_resource.component = report.component
    children = ReportComponent.objects.filter(parent=report)

    children_attr = []
    for child in children:
        attrs = child.attr.all()
        for attr in attrs:
            children_attr.append(attr.name)
    children_attr = set(children_attr)
    children_values = {}
    for child in children:
        attr_values = []
        for attr in children_attr:
            attr_values.append(child.attr.all().filter(name=attr))
        children_values[child] = attr_values

    return render(
        request,
        'reports/report_root.html',
        {
            'report': report,
            'user_tz': user_tz,
            'delta': delta,
            'resources': resources,
            'verdict': job_f.verdict_info(report),
            'unknowns': job_f.unknowns_info(report),
            'children_attr': children_attr,
            'children_values': children_values,
        }
    )


@login_required
def report_component(request, report_id):
    activate(request.user.extended.language)
    report = ReportComponent.objects.get(pk=int(report_id))
    user_tz = request.user.extended.timezone
    delta = None
    if report.finish_date and report.start_date:
        delta = report.finish_date - report.start_date
    resources = ComponentResource.objects.filter(report=report)
    current_resource = ComponentResource()
    current_resource.resource = report.resource
    current_resource.component = report.component
    children = ReportComponent.objects.filter(parent=report)

    children_attr = []
    for child in children:
        attrs = child.attr.all()
        for attr in attrs:
            children_attr.append(attr.name)
    children_attr = set(children_attr)
    children_values = {}
    for child in children:
        attr_values = []
        for attr in children_attr:
            attr_values.append(child.attr.all().filter(name=attr))
        children_values[child] = attr_values

    parents = {}
    parents_attr = []
    cur_report = report.parent
    while cur_report:
        attrs = cur_report.attr.all()
        for attr in attrs:
            parents_attr.append(attr.name)
        cur_report = cur_report.parent
    parents_attr = set(parents_attr)
    cur_report = report.parent
    while cur_report:
        attr_values = []
        for attr in parents_attr:
            attr_values.append(cur_report.attr.all().filter(name=attr))
        parents[ReportComponent.objects.get(pk=cur_report.id)] = attr_values
        cur_report = cur_report.parent

    return render(
        request,
        'reports/report_root.html',
        {
            'report': report,
            'user_tz': user_tz,
            'delta': delta,
            'resources': resources,
            'verdict': job_f.verdict_info(report),
            'unknowns': job_f.unknowns_info(report),
            'parents': parents,
            'parents_attr': parents_attr,
            'children_attr': children_attr,
            'children_values': children_values,
        }
    )


@login_required
def report_unsafes(request, report_id):
    activate(request.user.extended.language)
    user_tz = request.user.extended.timezone

    # Node which we intend to get all unsafes leaves for.
    report = ReportComponent.objects.get(pk=int(report_id))

    # Get all leaves..
    unsafes_id = ReportComponentLeaf.objects.filter(report=report)

    # List of Unsafes.
    unsafes = []
    for unsafe_id in unsafes_id:
        try:
            report_unsafe = ReportUnsafe.objects.get(pk=int(unsafe_id.leaf_id))
            unsafes.append(report_unsafe)
        except Exception:
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

    # Common part.
    json_start = json.loads(request.POST['start report'])
    is_root = False
    if json_start['id'] == '/':
        is_root = True

    # Attributes
    attr_values = []
    for attr_dict in json_start['attrs']:
        # Only 1 element in attributes
        if len(attr_dict) != 1:
            return JsonResponse({
                'error': 'Wrong attribute format "{0}"'.format(attr_dict)
            })
        for attr, value in attr_dict.items():
            attr_name, stub = AttrName.objects.get_or_create(name=attr)
            # Check if value is list
            attr_value, stub = Attr.objects.get_or_create(name=attr_name, value=value)
            attr_values.append(attr_value)

    # Computer
    computer_description = json_start['comp']
    if type(computer_description) is list:
        computer_description = ''
        for descr_attr in json_start['comp']:
            for attr, value in descr_attr.items():
                computer_description += attr + "='" + value + "'\n"
    computer, stub = Computer.objects.get_or_create(description=computer_description)

    # Component
    report_id = json_start['id']
    component, stub = Component.objects.get_or_create(name=report_id)

    # Job
    try:
        job = Job.objects.get(identifier=request.POST['job id'],
                              format=int(request.POST['job format']))
    except ObjectDoesNotExist:
        pass

    # Report
    if is_root:
        report = ReportRoot()
        report.identifier = request.POST['job id'] + report_id
        report.parent = None
        report.description = None

        report.component = component
        report.computer = computer
        report.resource = None
        report.log = None
        report.data = None
        report.start_date = datetime.now()
        report.finish_date = None

        report.user = request.user
        report.job = job
        report.last_request_date = report.start_date

        try:
            # Update.
            old_id = ReportRoot.objects.get(identifier=report.identifier).id
            report.id = old_id
        except ObjectDoesNotExist:
            pass

        report.save()

    for attr_value in attr_values:
        report.attr.add(attr_value)
    report.save()

    return HttpResponse('')
