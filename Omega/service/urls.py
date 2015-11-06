from django.conf.urls import url
from service import views


urlpatterns = [
    url(r'^test/$', views.test),
    url(r'^set_schedulers_status/$', views.set_schedulers_status),
    url(r'^get_jobs_and_tasks/$', views.get_jobs_and_tasks),
    url(r'^schedule_task/$', views.schedule_task),
    url(r'^update_tools/$', views.update_tools),
    url(r'^get_task_status/$', views.get_task_status),
    url(r'^remove_task/$', views.remove_task),
    url(r'^cancel_task/$', views.cancel_task),
    url(r'^upload_solution/$', views.upload_solution),
    url(r'^download_solution/(?P<task_id>[0-9]+)/$', views.download_solution),
    url(r'^download_task/(?P<task_id>[0-9]+)/$', views.download_task),
    url(r'^update_nodes/$', views.update_nodes),

    url(r'^ajax/add_scheduler_user/$', views.add_scheduler_user),
    url(r'^ajax/remove_scheduler_user/$', views.remove_scheduler_user),
    url(r'^ajax/update_jobs/(?P<user_id>[0-9]+)$', views.update_user_jobs),
    url(r'^ajax/scheduler_sessions/$', views.scheduler_sessions),
    url(r'^ajax/scheduler_job_sessions/$', views.scheduler_job_sessions),

    url(r'^jobs/(?P<user_id>[0-9]+)$', views.user_jobs, name='jobs'),
    url(r'^scheduler/(?P<scheduler_id>[0-9]+)$', views.scheduler_table,
        name='scheduler'),
    url(r'^sessions/$', views.sessions_page, name='sessions'),
    url(r'^manager-tools/$', views.manager_tools, name='manager_tools'),
    url(r'^ajax/change_component/$', views.change_component),
    url(r'^ajax/clear_components_table/$', views.clear_components_table),
    url(r'^ajax/delete_problem/$', views.delete_problem),
    url(r'^ajax/clear_problems/$', views.clear_problems),
]