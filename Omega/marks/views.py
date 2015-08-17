import json
import pytz
from django.template.loader import get_template
from django.shortcuts import render
from marks.utils import NewMark, MarkAttrTable, MarkData, \
    MarkChangesTable, MarkListTable, MarkReportsTable, AllMarksList
from reports.models import ReportUnsafe, ReportSafe
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.core.urlresolvers import reverse
from marks.models import MarkUnsafeCompare, MarkUnsafeConvert, MarkUnsafe,\
    MarkSafe, MarkUnsafeHistory, MarkSafeHistory
from django.contrib.auth.decorators import login_required
from django.utils.translation import ugettext as _


@login_required
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
        'AttrTable': MarkAttrTable(report),
        'markdata': MarkData(mark_type),
    })


@login_required
def edit_mark(request, mark_type, mark_id):
    try:
        if mark_type == 'unsafe':
            mark = MarkUnsafe.objects.get(pk=int(mark_id))
            history_set = mark.markunsafehistory_set.all().order_by('-version')
        elif mark_type == 'safe':
            mark = MarkSafe.objects.get(pk=int(mark_id))
            history_set = mark.marksafehistory_set.all().order_by('-version')
        else:
            return HttpResponseRedirect(reverse('jobs:error', args=[500]))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('jobs:error', args=[504]))

    mark_versions = []
    for m in history_set:
        if m.version == mark.version:
            title = _("Current version")
        else:
            change_time = m.change_date.astimezone(
                pytz.timezone(request.user.extended.timezone)
            )
            title = change_time.strftime("%d.%m.%Y %H:%M:%S")
            title += " (%s %s)" % (
                m.author.extended.last_name,
                m.author.extended.first_name,
            )
            title += ': ' + m.comment
        mark_versions.append({
            'version': m.version,
            'title': title
        })
    last_version = history_set[0]

    return render(request, 'marks/EditMark.html', {
        'mark': mark,
        'version': last_version,
        'first_version': history_set.order_by('version')[0],
        'type': mark_type,
        'AttrTable': MarkAttrTable(mark_version=last_version),
        'markdata': MarkData(mark_type, last_version),
        'reports': MarkReportsTable(mark),
        'versions': mark_versions,
    })


@login_required
def save_mark(request):
    if request.method != 'POST':
        return HttpResponseRedirect(reverse('jobs:error', args=[500]))
    savedata = json.loads(request.POST.get('savedata', '{}'))
    print(savedata)
    if any(x not in savedata for x in
           ['verdict', 'status', 'attrs', 'data_type']):
        print(1)
        return render(request, 'error.html', {'message': _('Unknown error')})
    if 'report_id' in savedata:
        try:
            if savedata['data_type'] == 'unsafe':
                inst = ReportUnsafe.objects.get(pk=int(savedata['report_id']))
                if any(x not in savedata for x in ['convert_id', 'compare_id']):
                    return render(request, 'error.html',
                                  {'message': _('Unknown error')})
            elif savedata['data_type'] == 'safe':
                inst = ReportSafe.objects.get(pk=int(savedata['report_id']))
            else:
                return render(request, 'error.html',
                              {'message': _('Unknown error')})
        except ObjectDoesNotExist:
            return HttpResponseRedirect(reverse('jobs:error', args=[504]))
    elif 'mark_id' in savedata:
        try:
            if savedata['data_type'] == 'unsafe':
                if 'compare_id' not in savedata:
                    return render(request, 'error.html',
                                  {'message': _('Unknown error')})
                inst = MarkUnsafe.objects.get(pk=int(savedata['mark_id']))
            elif savedata['data_type'] == 'safe':
                inst = MarkSafe.objects.get(pk=int(savedata['mark_id']))
            else:
                return render(request, 'error.html',
                              {'message': _('Unknown error')})
        except ObjectDoesNotExist:
            return HttpResponseRedirect(reverse('jobs:error', args=[604]))
    else:
        return render(request, 'error.html', {'message': _('Unknown error')})

    mark = NewMark(inst, request.user, savedata['data_type'], savedata)
    if mark.error is not None:
        return render(request, 'error.html', {'message': mark.error})
    return render(request, 'marks/SaveMarkResult.html', {
        'mark_type': mark.type,
        'mark': mark.mark,
        'MarkTable': MarkChangesTable(mark.mark, mark.changes)
    })


@login_required
def get_func_description(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    func_id = int(request.POST.get('func_id', '0'))
    func_type = request.POST.get('func_type', 'compare')
    if func_type == 'compare':
        try:
            function = MarkUnsafeCompare.objects.get(pk=func_id)
        except ObjectDoesNotExist:
            return JsonResponse({'error': 'Function was not found'})
    elif func_type == 'convert':
        try:
            function = MarkUnsafeConvert.objects.get(pk=func_id)
        except ObjectDoesNotExist:
            return JsonResponse({'error': 'Function was not found'})
    else:
        return JsonResponse({'error': 'Unknown error'})
    return JsonResponse({'description': function.description})


@login_required
def get_mark_version_data(request):
    if request.method != 'POST':
        return HttpResponse('')

    mark_type = request.POST.get('type', None)
    if mark_type is None:
        return JsonResponse({'error': _('Unknown error')})
    try:
        if mark_type == 'unsafe':
            mark_version = MarkUnsafeHistory.objects.get(
                version=int(request.POST.get('version', '0')),
                mark_id=int(request.POST.get('mark_id', '0'))
            )
        elif mark_type == 'safe':
            mark_version = MarkSafeHistory.objects.get(
                version=int(request.POST.get('version', '0')),
                mark_id=int(request.POST.get('mark_id', '0'))
            )
        else:
            return JsonResponse({
                'error': _('Unknown error')
            })
    except ObjectDoesNotExist:
        return JsonResponse({
            'error': _('Version was not found, please reload page')
        })
    table_templ = get_template('marks/MarkAttrTable.html')
    table = table_templ.render({
        'data': MarkAttrTable(mark_version=mark_version)
    })
    data_templ = get_template('marks/MarkAddData.html')
    data = data_templ.render({'markdata': MarkData(mark_type, mark_version)})
    return JsonResponse({'table': table, 'adddata': data})


@login_required
def mark_list(request, marks_type):
    return render(request, 'marks/MarkList.html', {
        'tabledata': MarkListTable(marks_type)
    })


@login_required
def marks_all(request):
    return render(request, 'marks/MarksAll.html', {
        'safes': AllMarksList('safe'),
        'unsafes': AllMarksList('unsafe')
    })
