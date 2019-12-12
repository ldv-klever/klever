#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
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

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, DetailView

from users.forms import BridgeAuthForm, RegisterForm, EditProfileForm, SchedulerUserForm
from users.models import User, SchedulerUser
from users.utils import UserActionsHistory


class BridgeLoginView(LoginView):
    template_name = 'users/login.html'
    success_url = reverse_lazy('jobs:tree')
    authentication_form = BridgeAuthForm


class BridgeLogoutView(LogoutView):
    next_page = 'users:login'


class UserRegisterView(CreateView):
    form_class = RegisterForm
    success_url = reverse_lazy('users:login')
    template_name = 'users/register.html'


class EditProfileView(LoginRequiredMixin, UpdateView):
    form_class = EditProfileForm
    template_name = 'users/edit-profile.html'
    success_url = reverse_lazy('users:edit-profile')

    def get_object(self, queryset=None):
        return self.request.user

    def get_sch_form(self):
        sch_kwargs = {'initial': {}, 'prefix': 'sch'}
        if self.request.method in ('POST', 'PUT'):
            sch_kwargs.update({'data': self.request.POST})
        if hasattr(self, 'object'):
            try:
                sch_inst = SchedulerUser.objects.get(user=self.object)
            except SchedulerUser.DoesNotExist:
                sch_inst = SchedulerUser(user=self.object)
            sch_kwargs.update({'instance': sch_inst})
        return SchedulerUserForm(**sch_kwargs)

    def get_context_data(self, **kwargs):
        if 'sch_form' not in kwargs:
            kwargs['sch_form'] = self.get_sch_form()
        return super().get_context_data(**kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        sch_form = self.get_sch_form()
        if form.is_valid() and sch_form.is_valid():
            self.object = form.save()
            sch_form.save()
            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.render_to_response(self.get_context_data(form=form, sch_form=sch_form))


class UserProfileView(LoginRequiredMixin, DetailView):
    model = User
    pk_url_kwarg = 'user_id'
    template_name = 'users/showProfile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['activity'] = UserActionsHistory(self.request.user, self.object).activity
        return context
