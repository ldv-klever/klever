import pytz
import json
import hashlib
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, render
from django.utils.translation import ugettext as _
from django.http import HttpResponse, JsonResponse
from jobs.job_model import Job, JobHistory
from jobs.models import UserRole
from users.models import View, PreferableView
import jobs.table_prop as tp
import jobs.job_functions as job_f
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import activate
from Omega.vars import JOB_ROLES, JOB_STATUS
from reports.models import ReportRoot


@login_required
def report_root(request, report_id):
    activate(request.user.extended.language)
    report = ReportRoot.objects.get(pk=int(report_id))
    return render(
        request,
        'reports/report_root.html',
        {
            'report': report
        }
        )