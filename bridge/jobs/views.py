import os
import json
import mimetypes
from io import BytesIO
from urllib.parse import quote
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.loader import get_template
from django.utils.translation import ugettext as _, activate
from django.utils.timezone import pytz
from bridge.vars import VIEW_TYPES, PRIORITY
from bridge.utils import unparallel, unparallel_group, print_exec_time
from jobs.forms import FileForm
from jobs.ViewJobData import ViewJobData
from jobs.JobTableProperties import FilterForm, TableTree
from users.models import View, PreferableView
from reports.UploadReport import UploadReport
from reports.models import ReportComponent
from reports.comparison import can_compare
from jobs.Download import UploadJob, DownloadJob, KleverCoreDownloadJob
from jobs.utils import *
from service.utils import StartJobDecision, StartDecisionData, StopDecision, get_default_data


@login_required
def tree_view(request):
    activate(request.user.extended.language)

    tree_args = [request.user]
    if request.method == 'POST':
        tree_args.append(request.POST.get('view', None))
        tree_args.append(request.POST.get('view_id', None))

    return render(request, 'jobs/tree.html', {
        'FF': FilterForm(*tree_args),
        'users': User.objects.all(),
        'statuses': JOB_STATUS,
        'priorities': reversed(PRIORITY),
        'can_create': JobAccess(request.user).can_create(),
        'TableData': TableTree(*tree_args)
    })


@unparallel_group(['view'])
@login_required
def preferable_view(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': "Unknown error"})

    view_id = request.POST.get('view_id', None)
    view_type = request.POST.get('view_type', None)
    if view_id is None or view_type is None:
        return JsonResponse({'error': "Unknown error"})

    if view_id == 'default':
        pref_views = request.user.preferableview_set.filter(
            view__type=view_type)
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


@unparallel_group(['view'])
@login_required
def check_view_name(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})

    view_name = request.POST.get('view_title', None)
    view_type = request.POST.get('view_type', None)
    if view_name is None or view_type is None:
        return JsonResponse({'error': 'Unknown error'})

    if view_name == _('Default'):
        return JsonResponse({'error': _("Please choose another view name")})

    if view_name == '':
        return JsonResponse({'error': _("The view name is required")})

    if len(request.user.view_set.filter(type=view_type, name=view_name)):
        return JsonResponse({'error': _("Please choose another view name")})
    return JsonResponse({})


@unparallel_group(['view'])
@login_required
def save_view(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})

    view_data = request.POST.get('view', None)
    view_name = request.POST.get('title', '')
    view_id = request.POST.get('view_id', None)
    view_type = request.POST.get('view_type', None)
    if view_data is None or view_type is None or \
            view_type not in list(x[0] for x in VIEW_TYPES):
        return JsonResponse({'error': 'Unknown error'})
    if view_id == 'default':
        return JsonResponse({'error': _("You can't edit the default view")})
    elif view_id is not None:
        try:
            new_view = request.user.view_set.get(pk=int(view_id))
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('The view was not found')})
    elif len(view_name):
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


@unparallel_group(['view'])
@login_required
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
        View.objects.get(
            author=request.user, pk=int(v_id), type=view_type
        ).delete()
    except ObjectDoesNotExist:
        return JsonResponse({'error': _("The view was not found")})
    return JsonResponse({'message': _("The view was successfully removed")})


@login_required
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
    for child in job.children.all():
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

    return render(
        request,
        'jobs/viewJob.html',
        {
            'job': job,
            'last_version': job.versions.get(version=job.version),
            'parents': parents,
            'children': children,
            'reportdata': ViewJobData(*view_args),
            'created_by': job.versions.get(version=1).change_author,
            'can_delete': job_access.can_delete(),
            'can_edit': job_access.can_edit(),
            'can_create': job_access.can_create(),
            'can_decide': job_access.can_decide(),
            'can_download': job_access.can_download(),
            'can_stop': job_access.can_stop()
        }
    )


@login_required
def get_job_data(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    if 'job_id' not in request.POST:
        return JsonResponse({'error': 'Unknown error'})
    try:
        job = Job.objects.get(pk=int(request.POST['job_id']))
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Unknown error'})
    job_access = JobAccess(request.user, job)
    try:
        report = ReportComponent.objects.get(root__job=job, parent=None)
    except ObjectDoesNotExist:
        report = None
    except ValueError:
        return JsonResponse({'error': 'Unknown error'})

    data = {
        'can_delete': job_access.can_delete(),
        'can_edit': job_access.can_edit(),
        'can_create': job_access.can_create(),
        'can_decide': job_access.can_decide(),
        'can_download': job_access.can_download(),
        'can_stop': job_access.can_stop(),
        'jobstatus': job.status,
        'jobstatus_text': job.get_status_display() + ''
    }
    if report is not None:
        data['jobstatus_href'] = reverse('reports:component', args=[job.pk, report.pk])
        data['jobdata'] = get_template('jobs/jobData.html').render({
            'reportdata': ViewJobData(request.user, report, view=request.POST.get('view', None))
        })
    return JsonResponse(data)


@login_required
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
            job_time = j.change_date.astimezone(
                pytz.timezone(request.user.extended.timezone)
            )
            title = job_time.strftime("%d.%m.%Y %H:%M:%S")
            title += " (%s %s)" % (
                j.change_author.extended.last_name,
                j.change_author.extended.first_name,
            )
            title += ': ' + j.comment
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


@unparallel
@login_required
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
    for j in job.versions.filter(
            ~Q(version__in=[job.version, 1])).order_by('-version'):
        job_time = j.change_date.astimezone(
            pytz.timezone(request.user.extended.timezone)
        )
        title = job_time.strftime("%d.%m.%Y %H:%M:%S")
        title += " (%s %s)" % (
            j.change_author.extended.last_name,
            j.change_author.extended.first_name,
        )
        title += ': ' + j.comment
        job_versions.append({
            'version': j.version,
            'title': title
        })
    return render(request, 'jobs/viewVersions.html', {'versions': job_versions})


@login_required
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
        roles['available_users'].append({
            'id': u.pk,
            'name': u.extended.last_name + ' ' + u.extended.first_name
        })

    job = get_object_or_404(Job, pk=int(request.POST.get('parent_id', 0)))
    job_version = job.versions.order_by('-change_date')[0]

    return render(request, 'jobs/createJob.html', {
        'parent_id': job.identifier,
        'job': job_version,
        'roles': roles,
        'job_roles': JOB_ROLES,
        'filedata': FileData(job_version).filedata
    })


@unparallel_group(['job'])
@login_required
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
            parents = Job.objects.filter(
                identifier__startswith=parent_identifier
            )
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
        job_kwargs['absolute_url'] = 'http://' + request.get_host() + \
                                     reverse('jobs:job', args=[job_id])
        updated_job = update_job(job_kwargs)
        if isinstance(updated_job, Job):
            return JsonResponse({'job_id': job.pk})
        else:
            return JsonResponse({'error': updated_job + ''})
    elif parent_identifier is not None:
        try:
            parent = Job.objects.get(identifier=parent_identifier)
        except ObjectDoesNotExist:
            return JsonResponse({'error': _('The job parent was not found')})
        if not JobAccess(request.user).can_create():
            return JsonResponse({'error': _("You don't have an access to create new jobs")})
        job_kwargs['parent'] = parent
        job_kwargs['absolute_url'] = 'http://' + request.get_host()
        newjob = create_job(job_kwargs)
        if isinstance(newjob, Job):
            return JsonResponse({'job_id': newjob.pk})
        return JsonResponse({'error': newjob + ''})
    return JsonResponse({'error': 'Unknown error'})


@unparallel_group(['job'])
@login_required
def remove_jobs(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    jobs_for_del = json.loads(request.POST.get('jobs', '[]'))
    status = remove_jobs_by_id(request.user, jobs_for_del)
    if status == 404:
        if len(jobs_for_del) == 1:
            return JsonResponse({'error': _('The job was not found')})
        return JsonResponse({'error': _('One of the selected jobs was not found')})
    elif status == 400:
        if len(jobs_for_del) == 1:
            return JsonResponse({'error': _("You don't have an access to remove this job")})
        return JsonResponse({'error': _("You don't have an access to remove one of the selected jobs")})
    return JsonResponse({})


@login_required
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


@unparallel
@login_required
def upload_file(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponse('')
    form = FileForm(request.POST, request.FILES)
    if form.is_valid():
        new_file = form.save(commit=False)
        hash_sum = hashlib.md5(new_file.file.read()).hexdigest()
        if len(File.objects.filter(hash_sum=hash_sum)) > 0:
            return JsonResponse({
                'hash_sum': hash_sum,
                'status': 0
            })
        new_file.hash_sum = hash_sum
        if not all(ord(c) < 128 for c in new_file.file.name):
            title_size = len(new_file.file.name)
            if title_size > 30:
                new_file.file.name = new_file.file.name[(title_size - 30):]
        new_file.save()
        return JsonResponse({
            'hash_sum': hash_sum,
            'status': 0
        })
    return JsonResponse({
        'message': _('File uploading failed'),
        'errors': form.errors,
        'status': 1
    })


@login_required
def download_file(request, file_id):
    if request.method == 'POST':
        return HttpResponseRedirect(reverse('error', args=[500]))
    try:
        source = FileSystem.objects.get(pk=int(file_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[500]))
    if source.file is None:
        return HttpResponseRedirect(reverse('error', args=[500]))
    mimetype = mimetypes.guess_type(os.path.basename(source.file.file.name))[0]
    response = HttpResponse(source.file.file.read(), content_type=mimetype)
    response['Content-Disposition'] = 'attachment; filename=%s' % quote(source.name)
    return response


@unparallel_group(['job'])
@login_required
def download_job(request, job_id):
    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[404]))
    if not JobAccess(request.user, job).can_download():
        return HttpResponseRedirect(reverse('error', args=[400]))
    jobtar = DownloadJob(job)
    if jobtar.error is not None:
        return HttpResponseRedirect(
            reverse('error', args=[500]) + "?back=%s" %
            quote(reverse('jobs:job', args=[job_id]))
        )
    response = HttpResponse(content_type="application/x-tar-gz")
    response["Content-Disposition"] = "attachment; filename=%s" % jobtar.tarname
    jobtar.memory.seek(0)
    response.write(jobtar.memory.read())
    return response


@unparallel_group(['job'])
@login_required
def download_jobs(request):
    if request.method != 'POST' or 'job_ids' not in request.POST:
        return HttpResponseRedirect(
            reverse('error', args=[500]) + "?back=%s" % quote(reverse('jobs:tree'))
        )
    import tarfile
    arch_mem = BytesIO()
    jobs_archive = tarfile.open(fileobj=arch_mem, mode='w:gz')
    for job in Job.objects.filter(pk__in=json.loads(request.POST['job_ids'])):
        if not JobAccess(request.user, job).can_download():
            return HttpResponseRedirect(reverse('error', args=[401]))
        jobtar = DownloadJob(job)
        if jobtar.error is not None:
            return HttpResponseRedirect(
                reverse('error', args=[500]) + "?back=%s" % quote(reverse('jobs:tree'))
            )
        jobtar.memory.seek(0)
        tarname = 'Job-%s.tar.gz' % job.identifier[:10]
        tinfo = tarfile.TarInfo(tarname)
        tinfo.size = jobtar.memory.getbuffer().nbytes
        jobs_archive.addfile(tinfo, jobtar.memory)
    jobs_archive.close()
    arch_mem.seek(0)
    response = HttpResponse(content_type="application/x-tar-gz")
    response["Content-Disposition"] = "attachment; filename=KleverJobs.tar.gz"
    response.write(arch_mem.read())
    return response


@login_required
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


@unparallel_group(['job'])
@login_required
@print_exec_time
def upload_job(request, parent_id=None):
    activate(request.user.extended.language)

    if len(parent_id) == 0:
        return JsonResponse({
            'status': False,
            'message': _("The parent identifier was not got")
        })
    parents = Job.objects.filter(identifier__startswith=parent_id)
    if len(parents) == 0:
        return JsonResponse({
            'status': False,
            'message': _("The parent with the specified "
                         "identifier was not found")
        })
    elif len(parents) > 1:
        return JsonResponse({
            'status': False,
            'message': _("Too many jobs starts with the specified identifier")
        })
    parent = parents[0]
    failed_jobs = []
    for f in request.FILES.getlist('file'):
        zipdata = UploadJob(parent, request.user, f)
        if zipdata.err_message is not None:
            failed_jobs.append([zipdata.err_message + '', f.name])
    if len(failed_jobs) > 0:
        return JsonResponse({
            'status': False,
            'messages': failed_jobs
        })
    return JsonResponse({'status': True})


@unparallel_group(['job', 'report'])
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
            'error': 'User "{0}" doesn\'t have access to decide job "{1}"'.format(
                request.user, job.identifier
            )
        })
    if job.status != JOB_STATUS[1][0]:
        return JsonResponse({'error': 'Only pending jobs can be decided'})

    jobtar = KleverCoreDownloadJob(job)
    if jobtar.error is not None:
        return JsonResponse({
            'error': "Couldn't prepare archive for the job '%s'" % job.identifier
        })
    job.status = JOB_STATUS[2][0]
    job.save()

    jobtar.memory.seek(0)
    err = UploadReport(job, json.loads(request.POST.get('report', '{}'))).error
    if err is not None:
        return JsonResponse({'error': err})

    response = HttpResponse(content_type="application/x-tar-gz")
    response["Content-Disposition"] = 'attachment; filename={0}'.format(jobtar.tarname)
    response.write(jobtar.memory.read())

    return response


@login_required
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


@unparallel
@login_required
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


@unparallel_group(['decision'])
@login_required
def run_decision(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'status': False, 'error': 'Unknown error'})
    if 'data' not in request.POST:
        return JsonResponse({'status': False, 'error': 'Unknown error'})
    result = StartJobDecision(request.user, request.POST['data'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


@login_required
def prepare_decision(request, job_id):
    activate(request.user.extended.language)
    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[404]))
    return render(request, 'jobs/startDecision.html', {
        'job': job,
        'data': StartDecisionData(request.user)
    })


@unparallel_group(['decision'])
@login_required
def fast_run_decision(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    try:
        job_id = Job.objects.get(pk=int(request.POST.get('job_id', 0))).pk
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Unknown error'})
    data = {'job_id': job_id}
    data.update(get_default_data())
    result = StartJobDecision(request.user, json.dumps(data))
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


@login_required
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
        return JsonResponse({'error': _("You can't compare selected jobs.")})
    return JsonResponse({})
