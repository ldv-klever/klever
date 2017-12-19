#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from django.conf.urls import url
from marks import views


urlpatterns = [
    url(r'^(?P<mark_type>unsafe|safe|unknown)/create/(?P<report_id>[0-9]+)/$', views.create_mark, name='create_mark'),
    url(r'^(?P<mtype>unsafe|safe|unknown)/(?P<action>view|edit)/(?P<mark_id>[0-9]+)/$', views.mark_page, name='mark'),
    url(r'^(?P<mtype>unsafe|safe|unknown)/versions/(?P<mark_id>[0-9]+)/$', views.mark_versions, name='versions'),

    url(r'^(?P<marks_type>unsafe|safe|unknown)/$', views.mark_list, name='mark_list'),
    url(r'^download/(?P<mark_type>unsafe|safe|unknown)/(?P<mark_id>[0-9]+)/$',
        views.download_mark, name='download_mark'),
    url(r'^association_changes/(?P<association_id>.*)/$', views.association_changes),
    url(r'^tags/(?P<tags_type>unsafe|safe)/$', views.show_tags, name='tags'),
    url(r'^tags/download/(?P<tags_type>unsafe|safe)/$', views.download_tags, name='download_tags'),

    # For ajax requests
    url(r'^ajax/delete/$', views.delete_marks),
    url(r'^ajax/save_mark/$', views.save_mark),
    url(r'^ajax/upload_marks/$', views.upload_marks),
    url(r'^ajax/get_func_description/$', views.get_func_description),
    url(r'^ajax/inline_mark_form/$', views.get_inline_mark_form),
    url(r'^ajax/check-unknown-mark/$', views.check_unknown_mark),

    url(r'^ajax/get_mark_version_data/$', views.get_mark_version_data),
    url(r'^ajax/remove_versions/$', views.remove_versions),
    url(r'^ajax/compare_versions/$', views.compare_versions),

    url(r'^ajax/get_tag_data/$', views.get_tag_data),
    url(r'^ajax/save_tag/$', views.save_tag),
    url(r'^ajax/remove_tag/$', views.remove_tag),
    url(r'^ajax/get_tags_data/$', views.get_tags_data),
    url(r'^ajax/upload_tags/$', views.upload_tags),

    url(r'^ajax/confirm-association/$', views.confirm_association),
    url(r'^ajax/unconfirm-association/$', views.unconfirm_association),
    url(r'^ajax/like-association/$', views.like_association),

    # For service requests
    url(r'^download-all/$', views.download_all, name='download_all'),
    url(r'^upload-all/$', views.upload_all, name='upload_all'),
]
