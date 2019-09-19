#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

import json
from urllib.parse import unquote

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied

from django.urls import reverse
from django.utils.translation import ugettext as _
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin, DetailView


from tools.profiling import LoggedCallMixin
from bridge.vars import VIEW_TYPES, JOB_STATUS, PRIORITY, JOB_WEIGHT, USER_ROLES, JOB_ROLES, ERRORS
from bridge.utils import BridgeException
from bridge.CustomViews import DataViewMixin, StreamingResponseView

from users.models import User
from reports.utils import FilesForCompetitionArchive
from reports.coverage import JobCoverageStatistics

from jobs.models import Job, RunHistory, JobFile
from jobs.serializers import JobFormSerializerRO, get_view_job_data
from jobs.utils import months_choices, years_choices, JobDecisionData, JobAccess, CompareFileSet
from jobs.configuration import StartDecisionData
from jobs.ViewJobData import ViewJobData
from jobs.JobTableProperties import TableTree
from jobs.Download import JobFileGenerator, JobConfGenerator, JobArchiveGenerator, JobsArchivesGen, JobsTreesGen


class JobsTree(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, TemplateView):
    template_name = 'jobs/tree.html'

    def get_context_data(self, **kwargs):
        return {
            'users': User.objects.all(),
            'statuses': JOB_STATUS, 'weights': JOB_WEIGHT, 'priorities': list(reversed(PRIORITY)),
            'months': months_choices(), 'years': years_choices(),
            'TableData': TableTree(self.request.user, self.get_view(VIEW_TYPES[1]))
        }


class JobPage(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    model = Job
    template_name = 'jobs/viewJob/main.html'

    def get_queryset(self):
        queryset = super(JobPage, self).get_queryset()
        return queryset.select_related('author')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check view access
        context['job_access'] = JobAccess(self.request.user, self.object)
        if not context['job_access'].can_view:
            raise PermissionDenied(ERRORS[400])

        # Job data
        context.update(get_view_job_data(self.request.user, self.object))

        # Job verification results
        context['reportdata'] = ViewJobData(self.request.user, self.get_view(VIEW_TYPES[2]), self.object)

        # Job decision progress and other data
        context['decision'] = JobDecisionData(self.request, self.object)

        # Job coverages
        context['Coverage'] = JobCoverageStatistics(self.object)

        return context


class DecisionResults(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    model = Job
    template_name = 'jobs/DecisionResults.html'

    def get_context_data(self, **kwargs):
        return {'reportdata': ViewJobData(self.request.user, self.get_view(VIEW_TYPES[2]), self.object)}


class JobProgress(LoginRequiredMixin, LoggedCallMixin, DetailView):
    model = Job
    template_name = 'jobs/viewJob/decision.html'

    def get_context_data(self, **kwargs):
        return super().get_context_data(data=JobDecisionData(self.request, self.object), **kwargs)


class JobsFilesComparison(LoginRequiredMixin, LoggedCallMixin, TemplateView):
    template_name = 'jobs/comparison.html'

    def get_context_data(self, **kwargs):
        try:
            job1 = Job.objects.get(id=self.kwargs['job1_id'])
            job2 = Job.objects.get(id=self.kwargs['job2_id'])
        except ObjectDoesNotExist:
            raise BridgeException(code=405)
        if not JobAccess(self.request.user, job1).can_view or not JobAccess(self.request.user, job2).can_view:
            raise BridgeException(code=401)
        return {'job1': job1, 'job2': job2, 'data': CompareFileSet(job1, job2).data}


class JobFormPage(LoginRequiredMixin, LoggedCallMixin, DetailView):
    model = Job
    template_name = 'jobs/jobForm.html'

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object).can_view:
            raise BridgeException(code=400)
        context = super().get_context_data(**kwargs)
        context.update(JobFormSerializerRO(instance=self.object).data)
        context.update({'action': self.kwargs['action'], 'job_roles': JOB_ROLES})
        return context


class DownloadJobFileView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = JobFile
    slug_url_kwarg = 'hash_sum'
    slug_field = 'hash_sum'

    def get_filename(self):
        return unquote(self.request.GET.get('name', 'filename'))

    def get_generator(self):
        return JobFileGenerator(self.get_object())


class DownloadFilesForCompetition(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = Job

    def get_generator(self):
        instance = self.get_object()
        if not JobAccess(self.request.user, instance).can_download_verifier_input:
            raise BridgeException(code=400)
        if 'filters' not in self.request.GET:
            raise BridgeException()
        return FilesForCompetitionArchive(instance, json.loads(self.request.GET['filters']))


class DownloadJobView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = Job

    def get_generator(self):
        instance = self.get_object()
        if not JobAccess(self.request.user, instance).can_download:
            raise BridgeException(code=400)
        return JobArchiveGenerator(instance)


class DownloadJobsListView(LoginRequiredMixin, LoggedCallMixin, StreamingResponseView):
    def get_generator(self):
        jobs_qs = Job.objects.filter(pk__in=json.loads(unquote(self.request.GET['jobs'])))
        if not JobAccess(self.request.user).can_download_jobs(jobs_qs):
            raise BridgeException(_("You don't have an access to one of the selected jobs"), back=reverse('jobs:tree'))
        return JobsArchivesGen(jobs_qs)


class DownloadJobsTreeView(LoginRequiredMixin, LoggedCallMixin, StreamingResponseView):
    def get_generator(self):
        if self.request.user.role != USER_ROLES[2][0]:
            raise BridgeException(_("Only managers can download jobs trees"), back=reverse('jobs:tree'))
        return JobsTreesGen(json.loads(unquote(self.request.GET['jobs'])))


class PrepareDecisionView(LoggedCallMixin, DetailView):
    template_name = 'jobs/startDecision.html'
    model = Job

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['job'] = self.object
        context['current_conf'] = settings.DEF_KLEVER_CORE_MODE
        context['data'] = StartDecisionData(self.request.user)
        return context


class DownloadRunConfigurationView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = RunHistory

    def get_generator(self):
        instance = self.get_object()
        if not JobAccess(self.request.user, instance.job).can_view:
            raise BridgeException(code=400)
        return JobConfGenerator(instance)
