import pytz
import json
import hashlib
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, render
from django.utils.translation import ugettext as _
from django.http import HttpResponse, JsonResponse
from jobs.job_functions import resource_info
from jobs.job_model import Job, JobHistory, JobStatus
from jobs.models import UserRole, ComponentResource
from users.models import View, PreferableView
import jobs.table_prop as tp
import jobs.job_functions as job_f
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import activate
from Omega.vars import JOB_ROLES, JOB_STATUS
from reports.models import ReportRoot, Attr, Report, ReportComponent, Resource, ReportUnsafe
from datetime import datetime


@login_required
def report_root(request, report_id):
    activate(request.user.extended.language)
    report = ReportRoot.objects.get(pk=int(report_id))
    job = report.job
    user_tz = request.user.extended.timezone
    delta = report.finish_date - report.start_date
    resources = ComponentResource.objects.filter(job=job)
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
            'verdict': job_f.verdict_info(job),
            'unknowns': job_f.unknowns_info(job),
            'children_attr': children_attr,
            'children_values': children_values,
        }
    )


def concat_resources_elements(resource_1, resource_2):
    new_list = []
    if resource_1.component.name == resource_2.component.name:
        common_resource = ComponentResource()
        common_resource.component = resource_1.component
        common_resource.resource = resource_2.resource
        common_resource.resource.cpu_time = resource_1.resource.cpu_time + resource_2.resource.cpu_time
        #TODO: wall, memory
        new_list.append(common_resource)
    else:
        new_list.append(resource_1)
        new_list.append(resource_2)
    return new_list


def concat_resources(list_1, list_2):
    new_list = []
    if not list_1:
        return list_2
    if not list_2:
        return list_1
    for resource_1 in list_1:
        for resource_2 in list_2:
            if resource_1.component.name == resource_2.component.name:
                common_resource = ComponentResource()
                common_resource.component = resource_1.component
                common_resource.resource = resource_2.resource
                common_resource.resource.cpu_time = resource_1.resource.cpu_time + resource_2.resource.cpu_time
                #TODO: wall, memory
                new_list.append(common_resource)
            else:
                new_list.append(resource_1)
                new_list.append(resource_2)
    return new_list


def check_children(children):
    if not children:
        return []
    else:
        cur_resources = []
        for child in children:
            resource = ComponentResource()
            resource.component = child.component
            resource.resource = child.resource
            new_children = ReportComponent.objects.filter(parent=child)
            #tmp_resources = concat_resources([resource], check_children(new_children))
            #cur_resources = concat_resources(cur_resources, tmp_resources)
            cur_resources = concat_resources(cur_resources, [resource])
            cur_resources = concat_resources(cur_resources, check_children(new_children))
        return cur_resources


@login_required
def report_component(request, report_id):
    activate(request.user.extended.language)
    report = ReportComponent.objects.get(pk=int(report_id))
    user_tz = request.user.extended.timezone
    delta = None
    if report.finish_date and report.start_date:
        delta = report.finish_date - report.start_date

    children = ReportComponent.objects.filter(parent=report)
    resources = check_children(children)
    current_resource = ComponentResource()
    current_resource.component = report.component
    current_resource.resource = report.resource
    if not resources:
        resources = []
    resources.insert(0, current_resource)

    parents = {}
    parents_attr = []
    cur_report = report.parent

    while cur_report:
        attrs = cur_report.attr.all()
        for attr in attrs:
            parents_attr.append(attr.name)
        cur_report = cur_report.parent
    cur_report = report.parent
    while cur_report:
        attr_values = []
        for attr in parents_attr:
            attr_values.append(cur_report.attr.all().filter(name=attr))
        parents[ReportComponent.objects.get(pk=cur_report.id)] = attr_values
        cur_report = cur_report.parent

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

    #TODO: get verdicts and unknowns from marks

    return render(
        request,
        'reports/report_root.html',
        {
            'report': report,
            'user_tz': user_tz,
            'delta': delta,
            'resources': resources,
            #'verdict': job_f.verdict_info(job),
            #'unknowns': job_f.unknowns_info(job),
            'parents': parents,
            'parents_attr': parents_attr,
            'children_attr': children_attr,
            'children_values': children_values,
        }
    )


