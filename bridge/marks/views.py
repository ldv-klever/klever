import json
from urllib.parse import unquote
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import render
from django.template.loader import get_template
from django.utils.translation import ugettext as _, activate
from django.utils.timezone import pytz
from bridge.vars import USER_ROLES
from bridge.utils import logger, unparallel_group, unparallel
from users.models import View
from marks.utils import NewMark, CreateMarkTar, ReadTarMark, MarkAccess, TagsInfo, DeleteMark
from marks.tables import MarkData, MarkChangesTable, MarkReportsTable, MarksList
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
            report = ReportUnknown.objects.get(pk=int(report_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[504]))
    if not MarkAccess(request.user, report=report).can_create():
        return HttpResponseRedirect(reverse('error', args=[601]))

    return render(request, 'marks/CreateMark.html', {
        'report': report,
        'type': mark_type,
        'markdata': MarkData(mark_type, report=report),
        'can_freeze': (request.user.extended.role == USER_ROLES[2][0]),
        'tags': TagsInfo(mark_type),
        'can_edit': True
    })


@login_required
def edit_mark(request, mark_type, mark_id):
    activate(request.user.extended.language)

    try:
        if mark_type == 'unsafe':
            mark = MarkUnsafe.objects.get(pk=int(mark_id))
        elif mark_type == 'safe':
            mark = MarkSafe.objects.get(pk=int(mark_id))
        else:
            mark = MarkUnknown.objects.get(pk=int(mark_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[604]))

    can_edit = MarkAccess(request.user, mark=mark).can_edit()
    history_set = mark.versions.order_by('-version')
    last_version = history_set[0]
    if can_edit:
        template = 'marks/EditMark.html'
        if mark_type == 'unknown':
            template = 'marks/EditUnknownMark.html'
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

        return render(request, template, {
            'mark': mark,
            'version': last_version,
            'first_version': history_set.order_by('version')[0],
            'type': mark_type,
            'markdata': MarkData(mark_type, mark_version=last_version),
            'reports': MarkReportsTable(request.user, mark),
            'versions': mark_versions,
            'can_freeze': (request.user.extended.role == USER_ROLES[2][0]),
            'tags': TagsInfo(mark_type, mark),
            'can_edit': True
        })
    else:
        return render(request, 'marks/ViewMark.html', {
            'mark': mark,
            'version': last_version,
            'first_version': history_set.order_by('version')[0],
            'type': mark_type,
            'markdata': MarkData(mark_type, mark_version=last_version),
            'reports': MarkReportsTable(request.user, mark),
            'tags': TagsInfo(mark_type, mark)
        })


@unparallel_group(['mark'])
@login_required
def save_mark(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponseRedirect(reverse('error', args=[500]))

    savedata = json.loads(unquote(request.POST.get('savedata', '{}')))
    if 'data_type' not in savedata or \
            savedata['data_type'] not in ['safe', 'unsafe', 'unknown']:
        return HttpResponseRedirect(reverse('error', args=[650]))

    if 'status' not in savedata:
        return HttpResponseRedirect(reverse('error', args=[650]))
    if savedata['data_type'] == 'unknown':
        if any(x not in savedata for x in ['function', 'problem']):
            return HttpResponseRedirect(reverse('error', args=[650]))
    else:
        if any(x not in savedata for x in ['verdict', 'attrs']):
            return HttpResponseRedirect(reverse('error', args=[650]))
    if 'report_id' in savedata:
        try:
            if savedata['data_type'] == 'unsafe':
                inst = ReportUnsafe.objects.get(pk=int(savedata['report_id']))
                if any(x not in savedata for x in ['convert_id', 'compare_id']):
                    return HttpResponseRedirect(reverse('error', args=[650]))
            elif savedata['data_type'] == 'safe':
                inst = ReportSafe.objects.get(pk=int(savedata['report_id']))
            else:
                inst = ReportUnknown.objects.get(pk=int(savedata['report_id']))
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
            elif savedata['data_type'] == 'safe':
                inst = MarkSafe.objects.get(pk=int(savedata['mark_id']))
            else:
                inst = MarkUnknown.objects.get(pk=int(savedata['mark_id']))
        except ObjectDoesNotExist:
            return HttpResponseRedirect(reverse('error', args=[604]))
        if not MarkAccess(request.user, mark=inst).can_edit():
            return HttpResponseRedirect(reverse('error', args=[600]))
    else:
        return HttpResponseRedirect(reverse('error', args=[650]))

    res = NewMark(inst, request.user, savedata['data_type'], savedata)
    if res.error is not None:
        logger.error(res.error, stack_info=True)
        return HttpResponseRedirect(reverse('error', args=[650]))
    return render(request, 'marks/SaveMarkResult.html', {
        'mark_type': res.type,
        'mark': res.mark,
        'MarkTable': MarkChangesTable(request.user, res.mark, res.changes)
    })


@login_required
def get_func_description(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
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
        return JsonResponse({'error': 'Unknown error'})
    return JsonResponse({'description': function.description})


@login_required
def get_mark_version_data(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponse('')

    mark_type = request.POST.get('type', None)
    if mark_type not in ['safe', 'unsafe', 'unknown']:
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
            mark_version = MarkUnknownHistory.objects.get(
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
    if mark_type == 'unknown':
        unknown_data_tmpl = get_template('marks/MarkUnknownData.html')
        data = unknown_data_tmpl.render({
            'markdata': MarkData(mark_type, mark_version=mark_version)
        })
    else:
        data_templ = get_template('marks/MarkAddData.html')
        data = data_templ.render({
            'markdata': MarkData(mark_type, mark_version=mark_version),
            'tags': TagsInfo(mark_type, mark_version),
            'can_edit': True
        })
    return JsonResponse({'data': data})


@login_required
def mark_list(request, marks_type):
    activate(request.user.extended.language)
    titles = {
        'unsafe': _('Unsafe marks'),
        'safe': _('Safe marks'),
        'unknown': _('Unknown marks'),
    }
    verdicts = {
        'unsafe': MARK_UNSAFE,
        'safe': MARK_SAFE,
        'unknown': []
    }
    view_type = {
        'unsafe': '7',
        'safe': '8',
        'unknown': '9'
    }
    table_args = [request.user, marks_type]
    if request.method == 'POST':
        if request.POST.get('view_type', None) == view_type[marks_type]:
            table_args.append(request.POST.get('view', None))
            table_args.append(request.POST.get('view_id', None))

    return render(request, 'marks/MarkList.html', {
        'tabledata': MarksList(*table_args),
        'type': marks_type,
        'title': titles[marks_type],
        'statuses': MARK_STATUS,
        'verdicts': verdicts[marks_type],
        'authors': User.objects.all(),
        'view_type': view_type[marks_type],
        'views': View.objects.filter(type=view_type[marks_type]),
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
            mark = MarkUnknown.objects.get(pk=int(mark_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[604]))

    mark_tar = CreateMarkTar(mark)

    response = HttpResponse(content_type="application/x-tar-gz")
    response["Content-Disposition"] = "attachment; filename=%s" % mark_tar.marktar_name
    mark_tar.memory.seek(0)
    response.write(mark_tar.memory.read())
    return response


@unparallel_group(['mark'])
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


@unparallel_group(['mark'])
@login_required
def delete_mark(request, mark_type, mark_id):
    try:
        if mark_type == 'unsafe':
            mark = MarkUnsafe.objects.get(pk=int(mark_id))
        elif mark_type == 'safe':
            mark = MarkSafe.objects.get(pk=int(mark_id))
        else:
            mark = MarkUnknown.objects.get(pk=int(mark_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[604]))
    if not MarkAccess(request.user, mark=mark).can_delete():
        return HttpResponseRedirect(reverse('error', args=[602]))
    DeleteMark(mark)
    return HttpResponseRedirect(reverse('marks:mark_list', args=[mark_type]))


@unparallel_group(['mark'])
@login_required
def delete_marks(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    if 'type' not in request.POST or 'ids' not in request.POST:
        return JsonResponse({'error': 'Unknown error'})
    try:
        mark_ids = json.loads(request.POST['ids'])
    except Exception as e:
        logger.exception("Json parsing error: %s" % e, stack_info=True)
        return JsonResponse({'error': 'Unknown error'})
    if request.POST['type'] == 'unsafe':
        marks = MarkUnsafe.objects.filter(id__in=mark_ids)
    elif request.POST['type'] == 'safe':
        marks = MarkSafe.objects.filter(id__in=mark_ids)
    elif request.POST['type'] == 'unknown':
        marks = MarkUnknown.objects.filter(id__in=mark_ids)
    else:
        return JsonResponse({'error': 'Unknown error'})

    if not all(MarkAccess(request.user, mark=mark).can_delete() for mark in marks):
        return JsonResponse({'error': _("You can't delete one of the selected mark")})
    for mark in marks:
        DeleteMark(mark)
    return JsonResponse({})


@unparallel
@login_required
def remove_versions(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': 'Unknown error'})
    mark_id = int(request.POST.get('mark_id', 0))
    mark_type = request.POST.get('mark_type', None)
    try:
        if mark_type == 'safe':
            mark = MarkSafe.objects.get(pk=mark_id)
        elif mark_type == 'unsafe':
            mark = MarkUnsafe.objects.get(pk=mark_id)
        elif mark_type == 'unknown':
            mark = MarkUnknown.objects.get(pk=mark_id)
        else:
            return JsonResponse({'message': 'Unknown error'})
        mark_history = mark.versions.filter(~Q(version__in=[mark.version, 1]))
    except ObjectDoesNotExist:
        return JsonResponse({
            'status': 1, 'message': _('The mark was not found')
        })
    if not MarkAccess(request.user, mark).can_edit():
        return JsonResponse({
            'status': 1,
            'message': _("You don't have an access to edit this mark")
        })

    versions = json.loads(request.POST.get('versions', '[]'))
    checked_versions = mark_history.filter(version__in=versions)
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
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'message': _('Unknown error')})
    mark_id = int(request.POST.get('mark_id', 0))
    mark_type = request.POST.get('mark_type', None)
    try:
        if mark_type == 'safe':
            mark = MarkSafe.objects.get(pk=mark_id)
        elif mark_type == 'unsafe':
            mark = MarkUnsafe.objects.get(pk=mark_id)
        elif mark_type == 'unknown':
            mark = MarkUnknown.objects.get(pk=mark_id)
        else:
            return JsonResponse({'message': _('Unknown error')})
        mark_history = mark.versions.filter(
            ~Q(version__in=[mark.version, 1])).order_by('-version')
    except ObjectDoesNotExist:
        return JsonResponse({'message': _('The mark was not found')})
    mark_versions = []
    for m in mark_history:
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
    return render(request, 'marks/markVersions.html', {'versions': mark_versions})
