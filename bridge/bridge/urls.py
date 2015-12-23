from django.conf.urls import include, url
from django.contrib import admin
from django.conf import settings
from bridge import views
from django.views.static import serve
from users.views import index_page

urlpatterns = [
    url(r'^i18n/', include('django.conf.urls.i18n')),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^users/', include('users.urls', namespace='users')),
    url(r'^jobs/', include('jobs.urls', namespace='jobs')),
    url(r'^reports/', include('reports.urls', namespace='reports')),
    url(r'^marks/', include('marks.urls', namespace='marks')),
    url(r'^service/', include('service.urls', namespace='service')),
    url(r'^tools/', include('tools.urls', namespace='tools')),
    url(r'^$', index_page),
    url(r'^media/(?P<path>.*)$', serve, {
        'document_root': settings.MEDIA_ROOT,
        'show_indexes': True
    }),
    url(r'^error/(?P<err_code>[0-9]+)/$', views.klever_bridge_error, name='error'),
    url(r'^population/$', views.population, name='population')
]
