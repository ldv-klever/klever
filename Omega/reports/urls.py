from django.conf.urls import url
from reports import views


urlpatterns = [
    url(r'^(?P<report_id>[0-9]+)/$', views.report_root, name='report_root'),
    url(r'^component/(?P<report_id>[0-9]+)/$', views.report_component, name='report_component'),
]
