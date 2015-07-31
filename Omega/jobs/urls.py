from django.conf.urls import url
from jobs import views


urlpatterns = [
    url(r'^$', views.tree_view, name='tree'),
    url(r'^(?P<job_id>[0-9]+)/$', views.show_job, name='job'),
    url(r'^joberror/(?P<err_code>[0-9]+)/$', views.job_error, name='error'),
    url(r'^downloadfile/(?P<file_id>[0-9]+)/$', views.download_file,
        name='download_file'),

    # For ajax requests
    url(r'^ajax/save_view/$', views.save_view),
    url(r'^ajax/remove_view/$', views.remove_view),
    url(r'^ajax/preferable_view/$', views.preferable_view),
    url(r'^ajax/check_view_name/$', views.check_view_name),
    url(r'^ajax/remove_jobs/$', views.remove_jobs),
    url(r'^ajax/editjob/$', views.edit_job),
    url(r'^ajax/create/$', views.create_job),
    url(r'^ajax/savejob/$', views.save_job),
    url(r'^ajax/removejob/$', views.remove_job),
    url(r'^ajax/showjobdata/$', views.showjobdata),
    url(r'^ajax/upload_file/$', views.upload_file),
    url(r'^ajax/downloadjob/(?P<job_id>[0-9]+)/$', views.download_job),
    url(r'^ajax/downloadlock/$', views.download_lock),
    url(r'^ajax/check_access/$', views.check_access),
    url(r'^ajax/upload_job/(?P<parent_id>.*)/$', views.upload_job),

    # For psi
    url(r'^setstatus/$', views.psi_set_status),
    url(r'^downloadlock/$', views.download_lock),
    url(r'^decide_job/$', views.decide_job),
]
