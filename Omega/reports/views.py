from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.translation import activate
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