from django.conf.urls import url
from marks import views


urlpatterns = [
    url(r'^(?P<mark_type>unsafe|safe|unknown)/create/(?P<report_id>[0-9]+)/$', views.create_mark, name='create_mark'),
    url(r'^(?P<mark_type>unsafe|safe|unknown)/edit/(?P<mark_id>[0-9]+)/$', views.edit_mark, name='edit_mark'),
    url(r'^(?P<marks_type>unsafe|safe|unknown)/$', views.mark_list, name='mark_list'),
    url(r'^download/(?P<mark_type>unsafe|safe|unknown)/(?P<mark_id>[0-9]+)/$',
        views.download_mark, name='download_mark'),
    url(r'^delete/(?P<mark_type>unsafe|safe|unknown)/(?P<mark_id>[0-9]+)/$', views.delete_mark, name='delete_mark'),
    url(r'^association_changes/(?P<association_id>.*)/$', views.association_changes),
    url(r'^tags/(?P<tags_type>unsafe|safe)/$', views.show_tags, name='tags'),
    url(r'^tags/download/(?P<tags_type>unsafe|safe)/$', views.download_tags, name='download_tags'),

    # For ajax requests
    url(r'^ajax/delete/$', views.delete_marks),
    url(r'^ajax/save_mark/$', views.save_mark),
    url(r'^ajax/get_func_description/$', views.get_func_description),
    url(r'^ajax/upload_marks/$', views.upload_marks),
    url(r'^ajax/get_mark_version_data/$', views.get_mark_version_data),
    url(r'^ajax/getversions/$', views.get_mark_versions),
    url(r'^ajax/remove_versions/$', views.remove_versions),
    url(r'^ajax/get_tag_parents/$', views.get_tag_parents),
    url(r'^ajax/save_tag/$', views.save_tag),
    url(r'^ajax/remove_tag/$', views.remove_tag),
    url(r'^ajax/get_tags_data/$', views.get_tags_data),
    url(r'^ajax/upload_tags/$', views.upload_tags),

    # For service requests
    url(r'^download-all/$', views.download_all, name='download_all'),
    url(r'^upload-all/$', views.upload_all, name='upload_all'),
]
