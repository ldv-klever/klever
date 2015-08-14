import json
from django.shortcuts import render
from marks.utils import NewMark, AttrTable, MarkData
from reports.models import ReportUnsafe, ReportSafe
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.core.urlresolvers import reverse


def create_mark(request, mark_type, report_id):
    try:
        if mark_type == 'unsafe':
            report = ReportUnsafe.objects.get(pk=int(report_id))
        elif mark_type == 'safe':
            report = ReportSafe.objects.get(pk=int(report_id))
        else:
            return HttpResponseRedirect(reverse('jobs:error', args=[500]))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('jobs:error', args=[504]))

    return render(request, 'marks/CreateMark.html', {
        'report_pk': report.pk,
        'type': mark_type,
        'AttrTable': AttrTable(report),
        'markdata': MarkData(mark_type),
    })


def save_mark(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    savedata = json.loads(request.POST.get('savedata', '{}'))
    if any(x not in savedata for x in
           ['verdict', 'status', 'attrs', 'compare_id', 'report_type']):
        return JsonResponse({'error': 'Unknown error'})
    if 'report_id' in savedata:
        try:
            report = ReportUnsafe.objects.get(pk=int(savedata['report_id']))
        except ObjectDoesNotExist:
            return JsonResponse({'error': 'Report was not found'})
        if 'convert_id' not in savedata:
            return JsonResponse({'error': 'Unknown error'})
        new_mark = NewMark(
            report, request.user, savedata['report_type'], savedata)
        if new_mark.error is not None:
            return JsonResponse({'error': new_mark.error})
        return HttpResponse("OK")
    elif 'mark_id' in savedata:
        try:
            mark = ReportUnsafe.objects.get(pk=int(savedata['mark_id']))
        except ObjectDoesNotExist:
            return JsonResponse({'error': 'Mark was not found'})
