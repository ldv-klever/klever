from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.translation import activate
from reports.models import *
from jobs.job_model import *
import jobs.job_functions as job_f
from django.utils.translation import ugettext as _
from _datetime import datetime
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, JsonResponse
import json
from django.db.models import Q


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
            if not children_attr.__contains__(attr.name):
                children_attr.append(attr.name)
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


def get_attr(attr, value, attr_values):
    if type(value) is list:
        for elem in value:
            for elem_attr, elem_value in elem.items():
                get_attr(attr+'::'+elem_attr, elem_value, attr_values)
    else:
        attr_name, stub = AttrName.objects.get_or_create(name=attr)
        attr_value, stub = Attr.objects.get_or_create(name=attr_name, value=value)
        attr_values.append(attr_value)


@login_required
def upload_report(request, is_root=False):

    # Common part.
    json_start = json.loads(request.POST['report'])

    # Current report identifier suffix
    report_id = json_start['id']

    # Job
    job = Job.objects.get(pk=request.session['job_id'])

    # Attributes
    attr_values = []
    if 'attrs' in json_start:
        for attr_dict in json_start['attrs']:
            # Only 1 element in attributes
            if len(attr_dict) != 1:
                return JsonResponse({
                    'error': 'Wrong attribute format "{0}"'.format(attr_dict)
                })

            for attr, value in attr_dict.items():
                get_attr(attr, value, attr_values)

    # Parent
    parent = None
    update_report = None
    if not is_root:
        parent_id = None
        if 'parent id' in json_start:
            parent_id = json_start['parent id']
            parent = ReportComponent.objects.get(Q(identifier__startswith=job.identifier) &
                                                 Q(identifier__endswith='/'+parent_id))
        else:
            update_report = ReportComponent.objects.get(Q(identifier__startswith=job.identifier) &
                                                        Q(identifier__endswith='/'+report_id))
            if job.reportroot.id == update_report.id:
                is_root = True

    # Resource
    resource = None
    if 'resources' in json_start:
        wall_time = json_start['resources']['wall time']
        cpu_time = json_start['resources']['CPU time']
        memory = json_start['resources']['max mem size']
        resource, stub = Resource.objects.get_or_create(wall_time=wall_time, cpu_time=cpu_time, memory=memory)

    # Identifier
    identifier = None
    if not is_root:
        if not update_report:
            identifier = parent.identifier + '/' + report_id
        else:
            pass  # update
    else:
        identifier = job.identifier + '/' + report_id

    # Computer
    computer = None
    if 'comp' in json_start:
        computer_description = json_start['comp']
        if type(computer_description) is list:
            computer_description = ''
            for descr_attr in json_start['comp']:
                for attr, value in descr_attr.items():
                    computer_description += attr + "='" + value + "'\n"
            computer, stub = Computer.objects.get_or_create(description=computer_description)
    elif not is_root:
        if not update_report:
            computer = parent.computer

    # Component
    component = None
    if not is_root:
        if 'name' in json_start:
            component, stub = Component.objects.get_or_create(name=json_start['name'])
    else:
        component, stub = Component.objects.get_or_create(name=report_id)

    # Logs
    log = None
    description = None
    data = None
    if 'log' in json_start:
        log = json_start['log']
    if 'description' in json_start:
        description = json_start['description']
    if 'data' in json_start:
        data = json_start['data']

    report_type = json_start['type']

    # Report
    if is_root:
        if not update_report:
            # Create root report
            report = ReportRoot()
            report.identifier = identifier
            report.parent = None
            report.description = description

            report.component = component
            report.computer = computer
            report.resource = resource
            report.log = log
            report.data = data
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

            status = JobStatus.objects.get(job=job)
            status.status = '1'
            status.save()
        else:
            # Update root report
            update_report.description = description
            update_report.resource = resource
            update_report.data = data
            update_report.log = log
            update_report.finish_date = datetime.now()
            update_report.save()

            ComponentResource.objects.update_or_create(component=update_report.component,
                                                       report=update_report,
                                                       defaults={'resource': resource})

            status = JobStatus.objects.get(job=job)
            is_failed = False
            for child in Report.objects.filter(parent=update_report):
                if isinstance(child, ReportUnknown):
                    is_failed = True
                    status.status = '4'
            if not is_failed:
                status.status = '3'
            status.save()
    elif report_type == 'start' or report_type == 'verification':
        # Create component report
        report = ReportComponent()
        report.identifier = identifier
        report.parent = parent
        report.description = description

        report.component = component
        report.computer = computer
        report.resource = resource
        report.log = log
        report.data = data
        report.start_date = datetime.now()
        report.finish_date = None

        try:
            # Update.
            old_id = ReportComponent.objects.get(identifier=report.identifier).id
            report.id = old_id
        except ObjectDoesNotExist:
            pass

        report.save()

        report.attr.clear()
        for attr_value in attr_values:
            report.attr.add(attr_value)
        report.save()
    elif report_type == 'finish' or report_type == 'attrs':
        # Update component report
        update_report.description = description
        update_report.resource = resource
        update_report.log = log
        update_report.data = data
        update_report.finish_date = datetime.now()
        update_report.save()

        for attr_value in attr_values:
            update_report.attr.add(attr_value)
        update_report.save()

        if resource:
            ComponentResource.objects.update_or_create(component=update_report.component,
                                                       report=update_report,
                                                       defaults={'resource': resource})
    elif report_type == 'unsafe':
        report = ReportUnsafe()
        report.identifier = identifier
        report.parent = parent
        report.description = description

        report.error_trace = json_start['error trace'].encode()
        report.error_trace_processed = json_start['error trace'].encode()  # TODO

        try:
            # Update.
            old_id = ReportUnsafe.objects.get(identifier=report.identifier).id
            report.id = old_id
        except ObjectDoesNotExist:
            pass

        report.save()

        report.attr.clear()
        for attr_value in attr_values:
            report.attr.add(attr_value)
            ReportAttr.objects.update_or_create(report=report, attr=attr_value)
        report.save()
    elif report_type == 'safe':
        report = ReportSafe()
        report.identifier = identifier
        report.parent = parent
        report.description = description

        report.proof = json_start['proof'].encode()

        try:
            # Update.
            old_id = ReportSafe.objects.get(identifier=report.identifier).id
            report.id = old_id
        except ObjectDoesNotExist:
            pass

        report.save()

        report.attr.clear()
        for attr_value in attr_values:
            report.attr.add(attr_value)
            ReportAttr.objects.update_or_create(report=report, attr=attr_value)
        report.save()
    elif report_type == 'unknown':
        report = ReportUnknown()
        report.identifier = identifier
        report.parent = parent
        report.description = description

        report.problem_description = json_start['problem desc'].encode()

        try:
            # Update.
            old_id = ReportUnknown.objects.get(identifier=report.identifier).id
            report.id = old_id
        except ObjectDoesNotExist:
            pass

        report.save()

        report.attr.clear()
        for attr_value in attr_values:
            report.attr.add(attr_value)
            ReportAttr.objects.update_or_create(report=report, attr=attr_value)
        report.save()

    return HttpResponse('')
