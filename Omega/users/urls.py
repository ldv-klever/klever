from django.conf.urls import url
from users import views


urlpatterns = [
    url(r'^signin/$', views.user_signin, name='login'),
    url(r'^signout/$', views.user_signout, name='logout'),
    url(r'^register/$', views.register, name='register'),
    url(r'^edit/$', views.edit_profile, name='edit_profile'),
    url(r'^profile/(?P<user_id>[0-9]+)$', views.show_profile,
        name='show_profile'),
    url(r'^service_signin/$', views.service_signin),
    url(r'^service_signout/$', views.service_signout),

    url(r'^ajax/save_notifications/$', views.save_notifications),
]
