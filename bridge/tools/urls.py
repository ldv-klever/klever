from django.conf.urls import url
from tools import views


urlpatterns = [
    url(r'^manager/$', views.manager_tools, name='manager'),
    url(r'^ajax/change_component/$', views.change_component),
    url(r'^ajax/clear_components_table/$', views.clear_components_table),
    url(r'^ajax/delete_problem/$', views.delete_problem),
    url(r'^ajax/clear_problems/$', views.clear_problems),
    url(r'^ajax/clear_system/$', views.clear_system),
    url(r'^ajax/recalculation/$', views.recalculation),
]
