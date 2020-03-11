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
from django.views.generic.base import TemplateView

from tools.profiling import LoggedCallMixin

from jobs.models import Scheduler
from service.models import Node
from service.utils import NodesData


class SchedulersInfoView(LoginRequiredMixin, LoggedCallMixin, TemplateView):
    template_name = 'service/scheduler.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['schedulers'] = Scheduler.objects.prefetch_related('verificationtool_set').all()
        context['data'] = NodesData()
        context['nodes'] = Node.objects.select_related('workload', 'config')
        return context
