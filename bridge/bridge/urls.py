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

from django.conf.urls import include, url
from django.contrib import admin
from django.conf import settings
from bridge import views
from django.views.static import serve

urlpatterns = [
    url(r'^i18n/', include('django.conf.urls.i18n')),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^users/', include('users.urls', namespace='users')),
    url(r'^jobs/', include('jobs.urls', namespace='jobs')),
    url(r'^reports/', include('reports.urls', namespace='reports')),
    url(r'^marks/', include('marks.urls', namespace='marks')),
    url(r'^service/', include('service.urls', namespace='service')),
    url(r'^tools/', include('tools.urls', namespace='tools')),
    url(r'^$', views.index_page),
    url(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT, 'show_indexes': True}),
    url(r'^population/$', views.population, name='population')
]
