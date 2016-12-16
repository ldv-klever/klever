#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os
import json
import mimetypes
from io import BytesIO
from urllib.parse import unquote
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import render
from django.template.defaulttags import register
from django.template.loader import get_template
from django.utils.translation import ugettext as _, activate
from django.utils.timezone import pytz
from bridge.vars import USER_ROLES
from bridge.tableHead import Header
from bridge.utils import logger, unparallel_group, unparallel, extract_tar_temp, ArchiveFileContent
from users.models import View
from marks.tags import GetTagsData, GetParents, SaveTag, can_edit_tags, TagsInfo, CreateTagsFromFile
from marks.utils import NewMark, MarkAccess, DeleteMark
from marks.Download import ReadTarMark, CreateMarkTar, AllMarksTar, UploadAllMarks
from marks.tables import MarkData, MarkChangesTable, MarkReportsTable, MarksList, MARK_TITLES
from marks.models import *


@register.filter
def value_type(value):
    return str(type(value))


@login_required
def create_mark(request, mark_type, report_id):
    activate(request.user.extended.language)

    problem_description = None
    try:
        if mark_type == 'unsafe':
            report = ReportUnsafe.objects.get(pk=int(report_id))
        elif mark_type == 'safe':
            report = ReportSafe.objects.get(pk=int(report_id))
        else:
            report = ReportUnknown.objects.get(pk=int(report_id))
            afc = ArchiveFileContent(report, file_name=report.problem_description)
            if afc.error is not None:
                logger.error(afc.error)
                return HttpResponseRedirect(reverse('error', args=[500]))
            problem_description = afc.content
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[504]))
    if not MarkAccess(request.user, report=report).can_create():
        return HttpResponseRedirect(reverse('error', args=[601]))
    tags = None
    if mark_type != 'unknown':
        tags = TagsInfo(mark_type, [])
        if tags.error is not None:
            logger.error(tags.error, stack_info=True)
            return HttpResponseRedirect(reverse('error', args=[500]))

    return render(request, 'marks/CreateMark.html', {
        'report': report,
        'type': mark_type,
        'markdata': MarkData(mark_type, report=report),
        'can_freeze': (request.user.extended.role == USER_ROLES[2][0]),
        'tags': tags,
        'problem_description': problem_description
    })


@login_required
def view_mark(request, mark_type, mark_id):
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

    if mark.version == 0:
        return HttpResponseRedirect(reverse('error', args=[605]))

    history_set = mark.versions.order_by('-version')
    last_version = history_set.first()

    error_trace = None
    if mark_type == 'unsafe':
        with last_version.error_trace.file.file as fp:
            error_trace = fp.read().decode('utf8')

    tags = None
    if mark_type != 'unknown':
        tags = TagsInfo(mark_type, list(tag.tag.pk for tag in last_version.tags.all()))
        if tags.error is not None:
            logger.error(tags.error, stack_info=True)
            return HttpResponseRedirect(reverse('error', args=[500]))
    return render(request, 'marks/ViewMark.html', {
        'mark': mark,
        'version': last_version,
        'first_version': history_set.last(),
        'type': mark_type,
        'markdata': MarkData(mark_type, mark_version=last_version),
        'reports': MarkReportsTable(request.user, mark),
        'tags': tags,
        'can_edit': MarkAccess(request.user, mark=mark).can_edit(),
        'view_tags': True,
        'error_trace': error_trace
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
    if mark.version == 0:
        return HttpResponseRedirect(reverse('error', args=[605]))

    if not MarkAccess(request.user, mark=mark).can_edit():
        return HttpResponseRedirect(reverse('error', args=[603]))

    history_set = mark.versions.order_by('-version')
    last_version = history_set.first()

    error_trace = None
    if mark_type == 'unsafe':
        with last_version.error_trace.file.file as fp:
            error_trace = fp.read().decode('utf8')

    tags = None
    if mark_type != 'unknown':
        tags = TagsInfo(mark_type, list(tag.tag.pk for tag in last_version.tags.all()))
        if tags.error is not None:
            logger.error(tags.error, stack_info=True)
            return HttpResponseRedirect(reverse('error', args=[500]))

    template = 'marks/EditMark.html'
    if mark_type == 'unknown':
        template = 'marks/EditUnknownMark.html'
    mark_versions = []
    for m in history_set:
        if m.version == mark.version:
            title = _("Current version")
        else:
            change_time = m.change_date.astimezone(pytz.timezone(request.user.extended.timezone))
            title = change_time.strftime("%d.%m.%Y %H:%M:%S")
            if m.author is not None:
                title += " (%s %s)" % (m.author.last_name, m.author.first_name)
            title += ': ' + m.comment
        mark_versions.append({'version': m.version, 'title': title})

    return render(request, template, {
        'mark': mark,
        'version': last_version,
        'first_version': history_set.last(),
        'type': mark_type,
        'markdata': MarkData(mark_type, mark_version=last_version),
        'reports': MarkReportsTable(request.user, mark),
        'versions': mark_versions,
        'can_freeze': (request.user.extended.role == USER_ROLES[2][0]),
        'tags': tags,
        'error_trace': error_trace
    })


@unparallel_group(['mark'])
@login_required
def save_mark(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    try:
        savedata = json.loads(unquote(request.POST.get('savedata', '{}')))
    except Exception as e:
        logger.exception(e, stack_info=True)
        return JsonResponse({'error': 'Unknown error'})
    if savedata.get('data_type') not in ['safe', 'unsafe', 'unknown']:
        return JsonResponse({'error': 'Unknown error'})

    if 'report_id' in savedata:
        try:
            if savedata['data_type'] == 'unsafe':
                inst = ReportUnsafe.objects.get(pk=int(savedata['report_id']))
            elif savedata['data_type'] == 'safe':
                inst = ReportSafe.objects.get(pk=int(savedata['report_id']))
            else:
                inst = ReportUnknown.objects.get(pk=int(savedata['report_id']))
        except ObjectDoesNotExist:
            return JsonResponse({'error': str(_('The report was not found'))})
        if not MarkAccess(request.user, report=inst).can_create():
            return JsonResponse({'error': str(_("You don't have an access to create new marks"))})
    elif 'mark_id' in savedata:
        try:
            if savedata['data_type'] == 'unsafe':
                inst = MarkUnsafe.objects.get(pk=int(savedata['mark_id']))
            elif savedata['data_type'] == 'safe':
                inst = MarkSafe.objects.get(pk=int(savedata['mark_id']))
            else:
                inst = MarkUnknown.objects.get(pk=int(savedata['mark_id']))
        except ObjectDoesNotExist:
            return JsonResponse({'error': str(_('The mark was not found'))})
        if not MarkAccess(request.user, mark=inst).can_edit():
            return JsonResponse({'error': str(_("You don't have an access to this mark"))})
    else:
        return JsonResponse({'error': 'Unknown error'})

    try:
        res = NewMark(inst, request.user, savedata['data_type'], savedata)
    except Exception as e:
        logger.exception("Error while saving/creating mark: %s" % e, stack_info=True)
        return JsonResponse({'error': 'Unknown error'})
    if res.error is not None:
        return JsonResponse({'error': str(res.error)})

    try:
        return JsonResponse({'cache_id': MarkChangesTable(request.user, res.mark, res.changes).cache_id})
    except Exception as e:
        logger.exception('Error while saving changes of mark associations: %s' % e, stack_info=True)
        return JsonResponse({'error': 'Unknown error'})


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
    if int(request.POST.get('version', '0')) == 0:
        return JsonResponse({'error': _('The mark is being deleted')})

    mark_type = request.POST.get('type', None)
    if mark_type not in ['safe', 'unsafe', 'unknown']:
        return JsonResponse({'error': _('Unknown error')})
    error_trace = None
    try:
        if mark_type == 'unsafe':
            mark_version = MarkUnsafeHistory.objects.get(
                version=int(request.POST.get('version', '0')),
                mark_id=int(request.POST.get('mark_id', '0'))
            )
            with mark_version.error_trace.file as fp:
                error_trace = fp.read().decode('utf8')
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
        tags = TagsInfo(mark_type, list(tag.tag.pk for tag in mark_version.tags.all()))
        if tags.error is not None:
            return JsonResponse({'error': str(tags.error)})
        data = data_templ.render({
            'markdata': MarkData(mark_type, mark_version=mark_version),
            'tags': tags,
            'can_edit': True,
            'error_trace': error_trace
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
        'mark_types': MARK_TYPE,
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
    if mark.version == 0:
        return HttpResponseRedirect(reverse('error', args=[605]))

    mark_tar = CreateMarkTar(mark)

    response = HttpResponse(content_type="application/x-tar-gz")
    response["Content-Disposition"] = "attachment; filename=%s" % mark_tar.name
    response.write(mark_tar.tempfile.read())
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
        return JsonResponse({'error': 'Unknown error'})
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
            return JsonResponse({'error': 'Unknown error'})
        if mark.version == 0:
            return JsonResponse({'error': 'The mark is being deleted'})
        mark_history = mark.versions.filter(~Q(version__in=[mark.version, 1]))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('The mark was not found')})
    if not MarkAccess(request.user, mark).can_edit():
        return JsonResponse({'error': _("You don't have an access to edit this mark")})

    versions = json.loads(request.POST.get('versions', '[]'))
    checked_versions = mark_history.filter(version__in=versions)
    deleted_versions = len(checked_versions)
    checked_versions.delete()

    if deleted_versions > 0:
        return JsonResponse({'message': _('Selected versions were successfully deleted')})
    return JsonResponse({'error': _('Nothing to delete')})


@login_required
def get_mark_versions(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
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
            return JsonResponse({'error': 'Unknown error'})
        if mark.version == 0:
            return JsonResponse({'error': 'The mark is being deleted'})
        mark_history = mark.versions.filter(
            ~Q(version__in=[mark.version, 1])).order_by('-version')
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('The mark was not found')})
    mark_versions = []
    for m in mark_history:
        mark_time = m.change_date.astimezone(pytz.timezone(request.user.extended.timezone))
        title = mark_time.strftime("%d.%m.%Y %H:%M:%S")
        if m.author is not None:
            title += " (%s %s)" % (m.author.last_name, m.author.first_name)
        title += ': ' + m.comment
        mark_versions.append({'version': m.version, 'title': title})
    return render(request, 'marks/markVersions.html', {'versions': mark_versions})


@login_required
def association_changes(request, association_id):
    activate(request.user.extended.language)

    try:
        ass_ch = MarkAssociationsChanges.objects.get(identifier=association_id)
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[500]))
    try:
        data = json.loads(ass_ch.table_data)
    except ValueError:
        return HttpResponseRedirect(reverse('error', args=[500]))
    return render(request, 'marks/SaveMarkResult.html', {
        'MarkTable': data,
        'header': Header(data.get('columns', []), MARK_TITLES).struct
    })


@login_required
def show_tags(request, tags_type):
    activate(request.user.extended.language)

    if tags_type == 'unsafe':
        page_title = "Unsafe tags"
    else:
        page_title = "Safe tags"
    tags_data = GetTagsData(tags_type)
    if tags_data.error is not None:
        logger.error("Can't get tags data: %s" % tags_data.error)
        return HttpResponseRedirect(reverse('error', args=[500]))
    return render(request, 'marks/TagsTree.html', {
        'title': page_title,
        'tags': tags_data.table.data,
        'tags_type': tags_type,
        'can_edit': can_edit_tags(request.user)
    })


@login_required
def get_tag_parents(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    if 'tag_type' not in request.POST or request.POST['tag_type'] not in ['safe', 'unsafe']:
        return JsonResponse({'error': 'Unknown error'})
    if 'tag_id' not in request.POST:
        if request.POST['tag_type'] == 'unsafe':
            return JsonResponse({'parents': json.dumps(list(tag.pk for tag in UnsafeTag.objects.order_by('tag')),
                                                       ensure_ascii=False, sort_keys=True, indent=4)})
        else:
            return JsonResponse({'parents': json.dumps(list(tag.pk for tag in SafeTag.objects.order_by('tag')),
                                                       ensure_ascii=False, sort_keys=True, indent=4)})
    res = GetParents(request.POST['tag_id'], request.POST['tag_type'])
    if res.error is not None:
        return JsonResponse({'error': str(res.error)})
    return JsonResponse({
        'parents': json.dumps(res.parents_ids, ensure_ascii=False, sort_keys=True, indent=4),
        'current': res.tag.parent_id if res.tag.parent_id is not None else 0
    })


@login_required
def save_tag(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    if not can_edit_tags(request.user):
        return JsonResponse({'error': _("You don't have an access to edit tags")})
    res = SaveTag(request.POST)
    if res.error is not None:
        return JsonResponse({'error': str(res.error)})
    return JsonResponse({})


@login_required
def remove_tag(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    if not can_edit_tags(request.user):
        return JsonResponse({'error': _("You don't have an access to remove tags") + ''})
    if 'tag_type' not in request.POST or request.POST['tag_type'] not in ['safe', 'unsafe']:
        return JsonResponse({'error': 'Unknown error'})
    if request.POST['tag_type'] == 'safe':
        try:
            SafeTag.objects.get(pk=request.POST.get('tag_id', 0)).delete()
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('The tag was not found')})
    else:
        try:
            UnsafeTag.objects.get(pk=request.POST.get('tag_id', 0)).delete()
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('The tag was not found')})
    return JsonResponse({})


@login_required
def get_tags_data(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    if 'tag_type' not in request.POST or request.POST['tag_type'] not in ['safe', 'unsafe']:
        return JsonResponse({'error': 'Unknown error'})
    if 'selected_tags' not in request.POST:
        return JsonResponse({'error': 'Unknown error'})
    deleted_tag = None
    if 'deleted' in request.POST and request.POST['deleted'] is not None:
        try:
            deleted_tag = int(request.POST['deleted'])
        except Exception as e:
            logger.error("Deleted tag has wrong format: %s" % e)
            return JsonResponse({'error': 'Unknown error'})
    try:
        selected_tags = json.loads(request.POST['selected_tags'])
    except Exception as e:
        logger.error("Can't parse selected tags: %s" % e, stack_info=True)
        return JsonResponse({'error': 'Unknown error'})
    res = TagsInfo(request.POST['tag_type'], selected_tags, deleted_tag)
    if res.error is not None:
        return JsonResponse({'error': str(res.error)})
    return JsonResponse({
        'available': json.dumps(res.available, ensure_ascii=False, sort_keys=True, indent=4),
        'selected': json.dumps(res.selected, ensure_ascii=False, sort_keys=True, indent=4),
        'tree': get_template('marks/MarkTagsTree.html').render({
            'tags': res.table, 'tags_type': res.tag_type, 'can_edit': True
        })
    })


@login_required
def download_tags(request, tags_type):
    tags_data = []
    if tags_type == 'safe':
        tags_table = SafeTag
    else:
        tags_table = UnsafeTag
    for tag in tags_table.objects.all():
        tag_data = {'name': tag.tag, 'description': tag.description}
        if tag.parent is not None:
            tag_data['parent'] = tag.parent.tag
        tags_data.append(tag_data)
    fp = BytesIO()
    fp.write(json.dumps(tags_data, ensure_ascii=False, sort_keys=True, indent=4).encode('utf8'))
    fp.seek(0)
    tags_file_name = 'Tags-%s.json' % tags_type
    mimetype = mimetypes.guess_type(os.path.basename(tags_file_name))[0]
    response = HttpResponse(content_type=mimetype)
    response["Content-Disposition"] = "attachment; filename=%s" % tags_file_name
    response.write(fp.read())
    return response


@login_required
def upload_tags(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    if not can_edit_tags(request.user):
        return JsonResponse({'error': _("You don't have an access to create tags") + ''})
    if 'tags_type' not in request.POST or request.POST['tags_type'] not in ['safe', 'unsafe']:
        return JsonResponse({'error': 'Unknown error'})
    fp = None
    for f in request.FILES.getlist('file'):
        fp = f
    if fp is None:
        return JsonResponse({'error': 'Unknown error'})
    res = CreateTagsFromFile(fp, request.POST['tags_type'])
    if res.error is not None:
        return JsonResponse({'error': str(res.error)})
    return JsonResponse({})


@unparallel_group(['mark'])
def download_all(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': "You don't have an access to download all marks"})
    arch = AllMarksTar()
    response = HttpResponse(content_type="application/x-tar-gz")
    response["Content-Disposition"] = 'attachment; filename={0}'.format(arch.name)
    response.write(arch.tempfile.read())

    return response


@unparallel_group(['mark'])
def upload_all(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})

    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': "You don't have an access to upload marks"})

    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    delete_all_marks = False
    if int(request.POST.get('delete', 0)) == 1:
        delete_all_marks = True

    if len(request.FILES.getlist('file')) == 0:
        return JsonResponse({'error': 'Archive with marks expected'})
    try:
        marks_dir = extract_tar_temp(request.FILES.getlist('file')[0])
    except Exception as e:
        logger.exception("Archive extraction failed" % e, stack_info=True)
        return JsonResponse({'error': 'Archive extraction failed'})

    res = UploadAllMarks(request.user, marks_dir.name, delete_all_marks)
    if res.error is not None:
        return JsonResponse({'error': res.error})
    return JsonResponse(res.numbers)
