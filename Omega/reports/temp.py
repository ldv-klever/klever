import json
from datetime import datetime
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from reports.models import *
from jobs.job_model import JobStatus


def get_parents(report):
    parents = []
    cur_report = report
    while cur_report:
        parents.append(ReportComponent.objects.get(pk=cur_report.pk))
        cur_report = cur_report.parent
    return parents


def fill_cache_component(report):
    parents = get_parents(report)
    component = report.component
    new_resource = report.resource
    old_resource = None
    try:
        # Cache was not empty.
        old_resource = ComponentResource.objects.get(component=component, report=report).resource
    except ObjectDoesNotExist:
        # Cache was empty.
        pass
    for parent in parents:
        wall_time = new_resource.wall_time
        cpu_time = new_resource.cpu_time
        memory = new_resource.memory
        try:
            cur_resource = ComponentResource.objects.get(component=component, report=parent).resource
            wall_time += cur_resource.wall_time
            cpu_time += cur_resource.cpu_time
            memory += cur_resource.memory
            if old_resource:
                wall_time -= old_resource.wall_time
                cpu_time -= old_resource.cpu_time
                memory -= old_resource.memory
        except ObjectDoesNotExist:
            pass
        resource, stub = Resource.objects.get_or_create(wall_time=wall_time, cpu_time=cpu_time, memory=memory)
        ComponentResource.objects.update_or_create(component=component, report=parent,
                                                   defaults={'resource': resource})


def fill_cache_unsafe(report):
    parents = get_parents(report.parent)
    for parent in parents:
        try:
            ReportComponentLeaf.objects.get(report=parent, leaf_id=report.pk)
        except ObjectDoesNotExist:
            ReportComponentLeaf.objects.create(report=parent, leaf_id=report.pk)
            try:
                verdict = Verdict.objects.get(report=parent)
                verdict.unsafe += 1
                verdict.save()
            except ObjectDoesNotExist:
                Verdict.objects.create(report=parent, unsafe=1)


def fill_cache_safe(report):
    parents = get_parents(report.parent)
    for parent in parents:
        try:
            ReportComponentLeaf.objects.get(report=parent, leaf_id=report.pk)
        except ObjectDoesNotExist:
            ReportComponentLeaf.objects.create(report=parent, leaf_id=report.pk)
            try:
                verdict = Verdict.objects.get(report=parent)
                verdict.safe += 1
                verdict.save()
            except ObjectDoesNotExist:
                Verdict.objects.create(report=parent, safe=1)


def fill_cache_unknown(report):
    parents = get_parents(report.parent)
    component = ReportComponent.objects.get(pk=report.parent.pk).component
    for parent in parents:
        try:
            ReportComponentLeaf.objects.get(report=parent, leaf_id=report.pk)
        except ObjectDoesNotExist:
            ReportComponentLeaf.objects.create(report=parent, leaf_id=report.pk)
            try:
                verdict = Verdict.objects.get(report=parent)
                verdict.unknown += 1
                verdict.save()
            except ObjectDoesNotExist:
                Verdict.objects.create(report=parent, unknown=1)
            try:
                unknown = ComponentUnknown.objects.get(report=parent, component=component)
                unknown.number += 1
                unknown.save()
            except ObjectDoesNotExist:
                ComponentUnknown.objects.create(report=parent, component=component, number=1)


def get_attr(attr, value, attr_values):
    if type(value) is list:
        for elem in value:
            for elem_attr, elem_value in elem.items():
                get_attr(attr+'::'+elem_attr, elem_value, attr_values)
    else:
        attr_name, stub = AttrName.objects.get_or_create(name=attr)
        attr_value, stub = Attr.objects.get_or_create(name=attr_name, value=value)
        attr_values.append(attr_value)


def upload_report(request, is_root=False):

    # Common part.
    json_start = json.loads(request.POST['report'])

    # Current report identifier suffix
    # TODO: check presence of all necessary attributes: 'id' can be absent!
    report_id = json_start['id']

    # Job
    # TODO: check if session['job_id] is int and session has job_id
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
        log = json_start['log'].encode('utf8')
    if 'desc' in json_start:
        description = json_start['desc'].encode('utf8')
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
            if ReportUnknown.objects.filter(parent=update_report).__len__() > 0:
                is_failed = True
                status.status = '4'
            else:
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

        if resource:
            fill_cache_component(report)
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
            fill_cache_component(update_report)
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

        fill_cache_unsafe(report)
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

        fill_cache_safe(report)
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

        fill_cache_unknown(report)

    return HttpResponse('')