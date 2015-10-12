from django.conf.urls import url
from service import views


urlpatterns = [
    url(r'^test/$', views.test),
    url(r'^ajax/init_session/$', views.init_session),
    url(r'^ajax/close_session/$', views.close_session),
    url(r'^ajax/add_scheduler/$', views.add_scheduler),
    url(r'^ajax/clear_sessions/$', views.clear_sessions),
    url(r'^ajax/check_schedulers/$', views.check_schedulers),
    url(r'^ajax/close_sessions/$', views.close_sessions),
    url(r'^ajax/get_tasks/$', views.get_tasks),
    url(r'^ajax/create_task/$', views.create_task),

    url(r'^ajax/get_scheduler_login_data/$', views.get_scheduler_login_data),
    url(r'^ajax/add_scheduler_login_data/$', views.add_scheduler_login_data),
    url(r'^ajax/remove_sch_logindata/$', views.remove_sch_logindata),
]