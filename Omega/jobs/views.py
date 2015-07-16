import pytz
import json
import hashlib
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, render
from django.utils.translation import ugettext as _
from django.http import HttpResponse, JsonResponse, Http404
from jobs.job_model import Job, JOB_ROLES, JobHistory
from jobs.models import UserRole
from reports.models import STATUS
from users.models import View, PreferableView, USER_ROLES
import jobs.table_prop as tp
import jobs.job_functions as job_f
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import activate


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
    for status in STATUS:
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
        'available_views': available_views
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
                'message': _("Default view was set as preferable.")
            })
        else:
            return JsonResponse({
                'status': 1,
                'message': _("Default view is already preferable!")
            })

    try:
        user_view = View.objects.get(pk=view_id, author=request.user, type='1')
    except ObjectDoesNotExist:
        return JsonResponse({
            'status': 1,
            'message': _("View was not found!")
        })
    request.user.preferableview_set.filter(view__type='1').delete()
    pref_view = PreferableView()
    pref_view.user = request.user
    pref_view.view = user_view
    pref_view.save()
    return JsonResponse({
        'status': 0,
        'message': _("Preferable view was successfully changed!")
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
            {'status': 4, 'message': _("View name is required")}
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
                'message': _("You can't edit Default view!")
            })
        elif view_id:
            try:
                new_view = request.user.view_set.get(pk=int(view_id))
            except ObjectDoesNotExist:
                return JsonResponse({
                    'status': 1,
                    'message': _('View was not found!')
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
            'message': _("View was successfully saved")
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
                    'message': _("View was successfully removed")
                })
            else:
                return JsonResponse({
                    'status': 1,
                    'message': _("View was not found")
                })
        else:
            return JsonResponse({
                'status': 1,
                'message': _("You can't remove Default view")
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

    # Get needed job or return error 404 (page doesn't exist)
    job = get_object_or_404(Job, pk=int(job_id))

    if not job_f.has_job_access(request.user, job=job):
        raise Http404(_("You don't have access to this verification job!"))

    # Get author of the job (who had created first version)
    created_by = None
    first_version = job.jobhistory_set.filter(version=1)
    if first_version:
        created_by = first_version[0].change_author.extended.last_name
        created_by += ' ' + first_version[0].change_author.extended.first_name

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

    return render(
        request,
        'jobs/viewJob.html',
        {
            'job': job,
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

    # Collecting existing job data
    job_parent_id = None
    if job_id:
        if job.parent:
            job_parent_id = job.parent.identifier
    else:
        job_parent_id = job.identifier
    old_job = job
    if version > 0:
        old_job_set = job.jobhistory_set.filter(version=version)
        if len(old_job_set):
            old_job = old_job_set[0]

    job_data = {
        'id': None,
        'parent_id': job_parent_id,
        'name': old_job.name,
        'configuration': old_job.configuration,
        'comment': old_job.comment,
        'version': None
    }
    if job_id:
        job_data['id'] = job.pk
        job_data['version'] = job.version

    # Get list of job versions
    job_versions = []
    if job_id:
        jobs = job.jobhistory_set.all().order_by('-version')
        for j in jobs:
            if j.version == job.version:
                title = _("Current version")
            else:
                job_time = j.change_date.astimezone(
                    pytz.timezone(request.user.extended.timezone)
                )
                title = job_time.strftime("%d.%m.%Y %H:%M:%S")
            job_versions.append({
                'version': j.version,
                'title': title
            })

    roles = job_f.role_info(job, request.user)
    if parent_id:
        roles['user_roles'] = []
        roles['global'] = JOB_ROLES[0][0]
    if version > 0:
        roles['user_roles'] = []
        roles['global'] = old_job.global_role
    return render(
        request,
        template,
        {
            'job': job_data,
            'roles': roles,
            'job_versions': job_versions,
            'version': version
        }
    )


@login_required
def create_job_page(request):
    return get_version_data(request, 'jobs/createJob.html')


@login_required
def save_job(request):
    if request.method != 'POST':
        return JsonResponse({'status': 1})

    title = request.POST.get('title', '')
    comment = request.POST.get('comment', '')
    config = request.POST.get('configuration', '')
    job_id = request.POST.get('job_id', None)
    parent_identifier = request.POST.get('parent_identifier', None)
    global_role = request.POST.get('global_role', JOB_ROLES[0][0])
    user_roles = request.POST.get('user_roles', '[]')
    user_roles = json.loads(user_roles)

    if job_id and parent_identifier:
        try:
            parent = Job.objects.get(identifier=parent_identifier)
            job = Job.objects.get(pk=int(job_id))
        except ObjectDoesNotExist:
            return JsonResponse({'status': 3})
        if not job_f.has_job_access(request.user, action='edit', job=job):
            return JsonResponse({'status': 10})
        if job.parent.identifier != parent.identifier:
            return JsonResponse({'status': 5})
        job.version += 1
    elif job_id:
        try:
            job = Job.objects.get(pk=int(job_id))
        except ObjectDoesNotExist:
            return JsonResponse({'status': 3})
        if not job_f.has_job_access(request.user, action='edit', job=job):
            return JsonResponse({'status': 10})
        job.version += 1
    elif parent_identifier:
        try:
            parent = Job.objects.get(identifier=parent_identifier)
        except ObjectDoesNotExist:
            return JsonResponse({'status': 3})
        if not job_f.has_job_access(request.user, action='create'):
            return JsonResponse({'status': 10})
        job = Job()
        job.type = parent.type
        job.parent = parent
    else:
        return JsonResponse({'status': 3})

    job.change_author = request.user
    job.name = title
    job.comment = comment
    job.configuration = config
    job.global_role = global_role
    job.save()
    if parent_identifier and job_id is None:
        time_encoded = job.change_date.strftime(
            "%Y%m%d%H%M%S%f%z"
        ).encode('utf-8')
        job.identifier = hashlib.md5(time_encoded).hexdigest()
        job.save()

    new_version = JobHistory()
    new_version.job = job
    new_version.name = job.name
    new_version.comment = job.comment
    new_version.configuration = job.configuration
    new_version.global_role = job.global_role
    new_version.type = job.type
    new_version.change_author = job.change_author
    new_version.change_date = job.change_date
    new_version.format = job.format
    new_version.version = job.version
    new_version.save()

    UserRole.objects.filter(job=job).delete()
    for ur in user_roles:
        user_id = int(ur['user'])
        role = ur['role']
        ur_user = User.objects.filter(pk=user_id)
        if len(ur_user):
            new_ur = UserRole()
            new_ur.job = job
            new_ur.user = ur_user[0]
            new_ur.role = role
            new_ur.save()
    return JsonResponse({'status': 0, 'job_id': job.pk})


@login_required
def remove_job(request):
    if request.method != 'POST':
        return JsonResponse({'status': 1})

    job_id = request.POST.get('job_id', None)
    if job_id is None:
        return JsonResponse({'status': 2})
    try:
        job = Job.objects.get(pk=job_id)
    except ObjectDoesNotExist:
        return JsonResponse({'status': 3})

    if not job_f.has_job_access(request.user, action='remove', job=job):
        return JsonResponse({'status': 10})

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
                'message': _('Job was not found, please reload page.')
            })
    for job in jobs:
        if not job_f.has_job_access(request.user, action="remove", job=job):
            return JsonResponse({
                'status': 1,
                'message':
                    _("You don't have access to remove one of selected jobs.")
            })
    for job in jobs:
        job.delete()
    return JsonResponse({'status': 0})
