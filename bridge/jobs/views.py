#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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
from difflib import unified_diff
from wsgiref.util import FileWrapper

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _, override
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin, DetailView

import bridge.CustomViews as Bviews
from tools.profiling import LoggedCallMixin
from bridge.vars import VIEW_TYPES, JOB_STATUS, PRIORITY, JOB_WEIGHT, USER_ROLES
from bridge.utils import logger, file_get_or_create, extract_archive, get_templated_text,\
    BridgeException

from users.models import User
from reports.models import ReportComponent, ReportRoot
from reports.UploadReport import UploadReport, CollapseReports
from reports.comparison import can_compare
from reports.utils import FilesForCompetitionArchive
from service.utils import StartJobDecision, StopDecision, GetJobsProgresses
from users.utils import ViewData

import jobs.utils
from jobs.jobForm import JobForm, role_info, LoadFilesTree, UserRolesForm
import marks.SafeUtils as SafeUtils
from jobs.models import Job, RunHistory, JobHistory, JobFile, FileSystem
from jobs.ViewJobData import ViewJobData
from jobs.JobTableProperties import TableTree
from jobs.Download import UploadJob, JobArchiveGenerator, KleverCoreArchiveGen, JobsArchivesGen,\
    UploadReportsWithoutDecision, JobsTreesGen, UploadTree


@method_decorator(login_required, name='dispatch')
class JobsTree(LoggedCallMixin, TemplateView):
    template_name = 'jobs/tree.html'

    def get_context_data(self, **kwargs):
        return {
            'users': User.objects.all(),
            'statuses': JOB_STATUS, 'weights': JOB_WEIGHT, 'priorities': list(reversed(PRIORITY)),
            'months': jobs.utils.months_choices(), 'years': jobs.utils.years_choices(),
            'TableData': TableTree(self.request.user, ViewData(self.request.user, VIEW_TYPES[1][0], self.request.GET))
        }


@method_decorator(login_required, name='dispatch')
class JobPage(LoggedCallMixin, DetailView):
    model = Job
    template_name = 'jobs/viewJob.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        job_access = jobs.utils.JobAccess(self.request.user, self.object)
        if not job_access.can_view():
            raise BridgeException(code=400)

        versions = jobs.utils.JobVersionsData(self.object, self.request.user)
        if versions.first_version is not None:
            context['created_by'] = versions.first_version.change_author
        context['last_version'] = versions.last_version
        context['versions'] = versions.versions
        context['parents'] = jobs.utils.get_job_parents(self.request.user, self.object)
        context['children'] = jobs.utils.get_job_children(self.request.user, self.object)
        context['progress'] = GetJobsProgresses(self.request.user, [self.object.id]).data[self.object.id]
        context['reportdata'] = ViewJobData(
            self.request.user,
            ReportComponent.objects.filter(root__job=self.object, parent=None).first(),
            ViewData(self.request.user, VIEW_TYPES[2][0], self.request.GET)
        )

        context['job_access'] = job_access
        context['roles'] = role_info(context['last_version'], self.request.user)
        return context


class DecisionResults(LoggedCallMixin, Bviews.JSONResponseMixin, Bviews.DetailPostView):
    model = Job
    template_name = 'jobs/DecisionResults.html'

    def get_context_data(self, **kwargs):
        return {'reportdata': ViewJobData(
            self.request.user,
            ReportComponent.objects.filter(root__job=self.object, parent=None).first(),
            ViewData(self.request.user, VIEW_TYPES[2][0], self.request.POST)
        )}


class JobProgress(LoggedCallMixin, Bviews.JSONResponseMixin, DetailView):
    model = Job
    template_name = 'jobs/jobProgress.html'

    def get_context_data(self, **kwargs):
        return {'progress': GetJobsProgresses(self.request.user, [self.object.id]).data[self.object.id]}


class JobStatus(LoggedCallMixin, Bviews.JsonDetailPostView):
    model = Job

    def get_context_data(self, **kwargs):
        return {'status': self.object.status}


@method_decorator(login_required, name='dispatch')
class JobsFilesComparison(LoggedCallMixin, TemplateView):
    template_name = 'jobs/comparison.html'

    def get_context_data(self, **kwargs):
        try:
            job1 = Job.objects.get(id=self.kwargs['job1_id'])
            job2 = Job.objects.get(id=self.kwargs['job2_id'])
        except ObjectDoesNotExist:
            raise BridgeException(code=405)
        if not jobs.utils.JobAccess(self.request.user, job1).can_view() \
                or not jobs.utils.JobAccess(self.request.user, job2).can_view():
            raise BridgeException(code=401)
        return {'job1': job1, 'job2': job2, 'data': jobs.utils.CompareFileSet(job1, job2).data}


class RemoveJobsView(LoggedCallMixin, Bviews.JsonView):
    unparallel = [Job]

    def get_context_data(self, **kwargs):
        jobs.utils.remove_jobs_by_id(self.request.user, json.loads(self.request.POST.get('jobs', '[]')))
        return {}


class SaveJobCopyView(LoggedCallMixin, Bviews.JsonDetailPostView):
    model = Job
    unparallel = [Job]

    def get_context_data(self, **kwargs):
        newjob = jobs.utils.save_job_copy(self.request.user, self.object, self.request.POST.get('name'))
        return {'identifier': newjob.identifier, 'id': newjob.id}


class DecisionResultsJson(LoggedCallMixin, Bviews.JsonDetailView):
    model = Job

    def get_context_data(self, **kwargs):
        res = jobs.utils.GetJobDecisionResults(self.object)
        return {'data': json.dumps({
            'name': res.job.name, 'status': res.job.status,
            'start_date': res.start_date.timestamp() if res.start_date else None,
            'finish_date': res.finish_date.timestamp() if res.finish_date else None,
            'verdicts': res.verdicts, 'resources': res.resources,
            'safes': res.safes, 'unsafes': res.unsafes, 'unknowns': res.unknowns
        }, indent=2, sort_keys=True, ensure_ascii=False)}


@method_decorator(login_required, name='dispatch')
class JobFormPage(LoggedCallMixin, DetailView):
    model = Job
    template_name = 'jobs/jobForm.html'

    # TODO: only for post()
    unparallel = [Job]

    def post(self, *args, **kwargs):
        self.is_not_used(*args, **kwargs)
        try:
            return JsonResponse({
                'job_id': JobForm(self.request.user, self.get_object(), self.kwargs['action']).save(self.request.POST)
            })
        except BridgeException as e:
            raise BridgeException(str(e), response_type='json')
        except Exception as e:
            logger.exception(e)
            raise BridgeException(response_type='json')

    def get_context_data(self, **kwargs):
        if not jobs.utils.JobAccess(self.request.user, self.object).can_view():
            raise BridgeException(code=400)
        return JobForm(self.request.user, self.object, self.kwargs['action']).get_context()


class GetJobHistoryData(LoggedCallMixin, Bviews.JsonDetailView):
    model = JobHistory

    def get_object(self, queryset=None):
        try:
            obj = self.get_queryset().get(job_id=self.kwargs['job_id'], version=self.kwargs['version'])
        except ObjectDoesNotExist:
            raise BridgeException(_("The job version was not found"))
        if not jobs.utils.JobAccess(self.request.user, obj.job).can_view():
            raise BridgeException(code=400)
        return obj

    def get_context_data(self, **kwargs):
        return {'description': self.object.description}


class GetJobHistoryRoles(LoggedCallMixin, Bviews.JSONResponseMixin, DetailView):
    model = JobHistory
    template_name = 'jobs/userRolesForm.html'

    def get_object(self, queryset=None):
        try:
            obj = self.get_queryset().get(job_id=self.kwargs['job_id'], version=self.kwargs['version'])
        except ObjectDoesNotExist:
            raise BridgeException(_('Job version was not found'))
        if not jobs.utils.JobAccess(self.request.user, obj.job).can_view():
            raise BridgeException(code=400)
        return obj

    def get_context_data(self, **kwargs):
        return UserRolesForm(self.request.user, self.object).get_context()


class GetJobHistoryFiles(LoggedCallMixin, Bviews.JsonView):
    def get_context_data(self, **kwargs):
        return LoadFilesTree(self.kwargs['job_id'], self.kwargs['version']).as_json()


@method_decorator(login_required, name='dispatch')
class DownloadJobFileView(LoggedCallMixin, SingleObjectMixin, Bviews.StreamingResponseView):
    model = JobFile
    slug_url_kwarg = 'hash_sum'
    slug_field = 'hash_sum'

    def get_filename(self):
        return unquote(self.request.GET.get('name', 'filename'))

    def get_generator(self):
        self.object = self.get_object()
        self.file_size = len(self.object.file)
        return FileWrapper(self.object.file, 8192)


class UploadJobFileView(LoggedCallMixin, Bviews.JsonView):
    unparallel = [JobFile]

    def get_context_data(self, **kwargs):
        fname = self.request.FILES['file'].name
        if not all(ord(c) < 128 for c in fname):
            title_size = len(fname)
            if title_size > 30:
                fname = fname[(title_size - 30):]
        return {'hashsum': file_get_or_create(self.request.FILES['file'], fname, JobFile, True)[1]}


class GetFileContentView(LoggedCallMixin, Bviews.JsonDetailView):
    model = JobFile
    slug_url_kwarg = 'hashsum'
    slug_field = 'hash_sum'

    def get_context_data(self, **kwargs):
        return {'content': self.object.file.read().decode('utf8')}


class GetFilesDiffView(LoggedCallMixin, Bviews.JsonView):
    def get_context_data(self, **kwargs):
        try:
            f1 = jobs.utils.JobFile.objects.get(hash_sum=self.kwargs['hashsum1'])
            f2 = jobs.utils.JobFile.objects.get(hash_sum=self.kwargs['hashsum2'])
        except ObjectDoesNotExist:
            raise BridgeException(_("The file was not found"))
        with f1.file as fp1, f2.file as fp2:
            lines1 = fp1.read().decode('utf8').split('\n')
            lines2 = fp2.read().decode('utf8').split('\n')
            name1 = self.request.POST.get('name1', 'Old')
            name2 = self.request.POST.get('name2', 'Old')
            return {'content': '\n'.join(list(unified_diff(lines1, lines2, fromfile=name1, tofile=name2)))}


class ReplaceJobFileView(LoggedCallMixin, Bviews.JsonView):
    unparallel = [FileSystem]

    def get_context_data(self, **kwargs):
        jobs.utils.ReplaceJobFile(self.kwargs['job_id'], self.request.POST['name'], self.request.FILES['file'])
        return {}


@method_decorator(login_required, name='dispatch')
class DownloadFilesForCompetition(LoggedCallMixin, SingleObjectMixin, Bviews.StreamingResponsePostView):
    model = Job

    def get_generator(self):
        self.object = self.get_object()
        if not jobs.utils.JobAccess(self.request.user, self.object).can_dfc():
            raise BridgeException(code=400)
        generator = FilesForCompetitionArchive(self.object, json.loads(self.request.POST['filters']))
        self.file_name = generator.name
        return generator


@method_decorator(login_required, name='dispatch')
class DownloadJobView(LoggedCallMixin, SingleObjectMixin, Bviews.StreamingResponseView):
    model = Job

    def get_generator(self):
        self.object = self.get_object()
        if not jobs.utils.JobAccess(self.request.user, self.object).can_download():
            raise BridgeException(code=400)
        generator = JobArchiveGenerator(self.object)
        self.file_name = generator.arcname
        return generator


@method_decorator(login_required, name='dispatch')
class DownloadJobsListView(LoggedCallMixin, Bviews.StreamingResponsePostView):
    def get_generator(self):
        jobs_list = Job.objects.filter(pk__in=json.loads(self.request.POST['job_ids']))
        for job in jobs_list:
            if not jobs.utils.JobAccess(self.request.user, job).can_download():
                raise BridgeException(
                    _("You don't have an access to one of the selected jobs"), back=reverse('jobs:tree'))
        self.file_name = 'KleverJobs.zip'
        return JobsArchivesGen(jobs_list)


@method_decorator(login_required, name='dispatch')
class DownloadJobsTreeView(LoggedCallMixin, Bviews.StreamingResponsePostView):
    def get_generator(self):
        if self.request.user.extended.role != USER_ROLES[2][0]:
            raise BridgeException(_("Only managers can download jobs trees"), back=reverse('jobs:tree'))
        self.file_name = 'KleverJobs.zip'
        return JobsTreesGen(json.loads(self.request.POST['job_ids']))


class UploadJobsView(LoggedCallMixin, Bviews.JsonView):
    unparallel = [Job]

    def get_context_data(self, **kwargs):
        if not jobs.utils.JobAccess(self.request.user).can_create():
            raise BridgeException(_("You don't have an access to upload jobs"))
        parent = jobs.utils.get_job_by_identifier(self.kwargs['parent_id'])
        for f in self.request.FILES.getlist('file'):
            try:
                job_dir = extract_archive(f)
            except Exception as e:
                logger.exception(e)
                raise BridgeException(_('Extraction of the archive "%(arcname)s" has failed') % {'arcname': f.name})
            try:
                UploadJob(parent, self.request.user, job_dir.name)
            except BridgeException as e:
                raise BridgeException(_('Creating the job from archive "%(arcname)s" failed: %(message)s') % {
                    'arcname': f.name, 'message': str(e)
                })
            except Exception as e:
                logger.exception(e)
                raise BridgeException(_('Creating the job from archive "%(arcname)s" failed: %(message)s') % {
                    'arcname': f.name, 'message': _('The job archive is corrupted')
                })
        return {}


class UploadJobsTreeView(LoggedCallMixin, Bviews.JsonView):
    unparallel = [Job]

    def get_context_data(self, **kwargs):
        if self.request.user.extended.role != USER_ROLES[2][0]:
            raise BridgeException(_("You don't have an access to upload jobs tree"))
        if Job.objects.filter(status__in=[JOB_STATUS[1][0], JOB_STATUS[2][0]]).count() > 0:
            raise BridgeException(_("There are jobs in progress right now, uploading may corrupt it results. "
                                    "Please wait until it will be finished."))

        jobs_dir = extract_archive(self.request.FILES['file'])
        UploadTree(self.request.POST['parent_id'], self.request.user, jobs_dir.name)
        return {}


class RemoveJobVersions(LoggedCallMixin, Bviews.JsonDetailPostView):
    model = Job
    unparallel = ['Job', JobHistory]

    def get_context_data(self, **kwargs):
        if not jobs.utils.JobAccess(self.request.user, self.object).can_edit():
            raise BridgeException(code=400)
        jobs.utils.delete_versions(self.object, json.loads(self.request.POST.get('versions', '[]')))
        return {'message': _('Selected versions were successfully deleted')}


class CompareJobVersionsView(LoggedCallMixin, Bviews.JSONResponseMixin, Bviews.DetailPostView):
    model = Job
    template_name = 'jobs/jobVCmp.html'

    def get_context_data(self, **kwargs):
        versions = [int(self.request.POST['v1']), int(self.request.POST['v2'])]
        job_versions = JobHistory.objects.filter(job=self.object, version__in=versions).order_by('change_date')
        if job_versions.count() != 2:
            raise BridgeException(_('The page is outdated, reload it please'))
        return {'data': jobs.utils.CompareJobVersions(*list(job_versions))}


class CopyJobVersionView(LoggedCallMixin, Bviews.JsonDetailView):
    model = Job
    unparallel = [Job]

    def get_context_data(self, **kwargs):
        if not jobs.utils.JobAccess(self.request.user, self.object).can_edit():
            raise BridgeException(code=400)
        jobs.utils.copy_job_version(self.request.user, self.object)
        return {}


class PrepareDecisionView(LoggedCallMixin, TemplateView):
    template_name = 'jobs/startDecision.html'

    def get_context_data(self, **kwargs):
        try:
            job = Job.objects.get(pk=int(self.kwargs['job_id']))
        except ObjectDoesNotExist:
            raise BridgeException(code=404)

        current_conf = settings.DEF_KLEVER_CORE_MODE
        configuration = None

        if self.request.method == 'POST':
            current_conf = self.request.POST.get('conf_name', current_conf)
            if current_conf == 'file_conf':
                if 'file_conf' not in self.request.FILES:
                    raise BridgeException(code=301)
                configuration = jobs.utils.GetConfiguration(
                    file_conf=json.loads(self.request.FILES['file_conf'].read().decode('utf8'))
                ).configuration

        if configuration is None:
            configuration = jobs.utils.GetConfiguration(conf_name=current_conf).configuration

        return {
            'job': job, 'current_conf': current_conf,
            'configurations': jobs.utils.get_default_configurations(),
            'data': jobs.utils.StartDecisionData(self.request.user, configuration)
        }


@method_decorator(login_required, name='dispatch')
class DownloadRunConfigurationView(LoggedCallMixin, SingleObjectMixin, Bviews.StreamingResponseView):
    model = RunHistory

    def get_generator(self):
        self.object = self.get_object()
        if not jobs.utils.JobAccess(self.request.user, self.object.job).can_view():
            raise BridgeException(code=400)
        self.file_name = "job-%s.conf" % self.object.job.identifier[:5]
        self.file_size = len(self.object.configuration.file)
        return FileWrapper(self.object.configuration.file, 8192)


class GetDefStartJobValue(LoggedCallMixin, Bviews.JsonView):
    def get_context_data(self, **kwargs):
        name = self.request.POST['name']
        value = self.request.POST['value']

        if name == 'formatter' and value in settings.KLEVER_CORE_LOG_FORMATTERS:
            return {'value': settings.KLEVER_CORE_LOG_FORMATTERS[value]}

        parallelism_names = ['sub_jobs_proc_parallelism', 'build_parallelism',
                             'tasks_gen_parallelism', 'results_processing_parallelism']
        for i in range(len(parallelism_names)):
            if name == parallelism_names[i] and value in settings.KLEVER_CORE_PARALLELISM_PACKS:

                return {'value': get_templated_text(
                    '{% load l10n %}{{ val|localize }}', val=settings.KLEVER_CORE_PARALLELISM_PACKS[value][i]
                )}
        raise BridgeException()


class StartDecision(LoggedCallMixin, Bviews.JsonView):
    unparallel = [Job]

    def get_context_data(self, **kwargs):
        getconf_args = {}

        if self.request.POST['mode'] == 'data':
            getconf_args['user_conf'] = json.loads(self.request.POST['data'])
        elif self.request.POST['mode'] == 'fast':
            getconf_args['conf_name'] = settings.DEF_KLEVER_CORE_MODE
        elif self.request.POST['mode'] == 'lastconf':
            last_run = RunHistory.objects.filter(job_id=self.kwargs['job_id']).order_by('date').last()
            if last_run is None:
                raise BridgeException(_('The job was not decided before'))
            with last_run.configuration.file as fp:
                getconf_args['file_conf'] = json.loads(fp.read().decode('utf8'))

        StartJobDecision(
            self.request.user, self.kwargs['job_id'], jobs.utils.GetConfiguration(**getconf_args).configuration
        )
        return {}


class StopDecisionView(LoggedCallMixin, Bviews.JsonDetailPostView):
    model = Job
    unparallel = [Job]

    def get_context_data(self, **kwargs):
        if not jobs.utils.JobAccess(self.request.user, self.object).can_stop():
            raise BridgeException(_("You don't have an access to stop decision of this job"))
        StopDecision(self.object)
        return {}


class DecideJobServiceView(LoggedCallMixin, SingleObjectMixin,
                           Bviews.JSONResponseMixin, Bviews.StreamingResponsePostView):
    model = Job
    unparallel = [Job]

    def dispatch(self, request, *args, **kwargs):
        with override(settings.DEFAULT_LANGUAGE):
            return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        return queryset.get(id=int(self.request.session['job id']), format=int(self.request.POST['job format']))

    def get_generator(self):
        self.object = self.get_object()

        if 'job format' not in self.request.POST:
            raise BridgeException('Job format is not specified')
        if 'report' not in self.request.POST:
            raise BridgeException('Start report is not specified')

        attempt = int(self.request.POST.get('attempt', 0))
        if not jobs.utils.JobAccess(self.request.user, self.object).klever_core_access():
            raise BridgeException('User "{0}" doesn\'t have access to decide the job "{1}"'
                                  .format(self.request.user, self.object.identifier))
        if attempt == 0:
            if self.object.status != JOB_STATUS[1][0]:
                raise BridgeException('Only pending jobs can be decided')
            jobs.utils.change_job_status(self.object, JOB_STATUS[2][0])

        err = UploadReport(self.object, json.loads(self.request.POST.get('report', '{}')), attempt=attempt).error
        if err is not None:
            raise BridgeException(err)

        generator = KleverCoreArchiveGen(self.object)
        self.file_name = generator.arcname
        return generator


class GetJobFieldView(Bviews.JsonView):
    def get_context_data(self, **kwargs):
        job = jobs.utils.get_job_by_name_or_id(self.request.POST['job'])
        return {self.request.POST['field']: getattr(job, self.request.POST['field'])}


class DoJobHasChildrenView(LoggedCallMixin, Bviews.JsonDetailPostView):
    model = Job

    def get_context_data(self, **kwargs):
        return {'children': (self.object.children.count() > 0)}


class CheckDownloadAccessView(LoggedCallMixin, Bviews.JsonView):
    def get_context_data(self, **kwargs):
        for job_id in json.loads(self.request.POST.get('jobs', '[]')):
            try:
                job = Job.objects.get(id=int(job_id))
            except ObjectDoesNotExist:
                raise BridgeException(code=405)
            if not jobs.utils.JobAccess(self.request.user, job).can_download():
                raise BridgeException(code=401)
        return {}


class CheckCompareAccessView(LoggedCallMixin, Bviews.JsonView):
    def get_context_data(self, **kwargs):
        try:
            j1 = Job.objects.get(id=self.request.POST.get('job1', 0))
            j2 = Job.objects.get(id=self.request.POST.get('job2', 0))
        except ObjectDoesNotExist:
            raise BridgeException(code=405)
        if not can_compare(self.request.user, j1, j2):
            raise BridgeException(code=401)
        return {}


class JobProgressJson(LoggedCallMixin, Bviews.JsonDetailPostView):
    model = Job

    def get_context_data(self, **kwargs):
        try:
            progress = self.object.jobprogress
            solving = self.object.solvingprogress
        except ObjectDoesNotExist:
            return {'data': json.dumps({'status': self.object.status})}

        return {'data': json.dumps({
            'status': self.object.status,
            'subjobs': {
                'total': progress.total_sj, 'failed': progress.failed_sj, 'solved': progress.solved_sj,
                'expected_time': progress.expected_time_sj, 'gag_text': progress.gag_text_sj,
                'start': progress.start_sj.timestamp() if progress.start_sj else None,
                'finish': progress.finish_sj.timestamp() if progress.finish_sj else None
            },
            'tasks': {
                'total': progress.total_ts, 'failed': progress.failed_ts, 'solved': progress.solved_ts,
                'expected_time': progress.expected_time_ts, 'gag_text': progress.gag_text_ts,
                'start': progress.start_ts.timestamp() if progress.start_ts else None,
                'finish': progress.finish_ts.timestamp() if progress.finish_ts else None
            },
            'start_date': solving.start_date.timestamp() if solving.start_date else None,
            'finish_date': solving.finish_date.timestamp() if solving.finish_date else None
        }, indent=2, sort_keys=True, ensure_ascii=False)}


class UploadReportsView(LoggedCallMixin, Bviews.JsonDetailPostView):
    model = Job
    unparallel = [Job]

    def get_context_data(self, **kwargs):
        if not jobs.utils.JobAccess(self.request.user, self.object).can_decide():
            raise BridgeException(_("You don't have an access to upload reports for this job"))

        try:
            reports_dir = extract_archive(self.request.FILES['archive'])
        except Exception as e:
            logger.exception(e)
            raise BridgeException(_('Extraction of the archive has failed'))

        UploadReportsWithoutDecision(self.object, self.request.user, reports_dir.name)
        return {}


class CollapseReportsView(LoggedCallMixin, Bviews.JsonDetailPostView):
    model = Job
    unparallel = [Job]

    def get_context_data(self, **kwargs):
        if not jobs.utils.JobAccess(self.request.user, self.object).can_collapse():
            raise BridgeException(_("You don't have an access to collapse reports"))
        CollapseReports(self.object)
        return {}


class EnableSafeMarks(LoggedCallMixin, Bviews.JsonDetailPostView):
    model = Job
    unparallel = [Job]

    def get_context_data(self, **kwargs):
        if not jobs.utils.JobAccess(self.request.user, self.object).can_edit():
            raise BridgeException(_("You don't have an access to edit this job"))

        self.object.safe_marks = not self.object.safe_marks
        self.object.save()
        try:
            root = ReportRoot.objects.get(job=self.object)
        except ObjectDoesNotExist:
            pass
        else:
            if self.object.safe_marks:
                SafeUtils.RecalculateConnections([root])
            else:
                SafeUtils.disable_safe_marks_for_job(root)
        return {}
