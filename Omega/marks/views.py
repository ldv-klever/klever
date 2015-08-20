import json
import pytz
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import render
from django.template.loader import get_template
from django.utils.translation import ugettext as _, activate
from Omega.vars import USER_ROLES
from marks.utils import NewMark, CreateMarkTar, ReadTarMark, UpdateVerdict,\
    MarkAccess
from marks.tables import MarkAttrTable, MarkData, MarkChangesTable,\
    MarkReportsTable2, MarksList
from marks.models import *


@login_required
def create_mark(request, mark_type, report_id):
    activate(request.user.extended.language)

    try:
        if mark_type == 'unsafe':
            report = ReportUnsafe.objects.get(pk=int(report_id))
        elif mark_type == 'safe':
            report = ReportSafe.objects.get(pk=int(report_id))
        else:
            return HttpResponseRedirect(reverse('error', args=[500]))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[504]))
    if not MarkAccess(request.user, report=report).can_create():
        return HttpResponseRedirect(reverse('error', args=[601]))

    return render(request, 'marks/CreateMark.html', {
        'report_pk': report.pk,
        'type': mark_type,
        'AttrTable': MarkAttrTable(report),
        'markdata': MarkData(mark_type),
        'can_freeze': (request.user.extended.role == USER_ROLES[2][0])
    })


@login_required
def edit_mark(request, mark_type, mark_id):
    activate(request.user.extended.language)

    try:
        if mark_type == 'unsafe':
            mark = MarkUnsafe.objects.get(pk=int(mark_id))
            history_set = mark.markunsafehistory_set.all().order_by('-version')
        elif mark_type == 'safe':
            mark = MarkSafe.objects.get(pk=int(mark_id))
            history_set = mark.marksafehistory_set.all().order_by('-version')
        else:
            return HttpResponseRedirect(reverse('error', args=[500]))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[604]))

    if not MarkAccess(request.user, mark=mark).can_edit():
        return HttpResponseRedirect(reverse('error', args=[600]))

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
        'reports': MarkReportsTable2(request.user, mark),
        'versions': mark_versions,
        'can_freeze': (request.user.extended.role == USER_ROLES[2][0])
    })


@login_required
def save_mark(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponseRedirect(reverse('error', args=[500]))

    savedata = json.loads(request.POST.get('savedata', '{}'))
    if 'data_type' not in savedata or \
            savedata['data_type'] not in ['safe', 'unsafe']:
        return HttpResponseRedirect(reverse('error', args=[650]))

    if any(x not in savedata for x in ['verdict', 'status', 'attrs']):
        return HttpResponseRedirect(reverse('error', args=[650]))
    if 'report_id' in savedata:
        try:
            if savedata['data_type'] == 'unsafe':
                inst = ReportUnsafe.objects.get(pk=int(savedata['report_id']))
                if any(x not in savedata for x in ['convert_id', 'compare_id']):
                    return HttpResponseRedirect(reverse('error', args=[650]))
            else:
                inst = ReportSafe.objects.get(pk=int(savedata['report_id']))
        except ObjectDoesNotExist:
            return HttpResponseRedirect(reverse('error', args=[504]))
        if not MarkAccess(request.user, report=inst).can_create():
            return HttpResponseRedirect(reverse('error', args=[601]))
    elif 'mark_id' in savedata:
        try:
            if savedata['data_type'] == 'unsafe':
                if 'compare_id' not in savedata:
                    return HttpResponseRedirect(reverse('error', args=[650]))
                inst = MarkUnsafe.objects.get(pk=int(savedata['mark_id']))
            else:
                inst = MarkSafe.objects.get(pk=int(savedata['mark_id']))
        except ObjectDoesNotExist:
            return HttpResponseRedirect(reverse('error', args=[604]))
        if not MarkAccess(request.user, mark=inst).can_edit():
            return HttpResponseRedirect(reverse('error', args=[600]))
    else:
        return HttpResponseRedirect(reverse('error', args=[650]))

    mark = NewMark(inst, request.user, savedata['data_type'], savedata)
    if mark.error is not None:
        print(mark.error)
        return HttpResponseRedirect(reverse('error', args=[650]))
    return render(request, 'marks/SaveMarkResult.html', {
        'mark_type': mark.type,
        'mark': mark.mark,
        'MarkTable': MarkChangesTable(request.user, mark.mark, mark.changes)
    })


@login_required
def get_func_description(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': _('Unknown error')})
    func_id = int(request.POST.get('func_id', '0'))
    func_type = request.POST.get('func_type', 'compare')
    if func_type == 'compare':
        try:
            function = MarkUnsafeCompare.objects.get(pk=func_id)
        except ObjectDoesNotExist:
            return JsonResponse({
                'error': _('The error traces comparison function was not found')
            })
    elif func_type == 'convert':
        try:
            function = MarkUnsafeConvert.objects.get(pk=func_id)
        except ObjectDoesNotExist:
            return JsonResponse({
                'error': _('The error traces conversion function was not found')
            })
    else:
        return JsonResponse({'error': _('Unknown error')})
    return JsonResponse({'description': function.description})


@login_required
def get_mark_version_data(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponse('')

    mark_type = request.POST.get('type', None)
    if mark_type not in ['safe', 'unsafe']:
        return JsonResponse({'error': _('Unknown error')})
    try:
        if mark_type == 'unsafe':
            mark_version = MarkUnsafeHistory.objects.get(
                version=int(request.POST.get('version', '0')),
                mark_id=int(request.POST.get('mark_id', '0'))
            )
        else:
            mark_version = MarkSafeHistory.objects.get(
                version=int(request.POST.get('version', '0')),
                mark_id=int(request.POST.get('mark_id', '0'))
            )
    except ObjectDoesNotExist:
        return JsonResponse({
            'error': _('Your version is expired, please reload the page')
        })
    if not MarkAccess(request.user, mark=mark_version.mark).can_edit():
        return JsonResponse({
            'error': _("You don't have an access to edit this mark")
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
    activate(request.user.extended.language)
    titles = {
        'unsafe': _('Unsafe marks'),
        'safe': _('Safe marks'),
        'unknown': _('Unknown marks'),
    }
    return render(request, 'marks/MarkList.html', {
        'tabledata': MarksList(request.user, marks_type),
        'title': titles[marks_type],
    })


@login_required
def download_mark(request, mark_type, mark_id):

    if request.method == 'POST':
        return HttpResponse('')
    try:
        if mark_type == 'safe':
            mark = MarkSafe.objects.get(pk=int(mark_id))
        elif mark_type == 'unsafe':
            mark = MarkUnsafe.objects.get(pk=int(mark_id))
        else:
            return HttpResponseRedirect(reverse('error', args=[500]))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[604]))

    if not MarkAccess(request.user, mark=mark).can_edit():
        return HttpResponseRedirect(reverse('error', args=[605]))

    mark_tar = CreateMarkTar(mark, mark_type)

    response = HttpResponse(content_type="application/x-tar-gz")
    response["Content-Disposition"] = "attachment; filename=%s" % \
                                      mark_tar.marktar_name
    mark_tar.memory.seek(0)
    response.write(mark_tar.memory.read())
    return response


@login_required
def upload_marks(request):
    activate(request.user.extended.language)

    if not MarkAccess(request.user).can_create():
        return JsonResponse({
            'status': False,
            'message': _("You don't have access to create new marks")
        })

    failed_marks = []
    mark_id = None
    mark_type = None
    num_of_new_marks = 0
    for f in request.FILES.getlist('file'):
        tardata = ReadTarMark(request.user, f)
        if tardata.error is not None:
            failed_marks.append([tardata.error + '', f.name])
        else:
            num_of_new_marks += 1
            mark_id = tardata.mark.pk
            mark_type = tardata.type
    if len(failed_marks) > 0:
        return JsonResponse({'status': False, 'messages': failed_marks})
    if num_of_new_marks == 1:
        return JsonResponse({
            'status': True, 'mark_id': str(mark_id), 'mark_type': mark_type
        })
    return JsonResponse({'status': True})


@login_required
def delete_mark(request, mark_type, mark_id):
    try:
        if mark_type == 'unsafe':
            mark = MarkUnsafe.objects.get(pk=int(mark_id))
        elif mark_type == 'safe':
            mark = MarkSafe.objects.get(pk=int(mark_id))
        else:
            return HttpResponseRedirect(reverse('error', args=[500]))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[604]))
    if not MarkAccess(request.user, mark=mark).can_delete():
        return HttpResponseRedirect(reverse('error', args=[602]))
    mark.delete()
    if mark_type == 'safe':
        for report in ReportSafe.objects.all():
            UpdateVerdict(report, {}, '=')
    else:
        for report in ReportUnsafe.objects.all():
            UpdateVerdict(report, {}, '=')
    return HttpResponseRedirect(reverse('marks:mark_list', args=[mark_type]))


@login_required
def remove_versions(request):
    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _('Unknown error')})
    mark_id = int(request.POST.get('mark_id', 0))
    mark_type = request.POST.get('mark_type', None)
    try:
        if mark_type == 'safe':
            mark = MarkSafe.objects.get(pk=mark_id)
            mark_history_set = mark.marksafehistory_set.filter(
                ~Q(version__in=[mark.version, 1])).order_by('-version')
        elif mark_type == 'unsafe':
            mark = MarkUnsafe.objects.get(pk=mark_id)
            mark_history_set = mark.markunsafehistory_set.filter(
                ~Q(version__in=[mark.version, 1])).order_by('-version')
        else:
            return JsonResponse({'message': _('Unknown error')})
    except ObjectDoesNotExist:
        return JsonResponse({
            'status': 1, 'message': _('The mark was not found')
        })
    if not MarkAccess(request.user, mark).can_edit():
        return JsonResponse({
            'status': 1,
            'message': _("You don't have access to edit this mark")
        })

    versions = json.loads(request.POST.get('versions', '[]'))
    checked_versions = mark_history_set.filter(version__in=versions)
    deleted_versions = len(checked_versions)
    checked_versions.delete()

    if deleted_versions > 0:
        return JsonResponse({
            'status': 0,
            'message': _('Selected versions were successfully deleted')
        })
    return JsonResponse({'status': 1, 'message': _('Nothing to delete')})


@login_required
def get_mark_versions(request):
    if request.method != 'POST':
        return JsonResponse({'message': _('Unknown error')})
    mark_id = int(request.POST.get('mark_id', 0))
    mark_type = request.POST.get('mark_type', None)
    try:
        if mark_type == 'safe':
            mark = MarkSafe.objects.get(pk=mark_id)
            mark_history_set = mark.marksafehistory_set.filter(
                ~Q(version__in=[mark.version, 1])).order_by('-version')
        elif mark_type == 'unsafe':
            mark = MarkUnsafe.objects.get(pk=mark_id)
            mark_history_set = mark.markunsafehistory_set.filter(
                ~Q(version__in=[mark.version, 1])).order_by('-version')
        else:
            return JsonResponse({'message': _('Unknown error')})
    except ObjectDoesNotExist:
        return JsonResponse({'message': _('The mark was not found')})
    mark_versions = []
    for m in  mark_history_set:
        mark_time = m.change_date.astimezone(
            pytz.timezone(request.user.extended.timezone)
        )
        title = mark_time.strftime("%d.%m.%Y %H:%M:%S")
        title += " (%s %s)" % (m.author.extended.last_name,
                               m.author.extended.first_name)
        title += ': ' + m.comment
        mark_versions.append({
            'version': m.version,
            'title': title
        })
    return render(request, 'marks/markVersions.html',
                  {'versions': mark_versions})
