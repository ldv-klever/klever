from django.conf.urls import url
from marks import views


urlpatterns = [
    url(r'^(?P<mark_type>unsafe|safe|unknown)/create/(?P<report_id>[0-9]+)/$',
        views.create_mark, name='create_mark'),
    url(r'^(?P<mark_type>unsafe|safe|unknown)/edit/(?P<mark_id>[0-9]+)/$',
        views.edit_mark, name='edit_mark'),
    url(r'^(?P<marks_type>unsafe|safe|unknown)/$',
        views.mark_list, name='mark_list'),
    url(r'^unklinked/$', views.marks_all, name='marks_all'),

    url(r'^ajax/save_mark/$', views.save_mark),
    url(r'^ajax/get_func_description/$', views.get_func_description),
    url(r'^ajax/get_mark_version_data/$', views.get_mark_version_data),
]
