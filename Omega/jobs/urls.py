from django.conf.urls import url
from jobs import views


urlpatterns = [
    url(r'^$', views.tree_view, name='tree'),
    url(r'^jobtable/$', views.get_jobtable),
    url(r'^(?P<job_id>[0-9]+)/$', views.show_job, name='job'),
    url(r'^jobnotfound/$', views.job404, name='job404'),
    url(r'^ajax/save_view/$', views.save_view),
    url(r'^ajax/remove_view/$', views.remove_view),
    url(r'^ajax/preferable_view/$', views.preferable_view),
    url(r'^ajax/check_view_name/$', views.check_view_name),
    url(r'^ajax/remove_jobs/$', views.remove_jobs),
    url(r'^editjob/$', views.get_version_data),
    url(r'^create/$', views.create_job_page),
    url(r'^savejob/$', views.save_job),
    url(r'^removejob/$', views.remove_job),
]
