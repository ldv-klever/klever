from django.conf.urls import url
from reports import views


urlpatterns = [
    url(r'^(?P<report_id>[0-9]+)/$', views.report_root, name='report_root'),
    url(r'^component/(?P<report_id>[0-9]+)/$', views.report_component, name='report_component'),
    url(r'^unsafes/(?P<report_id>[0-9]+)/$', views.report_unsafes, name='report_unsafes'),
    url(r'^safes/(?P<report_id>[0-9]+)/$', views.report_safes, name='report_safes'),
    url(r'^unknowns/(?P<report_id>[0-9]+)/$', views.report_unknowns, name='report_unknowns'),
    url(r'^unsafe/(?P<report_id>[0-9]+)/$', views.report_unsafe, name='report_unsafe'),
    url(r'^safe/(?P<report_id>[0-9]+)/$', views.report_safe, name='report_safe'),
    url(r'^unknown/(?P<report_id>[0-9]+)/$', views.report_unknown, name='report_unknown'),
    url(r'^upload/$', views.upload),
]
