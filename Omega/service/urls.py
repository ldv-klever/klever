from django.conf.urls import url
from service import views


urlpatterns = [
    url(r'^test/$', views.test),
    url(r'^init_session/$', views.init_session),
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
]