from django.shortcuts import render
from jobs.forms import JobForm, FileForm
import json
import jobs.table_prop as tp
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from reports.models import STATUS
from django.http import HttpResponse, JsonResponse
from users.models import View, PreferableView


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


@login_required
def tree_view(request):
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


def create_job(request):
    if request.method == 'POST':
        job_form = JobForm(data=request.POST)
        # file_form = FileForm(data=request.POST)
        postdata = {
            'version': job_form.version,
            'title': job_form.title,
            'type': job_form.job_type,
            'comment': job_form.comment,
            'config': job_form.config,
        }
        return render(request, 'jobs/postData.html', {'strings': postdata})
    else:
        job_form = JobForm()
        file_form = FileForm()
        context = {'job_form': job_form, 'file_form': file_form}
        return render(request, 'jobs/createJob.html', context)


def get_filter_data(request):
    if request.method == 'POST':
        data_type = request.POST.get('type', None)
        if data_type is None:
            return
        if data_type == 'types':
            data_val = request.POST.get('value', None)
            if data_val is None:
                return HttpResponse('')
            needed_values = data_val.split(';')
            retval = {}
            for v in needed_values:
                retval[v] = tp.FILTER_TYPE_TITLES.get(v, '')
            return HttpResponse(json.dumps(retval, separators=(',', ':')),
                                content_type="application/json")
    return HttpResponse('')


@login_required
def save_view(request):
    is_success = False
    view_id = None
    if request.method == 'POST':
        view_data = request.POST.get('view', None)
        view_name = request.POST.get('title', None)
        if view_data and view_name:
            new_view = View()
            new_view.name = view_name
            new_view.view = view_data
            new_view.author = request.user
            new_view.type = '1'
            new_view.save()
            view_id = new_view.id
            request.user.preferableview_set.filter(view__type='1').delete()
            pref_view = PreferableView()
            pref_view.user = request.user
            pref_view.view = new_view
            pref_view.save()
            is_success = True
    return JsonResponse({'success': is_success, 'view_id': view_id})


@login_required
def change_preferable(request):
    if request.method == 'POST':
        view_id = request.POST.get('view_id', None)
        request.user.preferableview_set.filter(view__type='1').delete()
        if view_id != 'default':
            new_pref_view = View.objects.filter(
                author=request.user,
                pk=int(view_id), type='1'
            )
            if len(new_pref_view):
                pref_view = PreferableView()
                pref_view.user = request.user
                pref_view.view = new_pref_view[0]
                pref_view.save()
    return JsonResponse({})


@login_required
def remove_view(request):
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
    return JsonResponse({})
