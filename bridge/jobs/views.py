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

import mimetypes
from datetime import datetime
from urllib.parse import quote
from difflib import unified_diff
from wsgiref.util import FileWrapper
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.template import loader
from django.utils.translation import ugettext as _, activate
from django.utils.timezone import pytz
from bridge.vars import VIEW_TYPES
from bridge.utils import file_get_or_create, extract_archive
from tools.profiling import unparallel_group
from jobs.ViewJobData import ViewJobData
from jobs.JobTableProperties import FilterForm, TableTree
from users.models import View, PreferableView
from reports.UploadReport import UploadReport, CollapseReports
from reports.comparison import can_compare
from reports.utils import FilesForCompetitionArchive
from jobs.Download import UploadJob, JobArchiveGenerator, KleverCoreArchiveGen, JobsArchivesGen
from jobs.utils import *
from jobs.models import RunHistory
from service.utils import StartJobDecision, StopDecision


@login_required
@unparallel_group(['Job'])
def tree_view(request):
    activate(request.user.extended.language)

    tree_args = [request.user]
    if request.method == 'POST':
        tree_args.append(request.POST.get('view', None))
        tree_args.append(request.POST.get('view_id', None))
    months_choices = []
    for i in range(1, 13):
        months_choices.append((i, datetime(2016, i, 1).strftime('%B')))
    curr_year = datetime.now().year

    return render(request, 'jobs/tree.html', {
        'FF': FilterForm(*tree_args),
        'users': User.objects.all(),
        'statuses': JOB_STATUS,
        'priorities': list(reversed(PRIORITY)),
        'months': months_choices,
        'years': list(range(curr_year - 3, curr_year + 1)),
        'TableData': TableTree(*tree_args)
    })


@login_required
@unparallel_group([PreferableView, 'View'])
def preferable_view(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': "Unknown error"})

    view_id = request.POST.get('view_id', None)
    view_type = request.POST.get('view_type', None)
    if view_id is None or view_type is None or view_type not in list(x[0] for x in VIEW_TYPES):
        return JsonResponse({'error': "Unknown error"})

    if view_id == 'default':
        pref_views = request.user.preferableview_set.filter(view__type=view_type)
        if len(pref_views):
            pref_views.delete()
            return JsonResponse({'message': _("The default view was made preferred")})
        return JsonResponse({'error': _("The default view is already preferred")})

    try:
        user_view = View.objects.get(pk=int(view_id), author=request.user, type=view_type)
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
        return JsonResponse({'error': 'Unknown error'})

    view_name = request.POST.get('view_title', None)
    view_type = request.POST.get('view_type', None)
    if view_name is None or view_type is None:
        return JsonResponse({'error': 'Unknown error'})

    if view_name == '':
        return JsonResponse({'error': _("The view name is required")})

    if view_name == _('Default') or len(request.user.view_set.filter(type=view_type, name=view_name)):
        return JsonResponse({'error': _("Please choose another view name")})
    return JsonResponse({})


@login_required
@unparallel_group([View])
def save_view(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})

    view_data = request.POST.get('view', None)
    view_name = request.POST.get('title', '')
    view_id = request.POST.get('view_id', None)
    view_type = request.POST.get('view_type', None)
    if view_data is None or view_type is None or view_type not in list(x[0] for x in VIEW_TYPES):
        return JsonResponse({'error': 'Unknown error'})
    if view_id == 'default':
        return JsonResponse({'error': _("You can't edit the default view")})
    elif view_id is not None:
        try:
            new_view = request.user.view_set.get(pk=int(view_id))
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('The view was not found')})
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
        'view_id': new_view.pk,
        'view_name': new_view.name,
        'message': _("The view was successfully saved")
    })


@login_required
@unparallel_group([View])
def remove_view(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    v_id = request.POST.get('view_id', 0)
    view_type = request.POST.get('view_type', None)
    if view_type is None:
        return JsonResponse({'error': 'Unknown error'})
    if v_id == 'default':
        return JsonResponse({'error': _("You can't remove the default view")})
    try:
        View.objects.get(author=request.user, pk=int(v_id), type=view_type).delete()
    except ObjectDoesNotExist:
        return JsonResponse({'error': _("The view was not found")})
    return JsonResponse({'message': _("The view was successfully removed")})


@login_required
@unparallel_group(['Job'])
def show_job(request, job_id=None):
    activate(request.user.extended.language)

    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[404]))

    job_access = JobAccess(request.user, job)
    if not job_access.can_view():
        return HttpResponseRedirect(reverse('error', args=[400]))

    parent_set = []
    next_parent = job.parent
    while next_parent is not None:
        parent_set.append(next_parent)
        next_parent = next_parent.parent
    parent_set.reverse()
    parents = []
    for parent in parent_set:
        if JobAccess(request.user, parent).can_view():
            job_id = parent.pk
        else:
            job_id = None
        parents.append({
            'pk': job_id,
            'name': parent.name,
        })

    children = []
    for child in job.children.all().order_by('change_date'):
        if JobAccess(request.user, child).can_view():
            job_id = child.pk
        else:
            job_id = None
        children.append({
            'pk': job_id,
            'name': child.name,
        })

    view_args = [request.user]
    try:
        report = ReportComponent.objects.get(root__job=job, parent=None)
    except ObjectDoesNotExist:
        report = None
    view_args.append(report)
    if request.method == 'POST':
        view_args.append(request.POST.get('view', None))
        view_args.append(request.POST.get('view_id', None))

    progress_data = get_job_progress(request.user, job) if job.status in [JOB_STATUS[1][0], JOB_STATUS[2][0]] else None
    return render(
        request,
        'jobs/viewJob.html',
        {
            'job': job,
            'last_version': job.versions.get(version=job.version),
            'parents': parents,
            'children': children,
            'progress_data': progress_data,
            'reportdata': ViewJobData(*view_args),
            'created_by': job.versions.get(version=1).change_author,
            'can_delete': job_access.can_delete(),
            'can_edit': job_access.can_edit(),
            'can_create': job_access.can_create(),
            'can_decide': job_access.can_decide(),
            'can_download': job_access.can_download(),
            'can_stop': job_access.can_stop(),
            'can_collapse': job_access.can_collapse(),
            'can_dfc': job_access.can_dfc()
        }
    )


@login_required
@unparallel_group(['Job', 'Report'])
def get_job_data(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    try:
        job = Job.objects.get(pk=request.POST.get('job_id', 0))
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Unknown error'})

    data = {'jobstatus': job.status}
    try:
        data['jobdata'] = loader.get_template('jobs/jobData.html').render({
            'reportdata': ViewJobData(
                request.user,
                ReportComponent.objects.get(root__job=job, parent=None),
                view=request.POST.get('view', None)
            )
        })
    except ObjectDoesNotExist:
        pass
    if job.status in [JOB_STATUS[1][0], JOB_STATUS[2][0]]:
        data['progress_data'] = json.dumps(list(get_job_progress(request.user, job)))
    return JsonResponse(data)


@login_required
@unparallel_group([Job])
def edit_job(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponse('')

    job_id = request.POST.get('job_id', 0)

    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponse('')
    if not JobAccess(request.user, job).can_edit():
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
        'roles': role_info(job_version, request.user),
        'job_roles': JOB_ROLES,
        'job_versions': job_versions,
        'version': version,
        'filedata': FileData(job_version).filedata
    })


@login_required
@unparallel_group(['Job', JobHistory])
def remove_versions(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    job_id = int(request.POST.get('job_id', 0))
    try:
        job = Job.objects.get(pk=job_id)
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('The job was not found')})
    if not JobAccess(request.user, job).can_edit():
        return JsonResponse({'error': _("You don't have access to delete versions")})

    versions = json.loads(request.POST.get('versions', '[]'))

    deleted_versions = delete_versions(job, versions)
    if deleted_versions > 0:
        return JsonResponse({'message': _('Selected versions were successfully deleted')})
    return JsonResponse({'error': _('Nothing to delete')})


@login_required
@unparallel_group(['Job', 'JobHistory'])
def get_job_versions(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'message': 'Unknown error'})
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
        job_versions.append({
            'version': j.version,
            'title': title
        })
    return render(request, 'jobs/viewVersions.html', {'versions': job_versions})


@login_required
@unparallel_group(['Job'])
def copy_new_job(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponse('')
    if not JobAccess(request.user).can_create():
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
        'job_roles': JOB_ROLES,
        'filedata': FileData(job_version).filedata
    })


@login_required
@unparallel_group([Job])
def save_job(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})

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
        if not JobAccess(request.user, job).can_edit():
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
            if not check_new_parent(job, parent):
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
            update_job(job_kwargs)
        except Exception as e:
            logger.exception(str(e), stack_info=True)
            return JsonResponse({'error': _('Updating the job failed')})
        return JsonResponse({'job_id': job.pk})
    elif parent_identifier is not None:
        try:
            parent = Job.objects.get(identifier=parent_identifier)
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('The job parent was not found')})
        if not JobAccess(request.user).can_create():
            return JsonResponse({'error': _("You don't have an access to create new jobs")})
        job_kwargs['parent'] = parent
        job_kwargs['absolute_url'] = 'http://' + request.get_host()
        try:
            newjob = create_job(job_kwargs)
        except Exception as e:
            logger.exception(str(e), stack_info=True)
            return JsonResponse({'error': _('Saving the job failed')})
        if isinstance(newjob, Job):
            return JsonResponse({'job_id': newjob.pk})
        return JsonResponse({'error': newjob + ''})
    return JsonResponse({'error': 'Unknown error'})


@login_required
@unparallel_group([Job])
def remove_jobs(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    jobs_for_del = json.loads(request.POST.get('jobs', '[]'))
    remove_jobs_by_id(request.user, jobs_for_del)
    return JsonResponse({})


@login_required
@unparallel_group(['Job'])
def showjobdata(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponse('')
    try:
        job = Job.objects.get(pk=int(request.POST.get('job_id', 0)))
    except ObjectDoesNotExist:
        return HttpResponse('')

    return render(request, 'jobs/showJob.html', {
        'job': job,
        'description': job.versions.get(version=job.version).description,
        'filedata': FileData(job.versions.get(version=job.version)).filedata
    })


@login_required
@unparallel_group(['JobFile'])
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
    return JsonResponse({'error': 'Unknown error'})


@login_required
@unparallel_group(['FileSystem', 'JobFile'])
def download_file(request, file_id):
    if request.method == 'POST':
        return HttpResponseRedirect(reverse('error', args=[500]))
    try:
        source = FileSystem.objects.get(pk=int(file_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[500]))
    if source.file is None:
        return HttpResponseRedirect(reverse('error', args=[500]))

    mimetype = mimetypes.guess_type(os.path.basename(source.name))[0]
    response = StreamingHttpResponse(FileWrapper(source.file.file, 8192), content_type=mimetype)
    response['Content-Length'] = len(source.file.file)
    response['Content-Disposition'] = "attachment; filename=%s" % quote(source.name)
    return response


@login_required
@unparallel_group(['Job'])
def download_job(request, job_id):
    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[404]))
    if not JobAccess(request.user, job).can_download():
        return HttpResponseRedirect(reverse('error', args=[400]))

    generator = JobArchiveGenerator(job)
    mimetype = mimetypes.guess_type(os.path.basename(generator.arcname))[0]
    response = StreamingHttpResponse(generator, content_type=mimetype)
    response["Content-Disposition"] = "attachment; filename=%s" % generator.arcname
    return response


@login_required
@unparallel_group(['Job'])
def download_jobs(request):
    if request.method != 'POST' or 'job_ids' not in request.POST:
        return HttpResponseRedirect(
            reverse('error', args=[500]) + "?back=%s" % quote(reverse('jobs:tree'))
        )
    jobs = Job.objects.filter(pk__in=json.loads(request.POST['job_ids']))
    for job in jobs:
        if not JobAccess(request.user, job).can_download():
            return HttpResponseRedirect(
                reverse('error', args=[401]) + "?back=%s" % quote(reverse('jobs:tree'))
            )
    generator = JobsArchivesGen(jobs)

    mimetype = mimetypes.guess_type(os.path.basename('KleverJobs.zip'))[0]
    response = StreamingHttpResponse(generator, content_type=mimetype)
    response["Content-Disposition"] = "attachment; filename=KleverJobs.zip"
    return response


@login_required
@unparallel_group(['Job'])
def check_access(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    jobs = json.loads(request.POST.get('jobs', '[]'))
    for job_id in jobs:
        try:
            job = Job.objects.get(pk=int(job_id))
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('One of the selected jobs was not found')})
        if not JobAccess(request.user, job).can_download():
            return JsonResponse({'error': _("You don't have an access to download one of the selected jobs")})
    return JsonResponse({})


@login_required
@unparallel_group([Job])
def upload_job(request, parent_id=None):
    activate(request.user.extended.language)

    if len(parent_id) == 0:
        return JsonResponse({'error': str(_("The parent identifier was not got"))})
    parents = Job.objects.filter(identifier__startswith=parent_id)
    if len(parents) == 0:
        return JsonResponse({'error': str(_("The parent with the specified identifier was not found"))})
    elif len(parents) > 1:
        return JsonResponse({'error': str(_("Too many jobs starts with the specified identifier"))})
    parent = parents[0]
    errors = []
    for f in request.FILES.getlist('file'):
        try:
            job_dir = extract_archive(f)
        except Exception as e:
            logger.exception("Archive extraction failed: %s" % e, stack_info=True)
            errors.append(_('Extraction of the archive "%(arcname)s" has failed') % {'arcname': f.name})
            continue
        # TODO: ensure that tempdir is deleted after job is uploaded (on Linux)
        zipdata = UploadJob(parent, request.user, job_dir.name)
        if zipdata.err_message is not None:
            errors.append(
                _('Creating the job from archive "%(arcname)s" failed: %(message)s') % {
                    'arcname': f.name,
                    'message': str(zipdata.err_message)
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

    if not JobAccess(request.user, job).klever_core_access():
        return JsonResponse({
            'error': 'User "{0}" doesn\'t have access to decide job "{1}"'.format(request.user, job.identifier)
        })
    if job.status != JOB_STATUS[1][0]:
        return JsonResponse({'error': 'Only pending jobs can be decided'})

    change_job_status(job, JOB_STATUS[2][0])
    err = UploadReport(job, json.loads(request.POST.get('report', '{}'))).error
    if err is not None:
        return JsonResponse({'error': err})

    generator = KleverCoreArchiveGen(job)
    mimetype = mimetypes.guess_type(os.path.basename(generator.arcname))[0]
    response = StreamingHttpResponse(generator, content_type=mimetype)
    response["Content-Disposition"] = "attachment; filename=%s" % generator.arcname
    return response


@login_required
@unparallel_group(['FileSystem', 'JobFile'])
def getfilecontent(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'message': "Unknown error"})
    try:
        file_id = int(request.POST.get('file_id', 0))
    except ValueError:
        return JsonResponse({'message': "Unknown error"})
    try:
        source = FileSystem.objects.get(pk=int(file_id))
    except ObjectDoesNotExist:
        return JsonResponse({'message': _("The file was not found")})
    return HttpResponse(source.file.file.read())


@login_required
@unparallel_group([Job])
def stop_decision(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': "Unknown error"})
    try:
        job = Job.objects.get(pk=int(request.POST.get('job_id', 0)))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _("The job was not found")})
    if not JobAccess(request.user, job).can_stop():
        return JsonResponse({'error': _("You don't have an access to stop decision of this job")})
    result = StopDecision(job)
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


@login_required
@unparallel_group([Job])
def run_decision(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    if any(x not in request.POST for x in ['data', 'job_id']):
        return JsonResponse({'error': 'Unknown error'})
    try:
        configuration = GetConfiguration(user_conf=json.loads(request.POST['data'])).configuration
    except ValueError:
        return JsonResponse({'error': 'Unknown error'})
    if configuration is None:
        return JsonResponse({'error': 'Unknown error'})
    result = StartJobDecision(request.user, request.POST['job_id'], configuration)
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


@login_required
@unparallel_group(['Job'])
def prepare_decision(request, job_id):
    activate(request.user.extended.language)
    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[404]))
    if request.method == 'POST' and 'conf_name' in request.POST:
        current_conf = request.POST['conf_name']
        if request.POST['conf_name'] == 'file_conf':
            if 'file_conf' not in request.FILES:
                return HttpResponseRedirect(reverse('error', args=[500]))
            try:
                configuration = GetConfiguration(
                    file_conf=json.loads(request.FILES['file_conf'].read().decode('utf8'))
                ).configuration
            except Exception as e:
                logger.exception(e, stack_info=True)
                return HttpResponseRedirect(reverse('error', args=[500]))
        else:
            configuration = GetConfiguration(conf_name=request.POST['conf_name']).configuration
    else:
        configuration = GetConfiguration(conf_name=DEF_KLEVER_CORE_MODE).configuration
        current_conf = DEF_KLEVER_CORE_MODE
    if configuration is None:
        return HttpResponseRedirect(reverse('error', args=[500]))
    return render(request, 'jobs/startDecision.html', {
        'job': job,
        'data': StartDecisionData(request.user, configuration),
        'configurations': get_default_configurations(),
        'current_conf': current_conf
    })


@login_required
@unparallel_group([Job])
def fast_run_decision(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    if 'job_id' not in request.POST:
        return JsonResponse({'error': 'Unknown error'})
    configuration = GetConfiguration(conf_name=DEF_KLEVER_CORE_MODE).configuration
    if configuration is None:
        return JsonResponse({'error': 'Unknown error'})
    result = StartJobDecision(request.user, request.POST['job_id'], configuration)
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


@login_required
@unparallel_group([Job])
def lastconf_run_decision(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    if 'job_id' not in request.POST:
        return JsonResponse({'error': 'Unknown error'})
    last_run = RunHistory.objects.filter(job_id=request.POST['job_id']).order_by('date').last()
    if last_run is None:
        return JsonResponse({'error': _('The job was not decided before')})
    try:
        with last_run.configuration.file as fp:
            configuration = GetConfiguration(file_conf=json.loads(fp.read().decode('utf8'))).configuration
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': 'Unknown error'})
    if configuration is None:
        return JsonResponse({'error': 'Unknown error'})
    result = StartJobDecision(request.user, request.POST['job_id'], configuration)
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


@login_required
@unparallel_group(['Job'])
def check_compare_access(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    try:
        j1 = Job.objects.get(pk=request.POST.get('job1', 0))
        j2 = Job.objects.get(pk=request.POST.get('job2', 0))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('One of the selected jobs was not found, please reload page')})
    if not can_compare(request.user, j1, j2):
        return JsonResponse({'error': _("You can't compare the selected jobs")})
    return JsonResponse({})


@login_required
@unparallel_group(['Job', 'JobFile'])
def jobs_files_comparison(request, job1_id, job2_id):
    activate(request.user.extended.language)
    try:
        job1 = Job.objects.get(pk=job1_id)
        job2 = Job.objects.get(pk=job2_id)
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[405]))
    if not can_compare(request.user, job1, job2):
        return HttpResponseRedirect(reverse('error', args=[507]))
    res = GetFilesComparison(request.user, job1, job2)
    return render(request, 'jobs/comparison.html', {
        'job1': job1,
        'job2': job2,
        'data': res.data
    })


@login_required
@unparallel_group(['JobFile'])
def get_file_by_checksum(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    try:
        check_sums = json.loads(request.POST['check_sums'])
    except Exception as e:
        logger.exception("Json parsing failed: %s" % e, stack_info=True)
        return JsonResponse({'error': 'Unknown error'})
    if len(check_sums) == 1:
        try:
            f = JobFile.objects.get(hash_sum=check_sums[0])
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('The file was not found') + ''})
        return HttpResponse(f.file.read())
    elif len(check_sums) == 2:
        try:
            f1 = JobFile.objects.get(hash_sum=check_sums[0])
            f2 = JobFile.objects.get(hash_sum=check_sums[1])
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('The file was not found') + ''})
        diff_result = []
        with f1.file as fp1, f2.file as fp2:
            for line in unified_diff(
                fp1.read().decode('utf8').split('\n'), fp2.read().decode('utf8').split('\n'),
                fromfile=request.POST.get('job1_name', ''), tofile=request.POST.get('job2_name', '')
            ):
                diff_result.append(line)
        return HttpResponse('\n'.join(diff_result))
    return JsonResponse({'error': 'Unknown error'})


@unparallel_group(['RunHistory'])
def download_configuration(request, runhistory_id):
    try:
        run_history = RunHistory.objects.get(id=runhistory_id)
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[500]))

    file_name = "job-%s.conf" % run_history.job.identifier[:5]
    mimetype = mimetypes.guess_type(file_name)[0]
    response = StreamingHttpResponse(FileWrapper(run_history.configuration.file, 8192), content_type=mimetype)
    response['Content-Length'] = len(run_history.configuration.file)
    response['Content-Disposition'] = "attachment; filename=%s" % quote(file_name)
    return response


def get_def_start_job_val(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    if 'name' not in request.POST or 'value' not in request.POST:
        return JsonResponse({'error': 'Unknown error'})
    if request.POST['name'] == 'formatter' and request.POST['value'] in KLEVER_CORE_LOG_FORMATTERS:
        return JsonResponse({'value': KLEVER_CORE_LOG_FORMATTERS[request.POST['value']]})
    if request.POST['name'] == 'sub_jobs_proc_parallelism' and request.POST['value'] in KLEVER_CORE_PARALLELISM_PACKS:
        return JsonResponse({
            'value': Template('{% load l10n %}{{ val|localize }}').render(Context({
                'val': KLEVER_CORE_PARALLELISM_PACKS[request.POST['value']][0]
            }))
        })
    if request.POST['name'] == 'build_parallelism' and request.POST['value'] in KLEVER_CORE_PARALLELISM_PACKS:
        return JsonResponse({
            'value': Template('{% load l10n %}{{ val|localize }}').render(Context({
                'val': KLEVER_CORE_PARALLELISM_PACKS[request.POST['value']][1]
            }))
        })
    if request.POST['name'] == 'tasks_gen_parallelism' and request.POST['value'] in KLEVER_CORE_PARALLELISM_PACKS:
        return JsonResponse({
            'value': Template('{% load l10n %}{{ val|localize }}').render(Context({
                'val': KLEVER_CORE_PARALLELISM_PACKS[request.POST['value']][2]
            }))
        })
    return JsonResponse({'error': 'Unknown error'})


@login_required
@unparallel_group([Job])
def collapse_reports(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    try:
        job = Job.objects.get(pk=request.POST.get('job_id', 0))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('The job was not found')})
    if not JobAccess(request.user, job).can_collapse():
        return JsonResponse({'error': _("You don't have an access to collapse reports")})
    CollapseReports(job)
    return JsonResponse({})


@login_required
@unparallel_group(['Job'])
def do_job_has_children(request):
    activate(request.user.extended.language)

    if request.method != 'POST' or 'job_id' not in request.POST:
        return JsonResponse({'error': 'Unknown error'})
    try:
        job = Job.objects.get(pk=request.POST['job_id'])
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('The job was not found')})
    if job.children.count() > 0:
        return JsonResponse({'children': True})
    return JsonResponse({})


@login_required
@unparallel_group(['Job'])
def download_files_for_compet(request, job_id):
    if request.method != 'POST':
        return HttpResponseRedirect(reverse('error', args=[500]))
    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[404]))
    if not JobAccess(request.user, job).can_download():
        return HttpResponseRedirect(reverse('error', args=[400]))
    if job.status in {x[0] for x in JOB_STATUS[:3]}:
        logger.error("Files for competition can't be downloaded for undecided jobs")
        return HttpResponseRedirect(reverse('error', args=[500]))

    generator = FilesForCompetitionArchive(job, json.loads(request.POST['filters']))
    mimetype = mimetypes.guess_type(os.path.basename(generator.name))[0]
    response = StreamingHttpResponse(generator, content_type=mimetype)
    response["Content-Disposition"] = "attachment; filename=%s" % generator.name
    return response
