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
from django.shortcuts import get_object_or_404, render
from django.utils.translation import ugettext as _
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from jobs.job_model import Job, JobHistory, JobStatus
from jobs.models import UserRole, File, FileSystem
from jobs.forms import FileForm
from users.models import View, PreferableView
import jobs.table_prop as tp
import jobs.job_functions as job_f
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import activate
from Omega.vars import JOB_ROLES, JOB_STATUS


class Counter(object):
    def __init__(self):
        self.cnt = 1
        self.dark = False

    def increment(self):
        self.cnt += 1
        if self.cnt % 2:
            self.dark = False
        else:
            self.dark = True


class Flag(object):
    def __init__(self):
        self.f = True

    def change_flag(self):
        if self.f:
            self.f = False
        else:
            self.f = True


##################
# Jobs tree page #
##################
@login_required
def tree_view(request):
    activate(request.user.extended.language)
    if request.method == 'POST':
        filters = tp.FilterForm(
            request.user,
            view=request.POST.get('view', None),
            view_id=request.POST.get('view_id', None)
        )
    else:
        filters = tp.FilterForm(request.user)

    users = User.objects.all()
    available_views = []
    for v in request.user.view_set.filter(type='1'):
        available_views.append({
            'title': v.name,
            'id': v.pk,
            'selected': (filters.view_id == v.pk),
        })
    statuses = []
    for status in JOB_STATUS:
        statuses.append({
            'title': status[1],
            'value': status[0],
        })
    context = {
        'available': filters.available_columns,
        'selected': filters.selected_columns,
        'available_orders': filters.available_orders,
        'selected_orders': filters.selected_orders,
        'user_views': filters.user_views,
        'selected_filters': filters.filters,
        'authors': users,
        'statuses': statuses,
        'available_filters': filters.available_filters,
        'available_views': available_views,
        'can_create': job_f.has_job_access(request.user, action='create')
    }
    return render(request, 'jobs/tree.html', context)


@login_required
def get_jobtable(request):
    activate(request.user.extended.language)
    if request.method == 'GET':
        return HttpResponse('')

    # Reading all required data from the database and
    # user view for drawing the table.
    table_data = tp.TableTree(
        request.user,
        view=request.POST.get('view', None),
        view_id=request.POST.get('view_id', None)
    )

    header_data = table_data.tableheader
    sum_of_columns = len(table_data.columns) + 1

    # The first column of the table is with checkboxes, so we have to
    # append to table's header data information for this column
    header_data[0].insert(0, {
        'column': '',
        'rows': max([col['rows'] for col in header_data[0]]),
        'columns': 1,
        'title': '',
    })

    # Counting how many columns the header of footer of the table needs
    # ('All', and 'All for checked')
    all_head_num = 0
    for col in header_data[0]:
        if col['column'] in ['name', 'author', 'date', 'status', '']:
            all_head_num += 1
        else:
            break

    # Table rows
    values_data = table_data.values
    counter = Counter()
    context = {
        'columns': header_data,
        'values': values_data,
        'counter': counter,
    }
    # If we have any rows in values data we print table footer and
    # give each column except header of footer id that we can get from this list
    if len(values_data) and (sum_of_columns - all_head_num) > 0:
        context['foot_cols'] = values_data[0]['values'][(all_head_num - 1):]
        context['foot_head_num'] = all_head_num

    return render(request, 'jobs/treeTable.html', context)


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
        else:
            return JsonResponse({
                'status': 1,
                'message': _("The default view is already preferred")
            })

    try:
        user_view = View.objects.get(pk=view_id, author=request.user, type='1')
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
        return JsonResponse({'status': 1, 'message': "Error 1"})

    view_name = request.POST.get('view_title', None)
    if view_name is None:
        return JsonResponse({'status': 2, 'message': "Error 2"})

    if view_name == _('Default'):
        return JsonResponse(
            {'status': 3, 'message': _("Please choose another view name")}
        )

    if view_name == '':
        return JsonResponse(
            {'status': 4, 'message': _("The view name is required")}
        )

    if len(request.user.view_set.filter(type='1', name=view_name)):
        return JsonResponse(
            {'status': 5, 'message': _("Please choose another view name")}
        )
    return JsonResponse({'status': 0})


@login_required
def save_view(request):
    activate(request.user.extended.language)
    if request.method == 'POST':
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
        elif view_id:
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
    return JsonResponse({'status': 1, 'message': _('Unknown error')})


@login_required
def remove_view(request):
    activate(request.user.extended.language)
    if request.method == 'POST':
        view_id = request.POST.get('view_id', None)
        request.user.preferableview_set.filter(view__type='1').delete()
        if view_id != 'default':
            new_pref_view = View.objects.filter(
                author=request.user,
                pk=int(view_id), type='1'
            )
            if len(new_pref_view):
                new_pref_view[0].delete()
                return JsonResponse({
                    'status': 0,
                    'message': _("The view was successfully removed")
                })
            else:
                return JsonResponse({
                    'status': 1,
                    'message': _("The view was not found")
                })
        else:
            return JsonResponse({
                'status': 1,
                'message': _("You can't remove the default view")
            })
    return JsonResponse({
        'status': 1,
        'message': _("Unknown error")
    })


#################
# View job page #
#################
@login_required
def show_job(request, job_id=None):
    activate(request.user.extended.language)

    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(
            reverse('jobs:error', args=[404]) + "?back=%s" % quote(
                reverse('jobs:tree')))
        # return job404(request, _('The job was not found'))

    if not job_f.has_job_access(request.user, action="view", job=job):
        return HttpResponseRedirect(
            reverse('jobs:error', args=[400]) + "?back=%s" % quote(
                reverse('jobs:tree')))
        # return job404(
        #     request,
        #     _("You don't have an access to this job")
        # )

    created_by = job.jobhistory_set.get(version=1).change_author

    # Collect parents of the job
    parents = []
    job_parent = job.parent
    while job_parent:
        parents.append(job_parent)
        job_parent = job_parent.parent
    parents.reverse()
    have_access_parents = []
    for parent in parents:
        if job_f.has_job_access(request.user, job=parent):
            job_id = parent.pk
        else:
            job_id = None
        have_access_parents.append({
            'pk': job_id,
            'name': parent.name,
        })

    # Collect children of the job
    children = job.children_set.all()
    have_access_children = []
    for child in children:
        if job_f.has_job_access(request.user, action="view", job=child):
            job_id = child.pk
        else:
            job_id = None
        have_access_children.append({
            'pk': job_id,
            'name': child.name,
        })

    # Get user time zone
    user_tz = request.user.extended.timezone
    last_change_comment = job.jobhistory_set.get(version=job.version).comment
    return render(
        request,
        'jobs/viewJob.html',
        {
            'job': job,
            'change_comment': last_change_comment,
            'parents': have_access_parents,
            'children': have_access_children,
            'user_tz': user_tz,
            'verdict': job_f.verdict_info(job),
            'unknowns': job_f.unknowns_info(job),
            'resources': job_f.resource_info(job, request.user),
            'created_by': created_by,
            'can_delete': job_f.has_job_access(
                request.user, action='remove', job=job
            ),
            'can_edit': job_f.has_job_access(
                request.user, action='edit', job=job
            ),
            'can_create': job_f.has_job_access(
                request.user, action='create'
            ),
        }
    )


@login_required
def get_version_data(request, template='jobs/editJob.html'):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponse('')

    # If None than we are creating new version
    job_id = request.POST.get('job_id', None)

    # If None than we are editing old version
    parent_id = request.POST.get('parent_id', None)

    version = request.POST.get('version', 0)
    version = int(version)

    # job and parent id can't be both None or both not None
    if (job_id and parent_id) or (job_id is None and parent_id is None):
        return HttpResponse('')

    # Get needed job or return error 404 (page doesn't exist)
    try:
        if job_id:
            job = get_object_or_404(Job, pk=int(job_id))
            if not job_f.has_job_access(request.user, action='edit', job=job):
                return HttpResponse('')
        else:
            job = get_object_or_404(Job, pk=int(parent_id))
            if not job_f.has_job_access(request.user, action='create'):
                return HttpResponse('')
    except ValueError:
        return HttpResponse('')

    if len(job.jobhistory_set.all()) == 0:
        return HttpResponse('')
    if version > 0:
        job_version = job.jobhistory_set.get(version=version)
    else:
        job_version = job.jobhistory_set.all().order_by('-change_date')[0]

    roles = job_f.role_info(job_version, request.user)

    parent_identifier = None
    if job.parent:
        parent_identifier = job.parent.identifier
    job_data = {
        'id': None,
        'parent_id': parent_identifier,
        'name': job_version.name,
        'configuration': job_version.configuration,
        'description': job_version.description,
        'version': None
    }

    job_versions = []
    if job_id:
        if job_version.parent:
            job_data['parent_id'] = job_version.parent.identifier
        job_data['id'] = job.pk
        job_data['version'] = job.version
        jobs = job.jobhistory_set.all().order_by('-version')
        for j in jobs:
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

    if parent_id:
        roles['user_roles'] = []
        roles['global'] = JOB_ROLES[0][0]
        roles['available_users'] = []
        for u in User.objects.filter(~Q(pk=request.user.pk)):
            roles['available_users'].append({
                'id': u.pk,
                'name': u.extended.last_name + ' ' + u.extended.first_name
            })

    filesdata = job_f.FileData(job_version)

    return render(
        request,
        template,
        {
            'job': job_data,
            'roles': roles,
            'job_versions': job_versions,
            'version': version,
            'filedata': filesdata.filedata
        }
    )


@login_required
def create_job_page(request):
    return get_version_data(request, 'jobs/createJob.html')


@login_required
def save_job(request):
    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _('Unknown error')})

    title = request.POST.get('title', '')
    description = request.POST.get('description', '')
    comment = request.POST.get('comment', '')
    config = request.POST.get('configuration', '')
    job_id = request.POST.get('job_id', None)
    parent_identifier = request.POST.get('parent_identifier', None)
    global_role = request.POST.get('global_role', JOB_ROLES[0][0])
    user_roles = request.POST.get('user_roles', '[]')
    user_roles = json.loads(user_roles)

    file_data = request.POST.get('file_data', '[]')
    file_data = json.loads(file_data)

    last_version = int(request.POST.get('last_version', 0))

    if job_id:
        try:
            job = Job.objects.get(pk=int(job_id))
        except ObjectDoesNotExist:
            return JsonResponse({
                'status': 1,
                'message': _('The job was not found')
            })
        if not job_f.has_job_access(request.user, action='edit', job=job):
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
                    'message': _("Root jobs can't become another child!")
                })
            if not job_f.check_new_parent(job, parent):
                return JsonResponse({
                    'status': 1,
                    'message': _("The specified parent can't "
                                 "be set for this job")
                })
            job.parent = parent
        elif job.parent:
            return JsonResponse({
                'status': 1,
                'message': _("A parent identifier is required for this job")
            })

        if job.version != last_version:
            return JsonResponse({
                'status': 1,
                'message': _("Your version is expired, please reload the page")
            })
        job.version += 1
    elif job_id is None and parent_identifier:
        try:
            parent = Job.objects.get(identifier=parent_identifier)
        except ObjectDoesNotExist:
            return JsonResponse({
                'status': 1,
                'message': _('The job parent was not found')
            })
        if not job_f.has_job_access(request.user, action='create'):
            return JsonResponse({
                'status': 1,
                'message': _("You don't have an access to create a new job")
            })
        job = Job()
        job.type = parent.type
        job.parent = parent
    else:
        return JsonResponse({'status': 1, 'message': _('Unknown error')})

    job.change_author = request.user
    job.name = title
    job.description = description
    job.configuration = config
    job.global_role = global_role
    job.save()
    if parent_identifier and job_id is None:
        time_encoded = job.change_date.strftime(
            "%Y%m%d%H%M%S%f%z"
        ).encode('utf-8')
        job.identifier = hashlib.md5(time_encoded).hexdigest()
        job.save()
        jobstatus = JobStatus()
        jobstatus.job = job
        jobstatus.save()

    new_version = JobHistory()
    new_version.job = job
    new_version.name = job.name
    new_version.description = job.description
    new_version.comment = comment
    new_version.configuration = job.configuration
    new_version.global_role = job.global_role
    new_version.type = job.type
    new_version.change_author = job.change_author
    new_version.change_date = job.change_date
    new_version.format = job.format
    new_version.version = job.version
    new_version.parent = job.parent
    new_version.save()

    for ur in user_roles:
        user_id = int(ur['user'])
        role = ur['role']
        ur_user = User.objects.filter(pk=user_id)
        if len(ur_user):
            new_ur = UserRole()
            new_ur.job = new_version
            new_ur.user = ur_user[0]
            new_ur.role = role
            new_ur.save()

    saving_filedata = job_f.DBFileData(file_data, new_version)
    if saving_filedata.err_message:
        if job.version == 1:
            job.delete()
        else:
            job.version -= 1
            job.save()
            new_version.delete()
        err_message = saving_filedata.err_message
        err_message += ' ' + _("Please reload the page and try again")
        return JsonResponse({
            'status': 1,
            'message': err_message,
        })
    return JsonResponse({'status': 0, 'job_id': job.pk})


@login_required
def remove_job(request):
    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _('Unknown error')})

    job_id = request.POST.get('job_id', None)
    if job_id is None:
        return JsonResponse({'status': 1, 'message': _('Unknown error')})
    try:
        job = Job.objects.get(pk=job_id)
    except ObjectDoesNotExist:
        return JsonResponse({
            'status': 1, 'message': _('The job was not found')
        })

    if not job_f.has_job_access(request.user, action='remove', job=job):
        return JsonResponse({
            'status': 1,
            'message': _("You don't have an access to remove this job")
        })
    job.delete()
    return JsonResponse({'status': 0})


@login_required
def remove_jobs(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _('Unknown error')})
    job_ids = request.POST.get('jobs', [])
    job_ids = json.loads(job_ids)
    jobs = []
    for job_id in job_ids:
        try:
            jobs.append(Job.objects.get(pk=int(job_id)))
        except ObjectDoesNotExist:
            return JsonResponse({
                'status': 1,
                'message': _('The job was not found, please reload the page')
            })
    for job in jobs:
        if not job_f.has_job_access(request.user, action="remove", job=job):
            return JsonResponse({
                'status': 1,
                'message':
                    _("You don't have an access to "
                      "remove one of the selected jobs")
            })
    for job in jobs:
        job.delete()
    return JsonResponse({'status': 0})


@login_required
def showjobdata(request):
    if request.method != 'POST':
        return HttpResponse('')
    job_id = request.POST.get('job_id', None)
    if job_id:
        try:
            job = Job.objects.get(pk=int(job_id))
        except ObjectDoesNotExist:
            return HttpResponse('')
        job_version = job.jobhistory_set.filter(version=job.version)[0]
        filesdata = job_f.FileData(job_version)
        return render(request, 'jobs/showJob.html', {
            'job': job,
            'filedata': filesdata.filedata
        })
    return HttpResponse('')


@login_required
def upload_files(request):
    if request.method != 'POST':
        return HttpResponse('')
    form = FileForm(request.POST, request.FILES)
    if form.is_valid():
        new_file = form.save(commit=False)
        check_sum = hashlib.md5(new_file.file.read()).hexdigest()
        if len(File.objects.filter(hash_sum=check_sum)):
            return JsonResponse({
                'hash_sum': check_sum,
                'status': 0
            })
        new_file.hash_sum = check_sum
        new_file.save()
        return JsonResponse({
            'hash_sum': check_sum,
            'status': 0
        })
    print("%s" % form.errors)
    return JsonResponse({
        'message': 'Loading failed!',
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
    response['Content-Disposition'] = 'attachment; filename="%s"' % source.name
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
    if not job_f.has_job_access(request.user, action='view', job=job):
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
    job_zip = job_f.JobArchive(job=job, hash_sum=hash_sum)
    job_zip.create_tar()
    if job_zip.err_code > 0:
        response = HttpResponseRedirect(
            reverse('jobs:error',
                    args=[job_zip.err_code]) + "?back=%s" % back_url
        )
    else:
        response = HttpResponse(content_type="application/x-tar-gz")
        zipname = job_zip.jobtar_name
        response["Content-Disposition"] = "attachment; filename=%s" % zipname
        job_zip.memory.seek(0)
        response.write(job_zip.memory.read())
    return response


def test_page(request):
    return render(request, 'jobs/testpage.html', {})


def job_error(request, err_code=0):
    err_code = int(err_code)
    message = _('Unknown error')
    back = None
    if request.method == 'GET':
        back = request.GET.get('back', None)
        if back:
            back = unquote(back)
    if err_code == 404:
        message = _('The job was not found')
    elif err_code == 400:
        message = _("You don't have an access to this job")
    elif err_code == 450:
        message = _('Somebody is downloading a job right now, '
                    'please try again later')
    elif err_code == 451:
        message = _('Wrong parameters, please reload page and try again.')
    return render(request, 'jobs/error.html',
                  {'message': message, 'back': back})


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
            if not job_f.has_job_access(request.user, action='view', job=job):
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
                'message': _("Parent with this id was not found.")
            })
        elif len(parents) > 1:
            return JsonResponse({
                'status': False,
                'message': _("Too many parents starts with this id.")
            })
        parent = parents[0]
        if len(request.FILES) == 0:
            return JsonResponse({
                'status': False,
                'message': _("Zip archive was not got.")
            })

        zipdata = job_f.ReadZipJob(parent, request.user, request.FILES['file'])
        if zipdata.job_id:
            return JsonResponse({
                'status': True,
                'job_id': zipdata.job_id
            })
        else:
            return JsonResponse({
                'status': False,
                'message': _("Job was not saved!")
            })
    return JsonResponse({
        'status': False,
        'message': _("Parent id was not got.")
    })


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
        else:
            print(2)
    print(1)
    return JsonResponse({'error': 500})


def psi_download_job(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 305})
    if request.method != 'POST':
        return JsonResponse({'error': 500})
    job_identifier = request.POST.get('identifier', None)
    hash_sum = request.POST.get('hash_sum', None)
    if job_identifier is None or hash_sum is None:
        return JsonResponse({'error': 300})
    try:
        job = Job.objects.get(identifier=job_identifier)
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
