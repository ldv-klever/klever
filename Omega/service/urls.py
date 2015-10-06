from django.conf.urls import url
from service import views


urlpatterns = [
    url(r'^init_session/$', views.init_session),
]