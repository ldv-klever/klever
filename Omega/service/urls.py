from django.conf.urls import url
from service import views


urlpatterns = [
    # TESTS
    url(r'^test/$', views.test, name='test'),
    url(r'^ajax/fill_session/$', views.fill_session),
    url(r'^ajax/process_job/$', views.process_job),

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
    url(r'^schedulers/$', views.schedulers_info, name='schedulers'),
    url(r'^ajax/add_scheduler_user/$', views.add_scheduler_user)
]