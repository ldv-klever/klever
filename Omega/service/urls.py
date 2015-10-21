from django.conf.urls import url
from service import views


urlpatterns = [
    url(r'^test/$', views.test),
    url(r'^close_session/$', views.close_session),
    url(r'^add_scheduler/$', views.add_scheduler),
    url(r'^clear_sessions/$', views.clear_sessions),
    url(r'^check_schedulers/$', views.check_schedulers),
    url(r'^close_sessions/$', views.close_sessions),
    url(r'^get_tasks/$', views.get_tasks),
    url(r'^create_task/$', views.create_task),
    url(r'^update_tools/$', views.update_tools),
    url(r'^get_task_status/$', views.get_task_status),
    url(r'^remove_task/$', views.remove_task),
    url(r'^stop_task/$', views.stop_task),
    url(r'^create_solution/$', views.create_solution),
    url(r'^download_solution/(?P<task_id>[0-9]+)/$', views.download_solution),
    url(r'^download_task/(?P<task_id>[0-9]+)/$', views.download_task),
    url(r'^update_nodes/$', views.update_nodes),

    url(r'^ajax/get_scheduler_login_data/$', views.get_scheduler_login_data),
    url(r'^ajax/add_scheduler_login_data/$', views.add_scheduler_login_data),
    url(r'^ajax/remove_sch_logindata/$', views.remove_sch_logindata),
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