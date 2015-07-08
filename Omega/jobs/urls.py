from django.conf.urls import url
from jobs import views


urlpatterns = [
    # Examples:
    # url(r'^$', 'Omega.views.home', name='home'),
    # url(r'^blog/', include('blog.urls')),
    url(r'^$', views.tree_view, name='tree'),
    # url(r'^create/$', views.create_job, name='create'),
    url(r'^jobtable/$', views.get_jobtable),
    url(r'^ajax/save_view/$', views.save_view),
    url(r'^ajax/change_preferable/$', views.change_preferable),
    url(r'^ajax/remove_view/$', views.remove_view)
]
