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

import json
from urllib.parse import unquote

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import ugettext as _
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin, DetailView
from django.views.generic.list import ListView


from tools.profiling import LoggedCallMixin
from bridge.vars import VIEW_TYPES, DECISION_STATUS, PRIORITY, DECISION_WEIGHT, JOB_ROLES, ERRORS
from bridge.utils import BridgeException
from bridge.CustomViews import DataViewMixin, StreamingResponseView

from users.models import User
from service.models import Decision
from reports.utils import FilesForCompetitionArchive
from reports.coverage import DecisionCoverageStatistics

from jobs.models import PRESET_JOB_TYPE, Job, JobFile, UploadedJobArchive, PresetJob, FileSystem, UserRole
from jobs.utils import (
    months_choices, years_choices, is_preset_changed, get_unique_name, get_roles_form_data,
    JobAccess, DecisionAccess, CompareFileSet, JSTreeConverter, get_core_link
)
from jobs.configuration import StartDecisionData
from jobs.ViewJobData import ViewJobData
from jobs.JobTableProperties import JobsTreeTable, PresetChildrenTree
from jobs.Download import (
    JobFileGenerator, DecisionConfGenerator, JobArchiveGenerator, JobsArchivesGen, get_jobs_to_download
)
from jobs.preset import get_preset_dir_list, preset_job_files_tree_json
from service.serializers import ProgressSerializerRO


class JobsTree(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, TemplateView):
    template_name = 'jobs/tree.html'

    def get_context_data(self, **kwargs):
        return {
            'users': User.objects.all(),
            'can_create': self.request.user.can_create_jobs,
            'statuses': DECISION_STATUS[1:], 'weights': DECISION_WEIGHT,
            'priorities': list(reversed(PRIORITY)),
            'months': months_choices(), 'years': years_choices(),
            'TableData': JobsTreeTable(self.get_view(VIEW_TYPES[1]))
        }


class PresetJobPage(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    template_name = 'jobs/presetJob.html'
    model = PresetJob

    def get_context_data(self, **kwargs):
        context = super(PresetJobPage, self).get_context_data(**kwargs)
        context.update({
            'can_create': self.request.user.can_create_jobs,
            'children': PresetChildrenTree(self.object).children,
            'files': preset_job_files_tree_json(self.object)
        })
        return context


class PresetFormPage(LoginRequiredMixin, LoggedCallMixin, TemplateView):
    template_name = 'jobs/jobCreateForm.html'

    def get_context_data(self, **kwargs):
        if not self.request.user.can_create_jobs:
            raise BridgeException(code=407)
        preset_job = get_object_or_404(PresetJob.objects.exclude(type=PRESET_JOB_TYPE[0][0]), pk=self.kwargs['pk'])
        return {
            'title': _('Job Creating'), 'job_roles': JOB_ROLES, 'cancel_url': reverse('jobs:tree'),
            'initial': {
                'name': get_unique_name(preset_job.name),
                'preset_dirs': get_preset_dir_list(preset_job),
                'files': preset_job_files_tree_json(preset_job),
                'roles': json.dumps(get_roles_form_data(), ensure_ascii=False),
            }
        }


class CopyJobFormPage(LoginRequiredMixin, LoggedCallMixin, DetailView):
    model = Job
    template_name = 'jobs/jobCreateForm.html'

    def get_context_data(self, **kwargs):
        if not self.request.user.can_create_jobs:
            raise BridgeException(code=407)
        if not JobAccess(self.request.user, self.object).can_view:
            raise BridgeException(code=400)

        return {
            'title': _('Job Copying'), 'job_roles': JOB_ROLES,
            'cancel_url': reverse('jobs:job', args=[self.object.id]),
            'base_job': self.object,
            'initial': {
                'name': get_unique_name(self.object.name),
                'preset_dirs': get_preset_dir_list(self.object.preset),
                'files': json.dumps(JSTreeConverter().make_tree(
                    list(FileSystem.objects.filter(job=self.object).values_list('name', 'file__hash_sum'))
                ), ensure_ascii=False),
                'roles': json.dumps(get_roles_form_data(self.object), ensure_ascii=False),
            }
        }


class EditJobFormPage(LoginRequiredMixin, LoggedCallMixin, DetailView):
    model = Job
    template_name = 'jobs/jobEditForm.html'

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object).can_edit:
            raise BridgeException(code=400)
        return {
            'job': self.object, 'title': _('Job Editing'), 'job_roles': JOB_ROLES,
            'cancel_url': reverse('jobs:job', args=[self.object.id]),
            'initial': {
                'name': self.object.name,
                'preset_dirs': get_preset_dir_list(self.object.preset),
                'files': json.dumps(JSTreeConverter().make_tree(
                    list(FileSystem.objects.filter(job=self.object).values_list('name', 'file__hash_sum'))
                ), ensure_ascii=False),
                'roles': json.dumps(get_roles_form_data(self.object), ensure_ascii=False),
            }
        }


class JobPage(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    model = Job
    template_name = 'jobs/jobPage.html'

    def get_queryset(self):
        queryset = super(JobPage, self).get_queryset()
        return queryset.select_related('author')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check view access
        context['job_access'] = JobAccess(self.request.user, self.object)
        if not context['job_access'].can_view:
            raise PermissionDenied(ERRORS[400])
        context['parents'] = self.object.preset.get_ancestors(include_self=True).only('id', 'name', 'type')
        context['files'] = json.dumps(JSTreeConverter().make_tree(
            list(FileSystem.objects.filter(job=self.object).values_list('name', 'file__hash_sum'))
        ), ensure_ascii=False)
        context['user_roles'] = UserRole.objects.filter(job=self.object).select_related('user')\
            .order_by('user__first_name', 'user__last_name', 'user__username')
        context['preset_changed'] = is_preset_changed(self.object)
        context['decisions'] = Decision.objects.filter(job=self.object).select_related('configuration').order_by('id')
        return context


class PrepareDecisionView(LoggedCallMixin, DetailView):
    template_name = 'jobs/startDecision.html'
    model = Job

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['job'] = self.object
        context['current_conf'] = settings.DEF_KLEVER_CORE_MODE
        context['data'] = StartDecisionData(self.request.user)
        if self.request.GET.get('base_job'):
            context['decisions'] = Decision.objects.filter(job_id=self.request.GET['base_job'])\
                .order_by('id').only('id', 'start_date', 'title')
        else:
            context['decisions'] = Decision.objects.filter(job=self.object).order_by('id')\
                .only('id', 'title', 'start_date')
        return context


class JobsFilesComparison(LoginRequiredMixin, LoggedCallMixin, TemplateView):
    template_name = 'jobs/comparison.html'

    def get_context_data(self, **kwargs):
        try:
            job1 = Job.objects.get(id=self.kwargs['job1_id'])
            job2 = Job.objects.get(id=self.kwargs['job2_id'])
        except Job.DoesNotExist:
            raise BridgeException(code=405)
        if not JobAccess(self.request.user, job1).can_view or not JobAccess(self.request.user, job2).can_view:
            raise BridgeException(code=401)
        return {'job1': job1, 'job2': job2, 'data': CompareFileSet(job1, job2).data}


class DownloadJobFileView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = JobFile
    slug_url_kwarg = 'hash_sum'
    slug_field = 'hash_sum'

    def get_filename(self):
        return unquote(self.request.GET.get('name', 'filename'))

    def get_generator(self):
        return JobFileGenerator(self.get_object())


class DownloadConfigurationView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    def get_queryset(self):
        return Decision.objects.select_related('configuration')

    def get_generator(self):
        instance = self.get_object()
        if not JobAccess(self.request.user, instance.job).can_view:
            raise BridgeException(code=400)
        return DecisionConfGenerator(instance)


class JobsUploadingStatus(LoginRequiredMixin, LoggedCallMixin, ListView):
    template_name = 'jobs/UploadingStatus.html'

    def get_queryset(self):
        return UploadedJobArchive.objects.filter(author=self.request.user).select_related('job').order_by('-start_date')


class DownloadFilesForCompetition(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = Decision

    def get_generator(self):
        decision = self.get_object()
        if not DecisionAccess(self.request.user, decision).can_download_verifier_files:
            raise BridgeException(code=400)
        if 'filters' not in self.request.GET:
            raise BridgeException()
        return FilesForCompetitionArchive(decision, json.loads(self.request.GET['filters']))


class DecisionProgress(LoginRequiredMixin, LoggedCallMixin, DetailView):
    model = Decision
    template_name = 'jobs/viewDecision/progress.html'

    def get_context_data(self, **kwargs):
        context = super(DecisionProgress, self).get_context_data(**kwargs)
        # Decision progress and core report link
        context['decision'] = self.object
        context['progress'] = ProgressSerializerRO(instance=self.object, context={'request': self.request}).data
        context['core_link'] = get_core_link(self.object)
        return context


class DecisionPage(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    model = Decision
    template_name = 'jobs/viewDecision/main.html'

    def get_queryset(self):
        queryset = super(DecisionPage, self).get_queryset()
        return queryset.select_related('job', 'job__author', 'operator', 'scheduler')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Decision access
        context['access'] = DecisionAccess(self.request.user, self.object)
        if not context['access'].can_view:
            raise PermissionDenied(ERRORS[400])

        # Other job decisions
        context['other_decisions'] = Decision.objects.filter(job=self.object.job)\
            .exclude(id=self.object.id).select_related('configuration').order_by('id')

        # Decision progress and core report link
        context['progress'] = ProgressSerializerRO(instance=self.object, context={'request': self.request}).data
        context['core_link'] = get_core_link(self.object)

        # Decision coverages
        context['Coverage'] = DecisionCoverageStatistics(self.object)

        # Verification results
        context['reportdata'] = ViewJobData(self.request.user, self.get_view(VIEW_TYPES[2]), self.object)

        return context


class DecisionResults(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    model = Decision
    template_name = 'jobs/DecisionResults.html'

    def get_context_data(self, **kwargs):
        return {'reportdata': ViewJobData(self.request.user, self.get_view(VIEW_TYPES[2]), self.object)}


class DownloadJobView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = Job

    def get_generator(self):
        instance = self.get_object()
        decisions_ids = self.request.GET.getlist('decision')
        if decisions_ids:
            for decision in Decision.objects.filter(job=instance, id__in=decisions_ids).select_related('job'):
                if not DecisionAccess(self.request.user, decision).can_download:
                    raise BridgeException(code=408, back=reverse('jobs:job', args=[instance.id]))
            return JobArchiveGenerator(instance, decisions_ids)
        if not JobAccess(self.request.user, instance).can_download:
            raise BridgeException(code=400, back=reverse('jobs:job', args=[instance.id]))
        return JobArchiveGenerator(instance)


class DownloadJobsListView(LoginRequiredMixin, LoggedCallMixin, StreamingResponseView):
    def get_generator(self):
        jobs_to_download = get_jobs_to_download(
            self.request.user,
            json.loads(unquote(self.request.GET['jobs'])),
            json.loads(unquote(self.request.GET['decisions']))
        )
        return JobsArchivesGen(jobs_to_download)
