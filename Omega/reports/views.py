import pytz
import json
import hashlib
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, render
from django.utils.translation import ugettext as _
from django.http import HttpResponse, JsonResponse
from jobs.job_model import Job, JobHistory, JobStatus
from jobs.models import UserRole, ComponentResource
from users.models import View, PreferableView
import jobs.table_prop as tp
import jobs.job_functions as job_f
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import activate
from Omega.vars import JOB_ROLES, JOB_STATUS
from reports.models import ReportRoot, Attr, Report, ReportComponent
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
            'children': children
        }
        )

@login_required
def report_component(request, report_id):
    activate(request.user.extended.language)
    report = ReportComponent.objects.get(pk=int(report_id))
    #job = report.job
    user_tz = request.user.extended.timezone
    delta = None
    if report.finish_date and report.start_date:
        delta = report.finish_date - report.start_date
    #resources = ComponentResource.objects.filter(job=job)
    children = ReportComponent.objects.filter(parent=report)
    parents = []
    cur_report = report.parent
    while cur_report:
        parents.insert(0, cur_report)
        cur_report = cur_report.parent

    return render(
        request,
        'reports/report_root.html',
        {
            'report': report,
            'user_tz': user_tz,
            'delta': delta,
            #'resources': resources,
            #'verdict': job_f.verdict_info(job),
            #'unknowns': job_f.unknowns_info(job),
            'children': children,
            'parents': parents,
        }
        )