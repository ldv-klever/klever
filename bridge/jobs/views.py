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
from datetime import datetime
from urllib.parse import quote
from difflib import unified_diff
from wsgiref.util import FileWrapper

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.db.models import Q, F
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.template import loader, Template, Context
from django.utils.translation import ugettext as _, activate, string_concat
from django.utils.timezone import pytz

from tools.profiling import unparallel_group
from bridge.vars import VIEW_TYPES, UNKNOWN_ERROR, JOB_STATUS, PRIORITY, JOB_ROLES, JOB_WEIGHT
from bridge.utils import file_get_or_create, extract_archive, logger, BridgeException, BridgeErrorResponse

from users.models import User, View, PreferableView
from reports.models import ReportComponent, ReportRoot
from reports.UploadReport import UploadReport, CollapseReports
from reports.comparison import can_compare
from reports.utils import FilesForCompetitionArchive
from service.utils import StartJobDecision, StopDecision, GetJobsProgresses

import jobs.utils
import marks.SafeUtils as SafeUtils
from jobs.models import Job, RunHistory, JobHistory, JobFile
from jobs.ViewJobData import ViewJobData
from jobs.JobTableProperties import TableTree
from jobs.Download import UploadJob, JobArchiveGenerator, KleverCoreArchiveGen, JobsArchivesGen,\
    UploadReportsWithoutDecision


@login_required
@unparallel_group([])
def tree_view(request):
    activate(request.user.extended.language)

    view_args = {}
    if request.GET.get('view_type') == VIEW_TYPES[1][0]:
        view_args['view'] = request.GET.get('view')
        view_args['view_id'] = request.GET.get('view_id')

    months_choices = []
    for i in range(1, 13):
        months_choices.append((i, datetime(2016, i, 1).strftime('%B')))
    curr_year = datetime.now().year

    return render(request, 'jobs/tree.html', {
        'users': User.objects.all(),
        'statuses': JOB_STATUS,
        'weights': JOB_WEIGHT,
        'priorities': list(reversed(PRIORITY)),
        'months': months_choices,
        'years': list(range(curr_year - 3, curr_year + 1)),
        'TableData': TableTree(request.user, **view_args)
    })


@login_required
@unparallel_group([PreferableView, 'View'])
def preferable_view(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    view_id = request.POST.get('view_id', None)
    view_type = request.POST.get('view_type', None)
    if view_id is None or view_type is None or view_type not in list(x[0] for x in VIEW_TYPES):
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    if view_id == 'default':
        pref_views = request.user.preferableview_set.filter(view__type=view_type)
        if len(pref_views):
            pref_views.delete()
            return JsonResponse({'message': _("The default view was made preferred")})
        return JsonResponse({'error': _("The default view is already preferred")})

    try:
        user_view = View.objects.get(Q(pk=view_id, type=view_type) & (Q(author=request.user) | Q(shared=True)))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _("The view was not found")})
    request.user.preferableview_set.filter(view__type=view_type).delete()
    pref_view = PreferableView()
    pref_view.user = request.user
    pref_view.view = user_view
    pref_view.save()
    return JsonResponse({'message': _("The preferred view was successfully changed")})


@login_required
@unparallel_group(['View'])
def check_view_name(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    view_name = request.POST.get('view_title', None)
    view_type = request.POST.get('view_type', None)
    if view_name is None or view_type is None:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    if view_name == '':
        return JsonResponse({'error': _("The view name is required")})

    if view_name == str(_('Default')) or len(request.user.view_set.filter(type=view_type, name=view_name)):
        return JsonResponse({'error': _("Please choose another view name")})
    return JsonResponse({})


@login_required
@unparallel_group([View])
def save_view(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    view_data = request.POST.get('view', None)
    view_name = request.POST.get('title', '')
    view_id = request.POST.get('view_id', None)
    view_type = request.POST.get('view_type', None)
    if view_data is None or view_type is None or view_type not in list(x[0] for x in VIEW_TYPES):
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if view_id == 'default':
        return JsonResponse({'error': _("You can't edit the default view")})
    elif view_id is not None:
        try:
            new_view = request.user.view_set.get(pk=int(view_id))
        except ObjectDoesNotExist:
            return JsonResponse({'error': _("The view was not found or you don't have an access to it")})
    elif len(view_name) > 0:
        new_view = View()
        new_view.name = view_name
        new_view.type = view_type
        new_view.author = request.user
    else:
        return JsonResponse({'error': _('The view name is required')})
    new_view.view = view_data
    new_view.save()
    return JsonResponse({
        'view_id': new_view.pk, 'view_name': new_view.name,
        'message': _("The view was successfully saved")
    })


@login_required
@unparallel_group([View])
def remove_view(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    v_id = request.POST.get('view_id', 0)
    view_type = request.POST.get('view_type', None)
    if view_type is None:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if v_id == 'default':
        return JsonResponse({'error': _("You can't remove the default view")})
    try:
        View.objects.get(author=request.user, pk=v_id, type=view_type).delete()
    except ObjectDoesNotExist:
        return JsonResponse({'error': _("The view was not found or you don't have an access to it")})
    return JsonResponse({'message': _("The view was successfully removed")})


@login_required
@unparallel_group([View])
def share_view(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    v_id = request.POST.get('view_id', 0)
    view_type = request.POST.get('view_type', None)
    if view_type is None:
        return JsonResponse({'error': 'Unknown error'})
    if v_id == 'default':
        return JsonResponse({'error': _("You can't share the default view")})
    try:
        view = View.objects.get(author=request.user, pk=v_id, type=view_type)
    except ObjectDoesNotExist:
        return JsonResponse({'error': _("The view was not found or you don't have an access to it")})
    view.shared = not view.shared
    view.save()
    if view.shared:
        return JsonResponse({'message': _("The view was successfully shared")})
    PreferableView.objects.filter(view=view).exclude(user=request.user).delete()
    return JsonResponse({'message': _("The view was hidden from other users")})


@login_required
@unparallel_group([])
def show_job(request, job_id=None):
    activate(request.user.extended.language)

    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return BridgeErrorResponse(404)
    job_access = jobs.utils.JobAccess(request.user, job)
    if not job_access.can_view():
        return BridgeErrorResponse(400)

    parent_set = []
    next_parent = job.parent
    while next_parent is not None:
        parent_set.append(next_parent)
        next_parent = next_parent.parent
    parent_set.reverse()
    parents = []
    for parent in parent_set:
        if jobs.utils.JobAccess(request.user, parent).can_view():
            job_id = parent.pk
        else:
            job_id = None
        parents.append({
            'pk': job_id,
            'name': parent.name,
        })

    children = []
    for child in job.children.all().order_by('change_date'):
        if jobs.utils.JobAccess(request.user, child).can_view():
            children.append({'pk': child.pk, 'name': child.name})

    try:
        report = ReportComponent.objects.get(root__job=job, parent=None)
    except ObjectDoesNotExist:
        report = None

    view_args = {}
    view_type = request.GET.get('view_type')
    if view_type == VIEW_TYPES[2][0]:
        view_args['view'] = request.GET.get('view')
        view_args['view_id'] = request.GET.get('view_id')

    try:
        progress = GetJobsProgresses(request.user, [job.id]).data[job.id]
    except Exception as e:
        logger.exception(e)
        return BridgeErrorResponse(500)
    return render(
        request,
        'jobs/viewJob.html',
        {
            'job': job,
            'last_version': job.versions.get(version=job.version),
            'parents': parents,
            'children': children,
            'progress': progress,
            'reportdata': ViewJobData(request.user, report, **view_args),
            'created_by': job.versions.get(version=1).change_author,
            'can_delete': job_access.can_delete(),
            'can_edit': job_access.can_edit(),
            'can_create': job_access.can_create(),
            'can_decide': job_access.can_decide(),
            'can_upload_reports': job_access.can_upload_reports(),
            'can_download': job_access.can_download(),
            'can_stop': job_access.can_stop(),
            'can_collapse': job_access.can_collapse(),
            'can_dfc': job_access.can_dfc(),
            'can_clear_verifications': job_access.can_clear_verifications()
        }
    )


@login_required
@unparallel_group([])
def get_job_data(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        job = Job.objects.get(pk=request.POST.get('job_id', 0))
    except ObjectDoesNotExist:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    data = {'jobstatus': job.status}
    if 'just_status' in request.POST and not json.loads(request.POST['just_status']):
        try:
            progress = GetJobsProgresses(request.user, [job.id]).data[job.id]
        except Exception as e:
            logger.exception(e)
            return JsonResponse({'error': str(UNKNOWN_ERROR)})
        try:
            data['jobdata'] = loader.get_template('jobs/jobData.html').render({
                'reportdata': ViewJobData(
                    request.user,
                    ReportComponent.objects.get(root__job=job, parent=None),
                    view=request.POST.get('view', None)
                )
            }, request)
        except ObjectDoesNotExist:
            pass
        data['progress'] = loader.get_template('jobs/jobProgress.html').render({'progress': progress}, request)
    return JsonResponse(data)


@login_required
@unparallel_group([])
def edit_job(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponse('')

    job_id = request.POST.get('job_id', 0)

    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponse('')
    if not jobs.utils.JobAccess(request.user, job).can_edit():
        return HttpResponse('')

    version = int(request.POST.get('version', 0))
    if version > 0:
        job_version = job.versions.get(version=version)
    else:
        job_version = job.versions.order_by('-change_date')[0]

    job_versions = []
    for j in job.versions.order_by('-version'):
        if j.version == job.version:
            title = _("Current version")
        else:
            job_time = j.change_date.astimezone(pytz.timezone(request.user.extended.timezone))
            title = '%s (%s): %s' % (job_time.strftime("%d.%m.%Y %H:%M:%S"), j.change_author.get_full_name(), j.comment)
        job_versions.append({
            'version': j.version,
            'title': title
        })

    parent_identifier = None
    if job_version.parent is not None:
        parent_identifier = job_version.parent.identifier

    return render(request, 'jobs/editJob.html', {
        'parent_id': parent_identifier,
        'job': job_version,
        'job_id': job_id,
        'roles': jobs.utils.role_info(job_version, request.user),
        'job_roles': JOB_ROLES,
        'job_versions': job_versions,
        'version': version,
        'filedata': jobs.utils.FileData(job_version).filedata
    })


@login_required
@unparallel_group(['Job', JobHistory])
def remove_versions(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    job_id = int(request.POST.get('job_id', 0))
    try:
        job = Job.objects.get(pk=job_id)
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('The job was not found')})
    if not jobs.utils.JobAccess(request.user, job).can_edit():
        return JsonResponse({'error': _("You don't have access to delete versions")})

    versions = json.loads(request.POST.get('versions', '[]'))

    deleted_versions = jobs.utils.delete_versions(job, versions)
    if deleted_versions > 0:
        return JsonResponse({'message': _('Selected versions were successfully deleted')})
    return JsonResponse({'error': _('Nothing to delete')})


@login_required
@unparallel_group([])
def get_job_versions(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    job_id = int(request.POST.get('job_id', 0))
    try:
        job = Job.objects.get(pk=job_id)
    except ObjectDoesNotExist:
        return JsonResponse({'message': _('The job was not found')})
    job_versions = []
    for j in job.versions.filter(~Q(version__in=[job.version, 1])).order_by('-version'):
        title = '%s (%s): %s' % (
            j.change_date.astimezone(pytz.timezone(request.user.extended.timezone)).strftime("%d.%m.%Y %H:%M:%S"),
            j.change_author.get_full_name(), j.comment
        )
        job_versions.append({'version': j.version, 'title': title})
    return render(request, 'jobs/viewVersions.html', {'versions': job_versions})


@login_required
@unparallel_group([])
def copy_new_job(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponse('')
    if not jobs.utils.JobAccess(request.user).can_create():
        return HttpResponse('')

    roles = {
        'user_roles': [],
        'global': JOB_ROLES[0][0],
        'available_users': []
    }
    for u in User.objects.filter(~Q(pk=request.user.pk)):
        roles['available_users'].append({'id': u.pk, 'name': u.get_full_name()})

    job = get_object_or_404(Job, pk=int(request.POST.get('parent_id', 0)))
    job_version = job.versions.order_by('-change_date')[0]

    return render(request, 'jobs/createJob.html', {
        'parent_id': job.identifier,
        'job': job_version,
        'roles': roles,
        'safe_marks': job.safe_marks,
        'job_roles': JOB_ROLES,
        'filedata': jobs.utils.FileData(job_version).filedata
    })


@login_required
@unparallel_group([Job])
def save_job(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    job_kwargs = {
        'name': request.POST.get('title', ''),
        'description': request.POST.get('description', ''),
        'global_role': request.POST.get('global_role', JOB_ROLES[0][0]),
        'user_roles': json.loads(request.POST.get('user_roles', '[]')),
        'filedata': json.loads(request.POST.get('file_data', '[]')),
        'author': request.user
    }

    job_id = request.POST.get('job_id', None)
    parent_identifier = request.POST.get('parent_identifier', None)

    if job_id is not None:
        try:
            job = Job.objects.get(pk=int(job_id))
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('The job was not found')})
        if not jobs.utils.JobAccess(request.user, job).can_edit():
            return JsonResponse({'error': _("You don't have an access to edit this job")})
        if parent_identifier is not None and len(parent_identifier) > 0:
            parents = Job.objects.filter(identifier__startswith=parent_identifier)
            if len(parents) == 0:
                return JsonResponse({'error': _('The job parent was not found')})
            elif len(parents) > 1:
                return JsonResponse({
                    'error': _('Several parents match the specified identifier, '
                               'please increase the length of the parent identifier')
                })
            parent = parents[0]
            if job.parent is None:
                return JsonResponse({'error': _("Parent can't be specified for root jobs")})
            if not jobs.utils.check_new_parent(job, parent):
                return JsonResponse({'error': _("The specified parent can't be set for this job")})
            job_kwargs['parent'] = parent
        elif job.parent is not None:
            return JsonResponse({'error': _("The parent identifier is required for this job")})
        if job.version != int(request.POST.get('last_version', 0)):
            return JsonResponse({'error': _("Your version is expired, please reload the page")})
        job_kwargs['job'] = job
        job_kwargs['comment'] = request.POST.get('comment', '')
        job_kwargs['absolute_url'] = 'http://' + request.get_host() + reverse('jobs:job', args=[job_id])
        try:
            jobs.utils.update_job(job_kwargs)
        except Exception as e:
            logger.exception(str(e), stack_info=True)
            return JsonResponse({'error': _('Updating the job failed')})
        return JsonResponse({'job_id': job.pk})
    elif parent_identifier is not None:
        try:
            parent = Job.objects.get(identifier=parent_identifier)
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('The job parent was not found')})
        if not jobs.utils.JobAccess(request.user).can_create():
            return JsonResponse({'error': _("You don't have an access to create new jobs")})
        job_kwargs['parent'] = parent
        job_kwargs['absolute_url'] = 'http://' + request.get_host()
        job_kwargs['safe_marks'] = json.loads(request.POST.get('safe_marks', 'false'))
        try:
            newjob = jobs.utils.create_job(job_kwargs)
        except BridgeException as e:
            return JsonResponse({'error': str(e)})
        except Exception as e:
            logger.exception(str(e))
            return JsonResponse({'error': _('Saving the job failed')})
        return JsonResponse({'job_id': newjob.pk})
    return JsonResponse({'error': str(UNKNOWN_ERROR)})


@login_required
@unparallel_group([Job])
def remove_jobs(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        jobs_for_del = json.loads(request.POST.get('jobs', '[]'))
        jobs.utils.remove_jobs_by_id(request.user, jobs_for_del)
    except BridgeException as e:
        return JsonResponse({'error': str(e)})
    except Exception as e:
        logger.exception(str(e))
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    return JsonResponse({})


@login_required
@unparallel_group([])
def showjobdata(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponse('')
    try:
        job = Job.objects.get(pk=int(request.POST.get('job_id', 0)))
    except ObjectDoesNotExist:
        return HttpResponse('')
    try:
        job_version = JobHistory.objects.get(job=job, version=F('job__version'))
    except ObjectDoesNotExist:
        return HttpResponse('')

    return render(request, 'jobs/showJob.html', {
        'job': job,
        'description': job.versions.get(version=job.version).description,
        'filedata': jobs.utils.FileData(job.versions.get(version=job.version)).filedata,
        'roles': jobs.utils.role_info(job_version, request.user)
    })


@login_required
@unparallel_group([JobFile])
def upload_file(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponse('')
    for f in request.FILES:
        fname = request.FILES[f].name
        if not all(ord(c) < 128 for c in fname):
            title_size = len(fname)
            if title_size > 30:
                fname = fname[(title_size - 30):]
        try:
            check_sum = file_get_or_create(request.FILES[f], fname, JobFile, True)[1]
        except Exception as e:
            return JsonResponse({'error': str(string_concat(_('File uploading failed'), ' (%s): ' % fname, e))})
        return JsonResponse({'checksum': check_sum})
    return JsonResponse({'error': str(UNKNOWN_ERROR)})


@login_required
@unparallel_group([])
def download_file(request, file_id):
    if request.method == 'POST':
        return BridgeErrorResponse(301)
    try:
        source = jobs.utils.FileSystem.objects.get(pk=file_id)
    except ObjectDoesNotExist:
        return BridgeErrorResponse(_('The file was not found'))
    if source.file is None:
        logger.error('Trying to download directory')
        return BridgeErrorResponse(500)

    mimetype = mimetypes.guess_type(os.path.basename(source.name))[0]
    response = StreamingHttpResponse(FileWrapper(source.file.file, 8192), content_type=mimetype)
    response['Content-Length'] = len(source.file.file)
    response['Content-Disposition'] = "attachment; filename=%s" % quote(source.name)
    return response


@login_required
@unparallel_group([])
def download_job(request, job_id):
    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return BridgeErrorResponse(404)
    if not jobs.utils.JobAccess(request.user, job).can_download():
        return BridgeErrorResponse(400)

    generator = JobArchiveGenerator(job)
    mimetype = mimetypes.guess_type(os.path.basename(generator.arcname))[0]
    response = StreamingHttpResponse(generator, content_type=mimetype)
    response["Content-Disposition"] = "attachment; filename=%s" % generator.arcname
    return response


@login_required
@unparallel_group([])
def download_jobs(request):
    if request.method != 'POST' or 'job_ids' not in request.POST:
        return BridgeErrorResponse(301, back=reverse('jobs:tree'))
    jobs_list = Job.objects.filter(pk__in=json.loads(request.POST['job_ids']))
    for job in jobs_list:
        if not jobs.utils.JobAccess(request.user, job).can_download():
            return BridgeErrorResponse(_("You don't have an access to one of the selected jobs"),
                                       back=reverse('jobs:tree'))
    generator = JobsArchivesGen(jobs_list)

    mimetype = mimetypes.guess_type(os.path.basename('KleverJobs.zip'))[0]
    response = StreamingHttpResponse(generator, content_type=mimetype)
    response["Content-Disposition"] = "attachment; filename=KleverJobs.zip"
    return response


@login_required
@unparallel_group([])
def check_access(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    for job_id in json.loads(request.POST.get('jobs', '[]')):
        try:
            job = Job.objects.get(pk=int(job_id))
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('One of the selected jobs was not found')})
        if not jobs.utils.JobAccess(request.user, job).can_download():
            return JsonResponse({'error': _("You don't have an access to download one of the selected jobs")})
    return JsonResponse({})


@login_required
@unparallel_group([Job])
def upload_job(request, parent_id=None):
    activate(request.user.extended.language)

    if not jobs.utils.JobAccess(request.user).can_create():
        return JsonResponse({'error': str(_("You don't have an access to upload jobs"))})
    if len(parent_id) == 0:
        return JsonResponse({'error': _("The parent identifier was not got")})
    parents = Job.objects.filter(identifier__startswith=parent_id)
    if len(parents) == 0:
        return JsonResponse({'error': _("The parent with the specified identifier was not found")})
    elif len(parents) > 1:
        return JsonResponse({'error': _("Too many jobs starts with the specified identifier")})
    parent = parents[0]
    errors = []
    for f in request.FILES.getlist('file'):
        try:
            job_dir = extract_archive(f)
        except Exception as e:
            logger.exception("Archive extraction failed: %s" % e, stack_info=True)
            errors.append(_('Extraction of the archive "%(arcname)s" has failed') % {'arcname': f.name})
            continue
        try:
            UploadJob(parent, request.user, job_dir.name)
        except BridgeException as e:
            errors.append(
                _('Creating the job from archive "%(arcname)s" failed: %(message)s') % {
                    'arcname': f.name, 'message': str(e)
                }
            )
        except Exception as e:
            logger.exception(e)
            errors.append(
                _('Creating the job from archive "%(arcname)s" failed: %(message)s') % {
                    'arcname': f.name, 'message': _('The job archive is corrupted')
                }
            )
    if len(errors) > 0:
        return JsonResponse({'errors': list(str(x) for x in errors)})
    return JsonResponse({})


@unparallel_group([Job])
def decide_job(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})

    if 'job format' not in request.POST:
        return JsonResponse({'error': 'Job format is not specified'})
    if 'report' not in request.POST:
        return JsonResponse({'error': 'Start report is not specified'})

    if 'job id' not in request.session:
        return JsonResponse({'error': "Session does not have job id"})
    try:
        job = Job.objects.get(pk=int(request.session['job id']), format=int(request.POST['job format']))
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'The job was not found'})
    except ValueError:
        return JsonResponse({'error': 'Unknown error'})

    attempt = int(request.POST.get('attempt', 0))
    if not jobs.utils.JobAccess(request.user, job).klever_core_access():
        return JsonResponse({
            'error': 'User "{0}" doesn\'t have access to decide job "{1}"'.format(request.user, job.identifier)
        })
    if attempt == 0:
        if job.status != JOB_STATUS[1][0]:
            return JsonResponse({'error': 'Only pending jobs can be decided'})
        jobs.utils.change_job_status(job, JOB_STATUS[2][0])

    err = UploadReport(job, json.loads(request.POST.get('report', '{}')), attempt=attempt).error
    if err is not None:
        return JsonResponse({'error': err})

    generator = KleverCoreArchiveGen(job)
    mimetype = mimetypes.guess_type(os.path.basename(generator.arcname))[0]
    response = StreamingHttpResponse(generator, content_type=mimetype)
    response["Content-Disposition"] = "attachment; filename=%s" % generator.arcname
    return response


@login_required
@unparallel_group([])
def getfilecontent(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        file_id = int(request.POST.get('file_id', 0))
    except ValueError:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        source = jobs.utils.FileSystem.objects.get(pk=int(file_id))
    except ObjectDoesNotExist:
        return JsonResponse({'message': _("The file was not found")})
    return HttpResponse(source.file.file.read())


@login_required
@unparallel_group([Job])
def stop_decision(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        job = Job.objects.get(pk=int(request.POST.get('job_id', 0)))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _("The job was not found")})
    if not jobs.utils.JobAccess(request.user, job).can_stop():
        return JsonResponse({'error': _("You don't have an access to stop decision of this job")})
    try:
        StopDecision(job)
    except BridgeException as e:
        return JsonResponse({'error': str(e)})
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    return JsonResponse({})


@login_required
@unparallel_group([Job])
def run_decision(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if any(x not in request.POST for x in ['data', 'job_id']):
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        configuration = jobs.utils.GetConfiguration(user_conf=json.loads(request.POST['data'])).configuration
    except ValueError:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if configuration is None:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        StartJobDecision(request.user, request.POST['job_id'], configuration)
    except BridgeException as e:
        return JsonResponse({'error': str(e)})
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    return JsonResponse({})


@login_required
@unparallel_group([])
def prepare_decision(request, job_id):
    activate(request.user.extended.language)
    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return BridgeErrorResponse(404)
    if request.method == 'POST' and 'conf_name' in request.POST:
        current_conf = request.POST['conf_name']
        if request.POST['conf_name'] == 'file_conf':
            if 'file_conf' not in request.FILES:
                return BridgeErrorResponse(301)
            try:
                configuration = jobs.utils.GetConfiguration(
                    file_conf=json.loads(request.FILES['file_conf'].read().decode('utf8'))
                ).configuration
            except Exception as e:
                logger.exception(e, stack_info=True)
                return BridgeErrorResponse(500)
        else:
            configuration = jobs.utils.GetConfiguration(conf_name=request.POST['conf_name']).configuration
    else:
        configuration = jobs.utils.GetConfiguration(conf_name=settings.DEF_KLEVER_CORE_MODE).configuration
        current_conf = settings.DEF_KLEVER_CORE_MODE
    if configuration is None:
        return BridgeErrorResponse(500)

    try:
        data = jobs.utils.StartDecisionData(request.user, configuration)
    except BridgeException as e:
        return BridgeErrorResponse(str(e))
    except Exception as e:
        logger.exception(e)
        return BridgeErrorResponse(500)
    return render(request, 'jobs/startDecision.html', {
        'job': job, 'data': data, 'current_conf': current_conf,
        'configurations': jobs.utils.get_default_configurations()
    })


@login_required
@unparallel_group([Job])
def fast_run_decision(request):
    activate(request.user.extended.language)
    if request.method != 'POST' or 'job_id' not in request.POST:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    configuration = jobs.utils.GetConfiguration(conf_name=settings.DEF_KLEVER_CORE_MODE).configuration
    if configuration is None:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        StartJobDecision(request.user, request.POST['job_id'], configuration)
    except BridgeException as e:
        return JsonResponse({'error': str(e)})
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    return JsonResponse({})


@login_required
@unparallel_group([Job])
def lastconf_run_decision(request):
    activate(request.user.extended.language)
    if request.method != 'POST' or 'job_id' not in request.POST:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    last_run = RunHistory.objects.filter(job_id=request.POST['job_id']).order_by('date').last()
    if last_run is None:
        return JsonResponse({'error': _('The job was not decided before')})
    try:
        with last_run.configuration.file as fp:
            configuration = jobs.utils.GetConfiguration(file_conf=json.loads(fp.read().decode('utf8'))).configuration
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if configuration is None:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        StartJobDecision(request.user, request.POST['job_id'], configuration)
    except BridgeException as e:
        return JsonResponse({'error': str(e)})
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    return JsonResponse({})


@login_required
@unparallel_group([])
def check_compare_access(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        j1 = Job.objects.get(pk=request.POST.get('job1', 0))
        j2 = Job.objects.get(pk=request.POST.get('job2', 0))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('One of the selected jobs was not found, please reload page')})
    if not can_compare(request.user, j1, j2):
        return JsonResponse({'error': _("You can't compare the selected jobs")})
    return JsonResponse({})


@login_required
@unparallel_group([])
def jobs_files_comparison(request, job1_id, job2_id):
    activate(request.user.extended.language)
    try:
        job1 = Job.objects.get(pk=job1_id)
        job2 = Job.objects.get(pk=job2_id)
    except ObjectDoesNotExist:
        return BridgeErrorResponse(405)
    if not can_compare(request.user, job1, job2):
        return BridgeErrorResponse(507)
    try:
        data = jobs.utils.GetFilesComparison(request.user, job1, job2).data
    except BridgeException as e:
        return BridgeErrorResponse(str(e))
    except Exception as e:
        logger.exception(e)
        return BridgeErrorResponse(500)
    return render(request, 'jobs/comparison.html', {'job1': job1, 'job2': job2, 'data': data})


@login_required
@unparallel_group([])
def get_file_by_checksum(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        check_sums = json.loads(request.POST['check_sums'])
    except Exception as e:
        logger.exception("Json parsing failed: %s" % e, stack_info=True)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if len(check_sums) == 1:
        try:
            f = JobFile.objects.get(hash_sum=check_sums[0])
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('The file was not found')})
        return HttpResponse(f.file.read())
    elif len(check_sums) == 2:
        try:
            f1 = JobFile.objects.get(hash_sum=check_sums[0])
            f2 = JobFile.objects.get(hash_sum=check_sums[1])
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('The file was not found')})
        diff_result = []
        with f1.file as fp1, f2.file as fp2:
            for line in unified_diff(
                fp1.read().decode('utf8').split('\n'), fp2.read().decode('utf8').split('\n'),
                fromfile=request.POST.get('job1_name', ''), tofile=request.POST.get('job2_name', '')
            ):
                diff_result.append(line)
        return HttpResponse('\n'.join(diff_result))
    return JsonResponse({'error': str(UNKNOWN_ERROR)})


@login_required
@unparallel_group([])
def download_configuration(request, runhistory_id):
    try:
        run_history = RunHistory.objects.get(id=runhistory_id)
    except ObjectDoesNotExist:
        return BridgeErrorResponse(_('The configuration was not found'))

    file_name = "job-%s.conf" % run_history.job.identifier[:5]
    mimetype = mimetypes.guess_type(file_name)[0]
    response = StreamingHttpResponse(FileWrapper(run_history.configuration.file, 8192), content_type=mimetype)
    response['Content-Length'] = len(run_history.configuration.file)
    response['Content-Disposition'] = "attachment; filename=%s" % quote(file_name)
    return response


@login_required
def get_def_start_job_val(request):
    activate(request.user.extended.language)
    if request.method != 'POST' or 'name' not in request.POST or 'value' not in request.POST:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if request.POST['name'] == 'formatter' and request.POST['value'] in settings.KLEVER_CORE_LOG_FORMATTERS:
        return JsonResponse({'value': settings.KLEVER_CORE_LOG_FORMATTERS[request.POST['value']]})
    if request.POST['name'] == 'sub_jobs_proc_parallelism' \
            and request.POST['value'] in settings.KLEVER_CORE_PARALLELISM_PACKS:
        return JsonResponse({
            'value': Template('{% load l10n %}{{ val|localize }}').render(Context({
                'val': settings.KLEVER_CORE_PARALLELISM_PACKS[request.POST['value']][0]
            }))
        })
    if request.POST['name'] == 'build_parallelism' \
            and request.POST['value'] in settings.KLEVER_CORE_PARALLELISM_PACKS:
        return JsonResponse({
            'value': Template('{% load l10n %}{{ val|localize }}').render(Context({
                'val': settings.KLEVER_CORE_PARALLELISM_PACKS[request.POST['value']][1]
            }))
        })
    if request.POST['name'] == 'tasks_gen_parallelism' \
            and request.POST['value'] in settings.KLEVER_CORE_PARALLELISM_PACKS:
        return JsonResponse({
            'value': Template('{% load l10n %}{{ val|localize }}').render(Context({
                'val': settings.KLEVER_CORE_PARALLELISM_PACKS[request.POST['value']][2]
            }))
        })
    if request.POST['name'] == 'results_processing_parallelism' \
            and request.POST['value'] in settings.KLEVER_CORE_PARALLELISM_PACKS:
        return JsonResponse({
            'value': Template('{% load l10n %}{{ val|localize }}').render(Context({
                'val': settings.KLEVER_CORE_PARALLELISM_PACKS[request.POST['value']][3]
            }))
        })
    return JsonResponse({'error': str(UNKNOWN_ERROR)})


@login_required
@unparallel_group([Job])
def collapse_reports(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        job = Job.objects.get(pk=request.POST.get('job_id', 0))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('The job was not found')})
    if not jobs.utils.JobAccess(request.user, job).can_collapse():
        return JsonResponse({'error': _("You don't have an access to collapse reports")})
    CollapseReports(job)
    return JsonResponse({})


@login_required
@unparallel_group([])
def do_job_has_children(request):
    activate(request.user.extended.language)

    if request.method != 'POST' or 'job_id' not in request.POST:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        job = Job.objects.get(pk=request.POST['job_id'])
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('The job was not found')})
    if job.children.count() > 0:
        return JsonResponse({'children': True})
    return JsonResponse({})


@login_required
@unparallel_group([])
def download_files_for_compet(request, job_id):
    if request.method != 'POST':
        return BridgeErrorResponse(301)
    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return BridgeErrorResponse(404)
    if not jobs.utils.JobAccess(request.user, job).can_dfc():
        return BridgeErrorResponse(400)

    generator = FilesForCompetitionArchive(job, json.loads(request.POST['filters']))
    mimetype = mimetypes.guess_type(os.path.basename(generator.name))[0]
    response = StreamingHttpResponse(generator, content_type=mimetype)
    response["Content-Disposition"] = "attachment; filename=%s" % generator.name
    return response


@login_required
@unparallel_group([Job])
def enable_safe_marks(request):
    if request.method != 'POST' or 'job_id' not in request.POST:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        job = Job.objects.get(id=request.POST['job_id'])
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('The job was not found')})
    if not jobs.utils.JobAccess(request.user, job).can_edit():
        return JsonResponse({'error': _("You don't have an access to edit this job")})
    job.safe_marks = not job.safe_marks
    job.save()
    try:
        root = ReportRoot.objects.get(job=job)
    except ObjectDoesNotExist:
        pass
    else:
        if job.safe_marks:
            SafeUtils.RecalculateConnections([root])
        else:
            SafeUtils.disable_safe_marks_for_job(root)
    return JsonResponse({})


@login_required
@unparallel_group([Job])
def upload_reports(request):
    if request.method != 'POST' or 'job_id' not in request.POST or 'archive' not in request.FILES:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    try:
        reports_dir = extract_archive(request.FILES['archive'])
    except Exception as e:
        logger.exception("Archive extraction failed: %s" % e, stack_info=True)
        return JsonResponse({'error': _('Extraction of the archive has failed')})
    try:
        job = Job.objects.get(id=request.POST['job_id'])
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('The job was not found')})

    if not jobs.utils.JobAccess(request.user, job).can_decide():
        return JsonResponse({'error': _("You don't have an access to upload reports for this job")})
    try:
        UploadReportsWithoutDecision(job, request.user, reports_dir.name)
    except BridgeException as e:
        return JsonResponse({'error': str(e)})
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    return JsonResponse({})
