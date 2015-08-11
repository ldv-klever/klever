from django.conf.urls import url
from reports import views


urlpatterns = [
    url(r'^component/(?P<job_id>[0-9]+)/(?P<report_id>[0-9]+)/$',
        views.report_component, name='report_component'),
    url('^log/(?P<report_id>[0-9]+)/$', views.get_component_log,
        name='report_log'),
    url(r'^upload/$', views.upload_report),
    url(r'^clear_tables/$', views.clear_tables),
    url(r'^component/(?P<report_id>[0-9]+)/(?P<ltype>unsafes|safes|unknowns)/$',
        views.report_list, name='report_list'),
    url(r'^component/(?P<report_id>[0-9]+)/unknowns/(?P<component_id>[0-9]+)/$',
        views.report_unknowns, name='report_unknowns'),

    url(r'^unsafe/(?P<report_id>[0-9]+)/$', views.report_unsafe, name='report_unsafe'),
    url(r'^safe/(?P<report_id>[0-9]+)/$', views.report_safe, name='report_safe'),
    url(r'^unknown/(?P<report_id>[0-9]+)/$', views.report_unknown, name='report_unknown'),
]
