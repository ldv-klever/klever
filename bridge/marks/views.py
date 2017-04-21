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
from django.db.models import Q, F
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, StreamingHttpResponse
from django.shortcuts import render
from django.template.defaulttags import register
from django.template.loader import get_template
from django.utils.translation import ugettext as _, activate
from django.utils.timezone import pytz

from bridge.vars import USER_ROLES, UNKNOWN_ERROR
from bridge.tableHead import Header
from bridge.utils import logger, unparallel_group, extract_archive, ArchiveFileContent, BridgeException,\
    BridgeErrorResponse

from users.models import View

from marks.tags import GetTagsData, GetParents, SaveTag, can_edit_tags, TagsInfo, CreateTagsFromFile
from marks.utils import NewMark, MarkAccess, DeleteMark
from marks.Download import ReadMarkArchive, MarkArchiveGenerator, AllMarksGen, UploadAllMarks
from marks.tables import MarkData, MarkChangesTable, MarkReportsTable, MarksList, MARK_TITLES
from marks.models import *


@register.filter
def value_type(value):
    return str(type(value))


@login_required
@unparallel_group(['MarkSafe', 'MarkUnsafe', 'MarkUnknown', 'UnsafeTag', 'SafeTag'])
def create_mark(request, mark_type, report_id):
    activate(request.user.extended.language)

    problem_description = None
    try:
        if mark_type == 'unsafe':
            report = ReportUnsafe.objects.get(pk=int(report_id))
        elif mark_type == 'safe':
            report = ReportSafe.objects.get(pk=int(report_id))
            if not report.root.job.safe_marks:
                return BridgeErrorResponse(_('Safe marks are disabled'))
        else:
            report = ReportUnknown.objects.get(pk=int(report_id))
            try:
                problem_description = ArchiveFileContent(report, report.problem_description).content.decode('utf8')
            except Exception as e:
                logger.exception("Can't get problem description for unknown '%s': %s" % (report.id, e))
                return BridgeErrorResponse(500)
    except ObjectDoesNotExist:
        return BridgeErrorResponse(504)
    if not MarkAccess(request.user, report=report).can_create():
        return BridgeErrorResponse(_("You don't have an access to create new marks"))
    tags = None
    if mark_type != 'unknown':
        try:
            tags = TagsInfo(mark_type, [])
        except Exception as e:
            logger.exception(e)
            return BridgeErrorResponse(500)

    return render(request, 'marks/CreateMark.html', {
        'report': report,
        'type': mark_type,
        'markdata': MarkData(mark_type, report=report),
        'can_freeze': (request.user.extended.role == USER_ROLES[2][0]),
        'tags': tags,
        'problem_description': problem_description
    })


@login_required
@unparallel_group(['MarkSafe', 'MarkUnsafe', 'MarkUnknown', 'UnsafeTag', 'SafeTag'])
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
        return BridgeErrorResponse(604)

    if mark.version == 0:
        return BridgeErrorResponse(605)

    history_set = mark.versions.order_by('-version')
    last_version = history_set.first()

    error_trace = None
    if mark_type == 'unsafe':
        with last_version.error_trace.file.file as fp:
            error_trace = fp.read().decode('utf8')

    tags = None
    if mark_type != 'unknown':
        try:
            tags = TagsInfo(mark_type, list(tag.tag.pk for tag in last_version.tags.all()))
        except Exception as e:
            logger.exception(e)
            return BridgeErrorResponse(500)
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
        'error_trace': error_trace,
        'report_id': request.GET.get('report_to_redirect')
    })


@login_required
@unparallel_group(['MarkSafe', 'MarkUnsafe', 'MarkUnknown'])
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
        return BridgeErrorResponse(604)
    if mark.version == 0:
        return BridgeErrorResponse(605)

    if not MarkAccess(request.user, mark=mark).can_edit():
        return BridgeErrorResponse(_("You don't have an access to edit this mark"))

    history_set = mark.versions.order_by('-version')
    last_version = history_set.first()

    error_trace = None
    if mark_type == 'unsafe':
        with last_version.error_trace.file.file as fp:
            error_trace = fp.read().decode('utf8')

    tags = None
    if mark_type != 'unknown':
        try:
            tags = TagsInfo(mark_type, list(tag.tag.pk for tag in last_version.tags.all()))
        except Exception as e:
            logger.exception(e)
            return BridgeErrorResponse(500)

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
                title += " (%s)" % m.author.get_full_name()
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
        'error_trace': error_trace,
        'report_id': request.GET.get('report_to_redirect')
    })


@login_required
@unparallel_group([MarkSafe, MarkUnsafe, MarkUnknown])
def save_mark(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        savedata = json.loads(unquote(request.POST.get('savedata', '{}')))
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if savedata.get('data_type') not in {'safe', 'unsafe', 'unknown'}:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    if 'report_id' in savedata:
        try:
            if savedata['data_type'] == 'unsafe':
                inst = ReportUnsafe.objects.get(pk=int(savedata['report_id']))
            elif savedata['data_type'] == 'safe':
                inst = ReportSafe.objects.get(pk=int(savedata['report_id']))
                if not inst.root.job.safe_marks:
                    return JsonResponse({'error': _('Safe marks are disabled')})
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
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    try:
        res = NewMark(inst, request.user, savedata['data_type'], savedata)
    except BridgeException as e:
        return JsonResponse({'error': str(e)})
    except Exception as e:
        logger.exception("Error while saving/creating mark: %s" % e, stack_info=True)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    try:
        return JsonResponse({'cache_id': MarkChangesTable(request.user, res.mark, res.changes).cache_id})
    except Exception as e:
        logger.exception('Error while saving changes of mark associations: %s' % e, stack_info=True)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})


@login_required
@unparallel_group(['MarkUnsafeCompare', 'MarkUnsafeConvert'])
def get_func_description(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    func_id = int(request.POST.get('func_id', '0'))
    func_type = request.POST.get('func_type', 'compare')
    if func_type == 'compare':
        try:
            func = MarkUnsafeCompare.objects.get(pk=func_id)
        except ObjectDoesNotExist:
            return JsonResponse({
                'error': _('The error traces comparison function was not found')
            })
    elif func_type == 'convert':
        try:
            func = MarkUnsafeConvert.objects.get(pk=func_id)
        except ObjectDoesNotExist:
            return JsonResponse({
                'error': _('The error traces conversion function was not found')
            })
    else:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    return JsonResponse({'description': func.description})


@login_required
@unparallel_group(['MarkSafe', 'MarkUnsafe', 'MarkUnknown'])
def get_mark_version_data(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return HttpResponse('')
    if int(request.POST.get('version', '0')) == 0:
        return JsonResponse({'error': _('The mark is being deleted')})

    mark_type = request.POST.get('type', None)
    if mark_type not in ['safe', 'unsafe', 'unknown']:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
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
        try:
            tags = TagsInfo(mark_type, list(tag.tag.pk for tag in mark_version.tags.all()))
        except BridgeException as e:
            return JsonResponse({'error': str(e)})
        except Exception as e:
            logger.exception(e)
            return JsonResponse({'error': str(UNKNOWN_ERROR)})
        data = data_templ.render({
            'markdata': MarkData(mark_type, mark_version=mark_version),
            'tags': tags,
            'can_edit': True,
            'error_trace': error_trace
        })
    return JsonResponse({'data': data})


@login_required
@unparallel_group(['MarkSafe', 'MarkUnsafe', 'MarkUnknown'])
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
@unparallel_group(['MarkSafe', 'MarkUnsafe', 'MarkUnknown'])
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
        return BridgeErrorResponse(604)
    if mark.version == 0:
        return BridgeErrorResponse(605)

    generator = MarkArchiveGenerator(mark)
    mimetype = mimetypes.guess_type(os.path.basename(generator.name))[0]
    response = StreamingHttpResponse(generator, content_type=mimetype)
    response["Content-Disposition"] = "attachment; filename=%s" % generator.name
    return response


@login_required
@unparallel_group(['MarkSafe', 'MarkUnsafe', 'MarkUnknown'])
def upload_marks(request):
    activate(request.user.extended.language)

    if not MarkAccess(request.user).can_create():
        return JsonResponse({'status': False, 'message': _("You don't have access to create new marks")})

    failed_marks = []
    mark_id = None
    mark_type = None
    num_of_new_marks = 0
    for f in request.FILES.getlist('file'):
        try:
            res = ReadMarkArchive(request.user, f)
        except BridgeException as e:
            failed_marks.append([str(e), f.name])
        except Exception as e:
            logger.exception(e)
            failed_marks.append([str(UNKNOWN_ERROR), f.name])
        else:
            num_of_new_marks += 1
            mark_id = res.mark.id
            mark_type = res.type
    if len(failed_marks) > 0:
        return JsonResponse({'status': False, 'messages': failed_marks})
    if num_of_new_marks == 1:
        return JsonResponse({
            'status': True, 'mark_id': str(mark_id), 'mark_type': mark_type
        })
    return JsonResponse({'status': True})


@login_required
@unparallel_group([MarkSafe, MarkUnsafe, MarkUnknown])
def delete_mark(request, mark_type, mark_id):
    obj_model = {
        'unsafe': (MarkUnsafe, ReportUnsafe),
        'safe': (MarkSafe, ReportSafe),
        'unknown': (MarkUnknown, ReportUnknown)
    }
    try:
        mark = obj_model[mark_type][0].objects.get(pk=mark_id)
    except ObjectDoesNotExist:
        return BridgeErrorResponse(604)
    if not MarkAccess(request.user, mark=mark).can_delete():
        return BridgeErrorResponse(_("You don't have an access to delete this mark"))
    DeleteMark(mark)
    if request.method == 'GET' and 'report_to_redirect' in request.GET:
        return HttpResponseRedirect(reverse('reports:%s' % mark_type, args=[request.GET['report_to_redirect']]))
    return HttpResponseRedirect(reverse('marks:mark_list', args=[mark_type]))


@login_required
@unparallel_group([MarkSafe, MarkUnsafe, MarkUnknown])
def delete_marks(request):
    activate(request.user.extended.language)
    if request.method != 'POST' or 'type' not in request.POST or 'ids' not in request.POST:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        mark_ids = json.loads(request.POST['ids'])
    except Exception as e:
        logger.exception("Json parsing error: %s" % e, stack_info=True)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if request.POST['type'] == 'unsafe':
        marks = MarkUnsafe.objects.filter(id__in=mark_ids)
    elif request.POST['type'] == 'safe':
        marks = MarkSafe.objects.filter(id__in=mark_ids)
    elif request.POST['type'] == 'unknown':
        marks = MarkUnknown.objects.filter(id__in=mark_ids)
    else:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    if not all(MarkAccess(request.user, mark=mark).can_delete() for mark in marks):
        return JsonResponse({'error': _("You can't delete one of the selected mark")})
    for mark in marks:
        DeleteMark(mark)
    return JsonResponse({})


@login_required
@unparallel_group([MarkSafe, MarkUnsafe, MarkUnknown])
def remove_versions(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
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
            return JsonResponse({'error': str(UNKNOWN_ERROR)})
        if mark.version == 0:
            return JsonResponse({'error': _('The mark is being deleted')})
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
@unparallel_group(['MarkSafe', 'MarkUnsafe', 'MarkUnknown'])
def get_mark_versions(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
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
            return JsonResponse({'error': str(UNKNOWN_ERROR)})
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
            title += " (%s)" % m.author.get_full_name()
        title += ': ' + m.comment
        mark_versions.append({'version': m.version, 'title': title})
    return render(request, 'marks/markVersions.html', {'versions': mark_versions})


@login_required
@unparallel_group([MarkAssociationsChanges])
def association_changes(request, association_id):
    activate(request.user.extended.language)

    try:
        ass_ch = MarkAssociationsChanges.objects.get(identifier=association_id)
    except ObjectDoesNotExist:
        return BridgeErrorResponse(_("Mark associations changes cache wasn't found"))
    try:
        data = json.loads(ass_ch.table_data)
    except Exception as e:
        logger.exception(e)
        return BridgeErrorResponse(500)
    return render(request, 'marks/SaveMarkResult.html', {
        'MarkTable': data,
        'header': Header(data.get('columns', []), MARK_TITLES).struct
    })


@login_required
@unparallel_group(['UnsafeTag', 'SafeTag'])
def show_tags(request, tags_type):
    activate(request.user.extended.language)

    if tags_type == 'unsafe':
        page_title = "Unsafe tags"
    else:
        page_title = "Safe tags"
    try:
        tags_data = GetTagsData(tags_type)
    except Exception as e:
        logger.exception(e)
        return BridgeErrorResponse(500)
    return render(request, 'marks/TagsTree.html', {
        'title': page_title,
        'tags': tags_data.table.data,
        'tags_type': tags_type,
        'can_edit': can_edit_tags(request.user)
    })


@login_required
@unparallel_group(['UnsafeTag', 'SafeTag'])
def get_tag_parents(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if 'tag_type' not in request.POST or request.POST['tag_type'] not in ['safe', 'unsafe']:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if 'tag_id' not in request.POST:
        if request.POST['tag_type'] == 'unsafe':
            return JsonResponse({'parents': json.dumps(list(tag.pk for tag in UnsafeTag.objects.order_by('tag')),
                                                       ensure_ascii=False, sort_keys=True, indent=4)})
        else:
            return JsonResponse({'parents': json.dumps(list(tag.pk for tag in SafeTag.objects.order_by('tag')),
                                                       ensure_ascii=False, sort_keys=True, indent=4)})
    try:
        res = GetParents(request.POST['tag_id'], request.POST['tag_type'])
    except BridgeException as e:
        return JsonResponse({'error': str(e)})
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    return JsonResponse({
        'parents': json.dumps(res.parents_ids, ensure_ascii=False, sort_keys=True, indent=4),
        'current': res.tag.parent_id if res.tag.parent_id is not None else 0
    })


@login_required
@unparallel_group([UnsafeTag, SafeTag])
def save_tag(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if not can_edit_tags(request.user):
        return JsonResponse({'error': _("You don't have an access to edit tags")})
    try:
        SaveTag(request.POST)
    except BridgeException as e:
        return JsonResponse({'error': str(e)})
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    return JsonResponse({})


@login_required
@unparallel_group([UnsafeTag, SafeTag])
def remove_tag(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if not can_edit_tags(request.user):
        return JsonResponse({'error': _("You don't have an access to remove tags")})
    if 'tag_type' not in request.POST or request.POST['tag_type'] not in ['safe', 'unsafe']:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
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
@unparallel_group(['UnsafeTag', 'SafeTag'])
def get_tags_data(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if 'tag_type' not in request.POST or request.POST['tag_type'] not in ['safe', 'unsafe']:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if 'selected_tags' not in request.POST:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    deleted_tag = None
    if 'deleted' in request.POST and request.POST['deleted'] is not None:
        try:
            deleted_tag = int(request.POST['deleted'])
        except Exception as e:
            logger.error("Deleted tag has wrong format: %s" % e)
            return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        selected_tags = json.loads(request.POST['selected_tags'])
    except Exception as e:
        logger.error("Can't parse selected tags: %s" % e, stack_info=True)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        res = TagsInfo(request.POST['tag_type'], selected_tags, deleted_tag)
    except BridgeException as e:
        return JsonResponse({'error': str(e)})
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    return JsonResponse({
        'available': json.dumps(res.available, ensure_ascii=False, sort_keys=True, indent=4),
        'selected': json.dumps(res.selected, ensure_ascii=False, sort_keys=True, indent=4),
        'tree': get_template('marks/MarkTagsTree.html').render({
            'tags': res.table, 'tags_type': res.tag_type, 'can_edit': True
        })
    })


@login_required
@unparallel_group(['UnsafeTag', 'SafeTag'])
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
@unparallel_group([UnsafeTag, SafeTag])
def upload_tags(request):
    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if not can_edit_tags(request.user):
        return JsonResponse({'error': _("You don't have an access to create tags") + ''})
    if 'tags_type' not in request.POST or request.POST['tags_type'] not in ['safe', 'unsafe']:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    fp = None
    for f in request.FILES.getlist('file'):
        fp = f
    if fp is None:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        CreateTagsFromFile(fp, request.POST['tags_type'])
    except BridgeException as e:
        return JsonResponse({'error': str(e)})
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    return JsonResponse({})


@unparallel_group(['MarkSafe', 'MarkUnsafe', 'MarkUnknown'])
def download_all(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': "You don't have an access to download all marks"})
    generator = AllMarksGen()
    mimetype = mimetypes.guess_type(os.path.basename(generator.name))[0]
    response = StreamingHttpResponse(generator, content_type=mimetype)
    response["Content-Disposition"] = "attachment; filename=%s" % generator.name
    return response


@unparallel_group([MarkSafe, MarkUnsafe, MarkUnknown])
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
        marks_dir = extract_archive(request.FILES.getlist('file')[0])
    except Exception as e:
        logger.exception("Archive extraction failed" % e, stack_info=True)
        return JsonResponse({'error': 'Archive extraction failed'})

    try:
        res = UploadAllMarks(request.user, marks_dir.name, delete_all_marks)
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': 'Unknown error'})
    return JsonResponse(res.numbers)


@unparallel_group(['MarkSafe', 'MarkUnsafe'])
def get_inline_mark_form(request):
    obj_model = {
        'safe': (MarkSafeHistory, ReportSafe),
        'unsafe': (MarkUnsafeHistory, ReportUnsafe)
    }
    if request.method != 'POST' or 'type' not in request.POST \
            or ('mark_id' not in request.POST and 'report_id' not in request.POST) \
            or request.POST['type'] not in obj_model:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    if 'mark_id' in request.POST:
        try:
            last_version = obj_model[request.POST['type']][0].objects.get(
                mark_id=request.POST['mark_id'], version=F('mark__version')
            )
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('The mark was not found')})
        markdata = MarkData(request.POST['type'], mark_version=last_version)
        try:
            tags = TagsInfo(request.POST['type'], list(tag.tag.pk for tag in last_version.tags.all()))
        except BridgeException as e:
            return JsonResponse({'error': str(e)})
        except Exception as e:
            logger.exception(e)
            return JsonResponse({'error': str(UNKNOWN_ERROR)})
    else:
        try:
            report = obj_model[request.POST['type']][1].objects.get(id=request.POST['report_id'])
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('The report was not found')})
        markdata = MarkData(request.POST['type'], report=report)
        try:
            tags = TagsInfo(request.POST['type'], [])
        except BridgeException as e:
            return JsonResponse({'error': str(e)})
        except Exception as e:
            logger.exception(e)
            return JsonResponse({'error': str(UNKNOWN_ERROR)})

    return JsonResponse({
        'data': get_template('marks/InlineMarkForm.html').render({
            'type': request.POST['type'], 'markdata': markdata, 'tags': tags
        })
    })
