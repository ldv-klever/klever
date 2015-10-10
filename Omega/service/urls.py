from django.conf.urls import url
from service import views


urlpatterns = [
    url(r'^test/$', views.test),
    url(r'^ajax/init_session/$', views.init_session),
    url(r'^ajax/add_scheduler/$', views.add_scheduler),
    url(r'^ajax/get_scheduler_login_data/$', views.get_scheduler_login_data),
    url(r'^ajax/add_scheduler_login_data/$', views.add_scheduler_login_data),
    url(r'^ajax/remove_sch_logindata/$', views.remove_sch_logindata),
]