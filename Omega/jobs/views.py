import os
import pytz
import json
import hashlib
import mimetypes
from io import BytesIO
from urllib.parse import quote, unquote
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils.translation import ugettext as _, activate
from Omega.vars import JOB_ROLES, JOB_STATUS
from jobs.job_model import Job
from jobs.models import File, FileSystem
from jobs.forms import FileForm
from jobs.JobTableProperties import FilterForm, TableTree
import jobs.job_functions as job_f
from users.models import View, PreferableView


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
        'can_create': job_f.JobAccess(request.user).can_create(),
        'TableData': TableTree(*tree_args)
    })


@login_required
def preferable_view(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _("Unknown error")})

    view_id = request.POST.get('view_id', None)
    if view_id is None:
        return JsonResponse({'status': 2, 'message': _("Unknown error")})

    if view_id == 'default':
        pref_views = request.user.preferableview_set.filter(view__type='1')
        if len(pref_views):
            pref_views.delete()
            return JsonResponse({
                'status': 0,
                'message': _("The default view was made preferred")
            })
        return JsonResponse({
            'status': 1,
            'message': _("The default view is already preferred")
        })

    try:
        user_view = View.objects.get(pk=int(view_id),
                                     author=request.user, type='1')
    except ObjectDoesNotExist:
        return JsonResponse({
            'status': 1,
            'message': _("The view was not found")
        })
    request.user.preferableview_set.filter(view__type='1').delete()
    pref_view = PreferableView()
    pref_view.user = request.user
    pref_view.view = user_view
    pref_view.save()
    return JsonResponse({
        'status': 0,
        'message': _("The preferred view was successfully changed")
    })


@login_required
def check_view_name(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'status': False, 'message': _('Unknown error')})

    view_name = request.POST.get('view_title', None)
    if view_name is None:
        return JsonResponse({'status': False, 'message': _('Unknown error')})

    if view_name == _('Default'):
        return JsonResponse({
            'status': False, 'message': _("Please choose another view name")
        })

    if view_name == '':
        return JsonResponse({
            'status': False, 'message': _("The view name is required")
        })

    if len(request.user.view_set.filter(type='1', name=view_name)):
        return JsonResponse({
            'status': False, 'message': _("Please choose another view name")
        })
    return JsonResponse({'status': True})


@login_required
def save_view(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _('Unknown error')})

    view_data = request.POST.get('view', None)
    view_name = request.POST.get('title', '')
    view_id = request.POST.get('view_id', None)
    if view_data is None:
        return JsonResponse({'status': 1, 'message': _('Unknown error')})
    if view_id == 'default':
        return JsonResponse({
            'status': 1,
            'message': _("You can't edit the default view")
        })
    elif view_id is not None:
        try:
            new_view = request.user.view_set.get(pk=int(view_id))
        except ObjectDoesNotExist:
            return JsonResponse({
                'status': 1,
                'message': _('The view was not found')
            })
    elif len(view_name):
        new_view = View()
        new_view.name = view_name
        new_view.type = '1'
        new_view.author = request.user
    else:
        return JsonResponse({'status': 1, 'message': _('Unknown error')})
    new_view.view = view_data
    new_view.save()
    return JsonResponse({
        'status': 0,
        'view_id': new_view.pk,
        'view_name': new_view.name,
        'message': _("The view was successfully saved")
    })


@login_required
def remove_view(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _("Unknown error")})
    v_id = request.POST.get('view_id', 0)
    if v_id == 'default':
        return JsonResponse({
            'status': 1,
            'message': _("You can't remove the default view")
        })
    try:
        View.objects.get(author=request.user, pk=int(v_id), type='1').delete()
    except ObjectDoesNotExist:
        return JsonResponse({
            'status': 1,
            'message': _("The view was not found")
        })
    return JsonResponse({
        'status': 0,
        'message': _("The view was successfully removed")
    })


@login_required
def show_job(request, job_id=None):
    activate(request.user.extended.language)

    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(
            reverse('jobs:error', args=[404]) + "?back=%s" % quote(
                reverse('jobs:tree')))

    job_access = job_f.JobAccess(request.user, job)
    if not job_access.can_view():
        return HttpResponseRedirect(
            reverse('jobs:error', args=[400]) + "?back=%s" % quote(
                reverse('jobs:tree')))

    parent_set = []
    next_parent = job.parent
    while next_parent is not None:
        parent_set.append(next_parent)
        next_parent = next_parent.parent
    parent_set.reverse()
    parents = []
    for parent in parent_set:
        if job_f.JobAccess(request.user, parent).can_view():
            job_id = parent.pk
        else:
            job_id = None
        parents.append({
            'pk': job_id,
            'name': parent.name,
        })

    children = []
    for child in job.children_set.all():
        if job_f.JobAccess(request.user, child).can_view():
            job_id = child.pk
        else:
            job_id = None
        children.append({
            'pk': job_id,
            'name': child.name,
        })

    return render(
        request,
        'jobs/viewJob.html',
        {
            'job': job,
            'comment': job.jobhistory_set.get(version=job.version).comment,
            'parents': parents,
            'children': children,
            'user_tz': request.user.extended.timezone,
            'verdict': job_f.verdict_info(job),
            'unknowns': job_f.unknowns_info(job),
            'resources': job_f.resource_info(job, request.user),
            'created_by': job.jobhistory_set.get(version=1).change_author,
            'can_delete': job_access.can_delete(),
            'can_edit': job_access.can_edit(),
            'can_create': job_access.can_create()
        }
    )


@login_required
def edit_job(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponse('')

    job_id = request.POST.get('job_id', 0)

    job = get_object_or_404(Job, pk=int(job_id))
    if not job_f.JobAccess(request.user, job).can_edit():
        return HttpResponse('')

    version = int(request.POST.get('version', 0))
    if version > 0:
        job_version = job.jobhistory_set.get(version=version)
    else:
        job_version = job.jobhistory_set.all().order_by('-change_date')[0]

    job_versions = []
    for j in job.jobhistory_set.all().order_by('-version'):
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
            version_comment = j.comment
            if len(version_comment) > 30:
                version_comment = version_comment[:27]
                version_comment += '...'
            if len(version_comment):
                title += ': ' + version_comment
        job_versions.append({
            'version': j.version,
            'title': title,
            'comment': j.comment,
        })

    parent_identifier = None
    if job_version.parent is not None:
        parent_identifier = job_version.parent.identifier

    return render(request, 'jobs/editJob.html', {
        'parent_id': parent_identifier,
        'job': job_version,
        'job_id': job_id,
        'roles': job_f.role_info(job_version, request.user),
        'job_roles': JOB_ROLES,
        'job_versions': job_versions,
        'version': version,
        'filedata': job_f.FileData(job_version).filedata
    })


@login_required
def create_job(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponse('')
    if not job_f.JobAccess(request.user).can_create():
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
    job_version = job.jobhistory_set.all().order_by('-change_date')[0]

    return render(request, 'jobs/createJob.html', {
        'parent_id': job.identifier,
        'job': job_version,
        'roles': roles,
        'job_roles': JOB_ROLES,
        'filedata': job_f.FileData(job_version).filedata
    })


@login_required
def save_job(request):
    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _('Unknown error')})

    job_kwargs = {
        'name': request.POST.get('title', ''),
        'description': request.POST.get('description', ''),
        'configuration': request.POST.get('configuration', ''),
        'global_role': request.POST.get('global_role', JOB_ROLES[0][0]),
        'user_roles': json.loads(request.POST.get('user_roles', '[]')),
        'filedata': json.loads(request.POST.get('file_data', '[]')),
        'author': request.user
    }
    job_id = request.POST.get('job_id', None)
    parent_identifier = request.POST.get('parent_identifier', None)

    if job_id:
        try:
            job = Job.objects.get(pk=int(job_id))
        except ObjectDoesNotExist:
            return JsonResponse({
                'status': 1,
                'message': _('The job was not found')
            })
        if not job_f.JobAccess(request.user, job).can_edit():
            return JsonResponse({
                'status': 1,
                'message': _("You don't have an access to edit this job")
            })
        if parent_identifier:
            parents = Job.objects.filter(
                identifier__startswith=parent_identifier
            )
            if len(parents) == 0:
                return JsonResponse({
                    'status': 1,
                    'message': _('The job parent was not found')
                })
            elif len(parents) > 1:
                return JsonResponse({
                    'status': 1,
                    'message': _('Several parents match the specified '
                                 'identifier, please increase the length '
                                 'of the parent identifier')
                })
            parent = parents[0]
            if job.parent is None:
                return JsonResponse({
                    'status': 1,
                    'message': _("Parent can't be specified for root jobs")
                })
            if not job_f.check_new_parent(job, parent):
                return JsonResponse({
                    'status': 1,
                    'message': _("The specified parent can't "
                                 "be set for this job")
                })
            job_kwargs['parent'] = parent
        elif job.parent:
            return JsonResponse({
                'status': 1,
                'message': _("A parent identifier is required for this job")
            })
        if job.version != int(request.POST.get('last_version', 0)):
            return JsonResponse({
                'status': 1,
                'message': _("Your version is expired, please reload the page")
            })
        job_kwargs['job'] = job
        job_kwargs['comment'] = request.POST.get('comment', '')
        updated_job = job_f.update_job(job_kwargs)
        if isinstance(updated_job, Job):
            return JsonResponse({'status': 0, 'job_id': job.pk})
        else:
            return JsonResponse({'status': 1, 'message': updated_job + ''})
    elif job_id is None and parent_identifier is not None:
        try:
            parent = Job.objects.get(identifier=parent_identifier)
        except ObjectDoesNotExist:
            return JsonResponse({
                'status': 1,
                'message': _('The job parent was not found')
            })
        if not job_f.JobAccess(request.user).can_create():
            return JsonResponse({
                'status': 1,
                'message': _("You don't have an access to create a new job")
            })
        job_kwargs['parent'] = parent
        newjob = job_f.create_job(job_kwargs)
        if isinstance(newjob, Job):
            return JsonResponse({'status': 0, 'job_id': newjob.pk})
        return JsonResponse({'status': 1, 'message': newjob + ''})
    return JsonResponse({'status': 1, 'message': _('Unknown error')})


@login_required
def remove_job(request):
    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _('Unknown error')})

    job_id = request.POST.get('job_id', None)
    status = job_f.remove_jobs_by_id(request.user, [job_id])
    if status == 404:
        return JsonResponse({
            'status': 1, 'message': _('The job was not found')
        })
    elif status == 400:
        return JsonResponse({
            'status': 1,
            'message': _("You don't have an access to remove this job")
        })
    return JsonResponse({'status': 0})


@login_required
def remove_jobs(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _('Unknown error')})
    status = job_f.remove_jobs_by_id(request.user,
                                     json.loads(request.POST.get('jobs', '[]')))
    if status == 404:
        return JsonResponse({
            'status': 1,
            'message': _('The job was not found')
        })
    elif status == 400:
        return JsonResponse({
            'status': 1,
            'message':
                _("You don't have an access to "
                  "remove one of the selected jobs")
        })
    return JsonResponse({'status': 0})


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
        'filedata': job_f.FileData(
            job.jobhistory_set.filter(version=job.version)[0]
        ).filedata
    })


@login_required
def upload_file(request):
    if request.method != 'POST':
        return HttpResponse('')
    form = FileForm(request.POST, request.FILES)
    if form.is_valid():
        new_file = form.save(commit=False)
        hash_sum = hashlib.md5(new_file.file.read()).hexdigest()
        if len(File.objects.filter(hash_sum=hash_sum)):
            return JsonResponse({
                'hash_sum': hash_sum,
                'status': 0
            })
        new_file.hash_sum = hash_sum
        new_file.save()
        return JsonResponse({
            'hash_sum': hash_sum,
            'status': 0
        })
    return JsonResponse({
        'message': _('File uploading failed'),
        'form_errors': form.errors,
        'status': 1
    })


@login_required
def download_file(request, file_id):
    if request.method == 'POST':
        return HttpResponse('')
    try:
        source = FileSystem.objects.get(pk=int(file_id))
    except ObjectDoesNotExist:
        return HttpResponse('')
    if source.file is None:
        return HttpResponse('')
    new_file = BytesIO(source.file.file.read())
    mimetype = mimetypes.guess_type(os.path.basename(source.file.file.name))[0]
    response = HttpResponse(new_file.read(), content_type=mimetype)
    response['Content-Disposition'] = 'attachment; filename="%s"' % \
                                      quote(source.name)
    return response


@login_required
def download_job(request, job_id):
    if request.method == 'POST':
        return HttpResponse('')
    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        back_url = quote(reverse('jobs:tree'))
        return HttpResponseRedirect(
            reverse('jobs:error', args=[404]) + "?back=%s" % back_url
        )
    if not job_f.JobAccess(request.user, job).can_view():
        back_url = quote(reverse('jobs:tree'))
        return HttpResponseRedirect(
            reverse('jobs:error', args=[400]) + "?back=%s" % back_url
        )
    back_url = quote(reverse('jobs:job', args=[job_id]))
    hash_sum = request.GET.get('hashsum', None)
    if hash_sum is None:
        return HttpResponseRedirect(
            reverse('jobs:error', args=[451]) + "?back=%s" % back_url
        )
    job_tar = job_f.JobArchive(job=job, hash_sum=hash_sum)

    if not job_tar.create_tar():
        return HttpResponseRedirect(
            reverse('jobs:error', args=[500]) + "?back=%s" % back_url
        )
    response = HttpResponse(content_type="application/x-tar-gz")
    zipname = job_tar.jobtar_name
    response["Content-Disposition"] = "attachment; filename=%s" % quote(zipname)
    job_tar.memory.seek(0)
    response.write(job_tar.memory.read())
    return response


@login_required
def download_lock(request):
    ziplock = job_f.JobArchive(user=request.user)
    status = ziplock.first_lock()
    response_data = {'status': status}
    if status:
        response_data['hash_sum'] = ziplock.hash_sum
    return JsonResponse(response_data)


@login_required
def check_access(request):
    if request.method == 'POST':
        jobs = json.loads(request.POST.get('jobs', '[]'))
        for job_id in jobs:
            try:
                job = Job.objects.get(pk=int(job_id))
            except ObjectDoesNotExist:
                return JsonResponse({
                    'status': False,
                    'message': _('The job was not found')
                })
            if not job_f.JobAccess(request.user, job).can_view():
                return JsonResponse({
                    'status': False,
                    'message': _("You don't have an access to this job")
                })
        return JsonResponse({
            'status': True,
            'message': ''
        })


@login_required
def upload_job(request, parent_id=None):
    if len(parent_id) > 0:
        parents = Job.objects.filter(identifier__startswith=parent_id)
        if len(parents) == 0:
            return JsonResponse({
                'status': False,
                'message': _("Parent with the specified identifier "
                             "was not found")
            })
        elif len(parents) > 1:
            return JsonResponse({
                'status': False,
                'message': _("Too many jobs starts with the specified "
                             "identifier")
            })
        parent = parents[0]
        failed_jobs = []
        for f in request.FILES.getlist('file'):
            zipdata = job_f.ReadZipJob(parent, request.user, f)
            if zipdata.err_message is not None:
                # failed_jobs.append([f.name, zipdata.err_message])
                failed_jobs.append([zipdata.err_message + '', f.name])
        if len(failed_jobs) > 0:
            return JsonResponse({
                'status': False,
                'messages': failed_jobs
            })
        return JsonResponse({
            'status': True
        })

    return JsonResponse({
        'status': False,
        'message': _("Parent identifier was not got")
    })


def job_error(request, err_code=0):
    err_code = int(err_code)
    message = _('Unknown error')
    back = None
    if request.method == 'GET':
        back = request.GET.get('back', None)
        if back is not None:
            back = unquote(back)
    if err_code == 404:
        message = _('The job was not found')
    elif err_code == 400:
        message = _("You don't have an access to this job")
    elif err_code == 450:
        message = _('Some job is downloaded right now, '
                    'please try again later')
    elif err_code == 451:
        message = _('Wrong parameters, please reload page and try again.')
    return render(request, 'jobs/error.html',
                  {'message': message, 'back': back})


def psi_set_status(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 305})
    if request.method == 'POST':
        identifier = request.POST.get('identifier', None)
        status = request.POST.get('status', None)
        if identifier and status:
            try:
                job = Job.objects.get(identifier=identifier)
            except ObjectDoesNotExist:
                return JsonResponse({'error': 304})
            if job_f.is_operator(request.user, job):
                if status in [x[0] for x in JOB_STATUS]:
                    job.jobstatus.status = status
                    job.jobstatus.save()
                    return JsonResponse({'error': 0})
                else:
                    JsonResponse({'error': 302})
            else:
                JsonResponse({'error': 303})
    return JsonResponse({'error': 500})


def psi_download_job(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 305})
    if request.method != 'POST':
        return JsonResponse({'error': 500})
    job_identifier = request.POST.get('identifier', None)
    hash_sum = request.POST.get('hash_sum', None)
    supported_format = request.POST.get('supported_format', None)
    if job_identifier is None or hash_sum is None or supported_format is None:
        return JsonResponse({'error': 300})
    try:
        job = Job.objects.get(identifier=job_identifier,
                              format=int(supported_format))
    except ObjectDoesNotExist:
        return JsonResponse({'error': 304})

    if not job_f.is_operator(request.user, job):
        return JsonResponse({'error': 303})

    job_tar = job_f.JobArchive(job=job, hash_sum=hash_sum)
    if not job_tar.create_tar():
        return JsonResponse({'error': 500})

    response = HttpResponse(content_type="application/x-tar-gz")
    zipname = job_tar.jobtar_name
    response["Content-Disposition"] = "attachment; filename=%s" % zipname
    job_tar.memory.seek(0)
    response.write(job_tar.memory.read())
    return response
