from django.conf.urls import url
from marks import views


urlpatterns = [
    url(r'^(?P<report_id>[0-9]+)/$', views.create_mark, name='create_mark'),
]
