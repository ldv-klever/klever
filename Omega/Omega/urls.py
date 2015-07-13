from django.conf.urls import include, url
from django.contrib import admin

urlpatterns = [
    url(r'^admin/', include(admin.site.urls)),
    url(r'^users/', include('users.urls', namespace='users')),
    url(r'^jobs/', include('jobs.urls', namespace='jobs')),
    url(r'^$', 'users.views.index_page'),
]
