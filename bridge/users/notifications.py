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
import smtplib
from email.mime.text import MIMEText

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.translation import gettext_lazy as _, activate

from bridge.vars import JOB_ROLES, USER_ROLES
from bridge.utils import logger

from users.models import User
from jobs.models import Job

SUBJECTS = {
    0: _("New job was created"),
    1: _("Job was changed"),
    2: _("Job was deleted"),
    3: _("Job decision has started"),
    4: _("Job decision has finished"),
    5: _("New unsafe was found"),
    6: _("New unknown was found"),
    7: _("Mark was associated with leaf report"),
    8: _("New mark was created"),
    9: _("Mark was changed"),
    10: _("Mark was deleted"),
}

MESSAGES = {
    0: [
        _('The job <a href="%(url)s">%(id)s</a> was created by %(user)s'),
        _('The job with identifier %(id)s was created by %(user)s')
    ],
    1: [
        _('The job <a href="%(url)s">%(id)s</a> was changed by '
          '%(user)s: %(comm)s'),
        _('The job with identifier %(id)s was changed by %(user)s: %(comm)s')
    ],
    2: _("The job with identifier %(id)s was deleted by %(user)s"),
    3: _("Started decision of the job with identifier %(id)s"),
    4: _("Finished decision of the job with identifier %(id)s"),
    5: _("Found the new unsafe for the job with identifier %(id)s"),
    6: _("Found the new unknown for the job with identifier %(id)s"),
    7: _("Mark was associated with leaf report"),
    8: _("New mark was created"),
    9: _("Mark was changed"),
    10: _("Mark was deleted"),
}


class Notify(object):
    def __init__(self, job, ntf_type, add_args=None):
        self.server = 'motor.intra.ispras.ru'
        self.email = 'klever-bridge-noreply@ispras.ru'
        self.type = ntf_type
        self.job = job
        if isinstance(job, Job):
            self.__notify(add_args)

    def __notify(self, add_args):
        try:
            s = smtplib.SMTP(self.server)
        except Exception as e:
            # TODO: analize exception
            logger.exception("SMTP registration error: %s" % e)
            return
        for user in User.objects.filter(~Q(notifications__settings='[]') & ~Q(notifications=None)):
            if user.email is not None and len(user.email) > 0:
                message = UserMessage(
                    user, self.job, self.type, add_args).message
                activate(user.language)
                if isinstance(message, MIMEText):
                    message['From'] = self.email
                    try:
                        s.send_message(message)
                    except Exception as e:
                        logger.exception("send_message() error: %s" % e, stack_info=True)
        s.quit()


class UserMessage:

    def __init__(self, user, job, ntf_type, add_args):
        self.user = user
        self.args = add_args
        try:
            self.type = int(ntf_type)
        except ValueError:
            return
        self.is_producer = False
        self.is_operator = False
        self.is_observer = False
        self.is_expert = False
        self.is_manager = (self.user.role == USER_ROLES[2][0])
        self.change_user = None
        self.__get_job_prop(job)
        self.message = self.__get_message(job)

    def __get_job_prop(self, job):
        try:
            last_version = job.versions.get(version=job.version)
        except ObjectDoesNotExist:
            return None

        self.is_producer = (self.user == job.author)
        self.change_user = last_version.change_author

        try:
            job_role = last_version.userrole_set.get(user=self.user).role
        except ObjectDoesNotExist:
            job_role = last_version.global_role

        if job_role == JOB_ROLES[1][0]:
            self.is_observer = True
        elif job_role == JOB_ROLES[2][0]:
            self.is_expert = True
        elif job_role == JOB_ROLES[3][0]:
            self.is_observer = True
            self.is_operator = True
        elif job_role == JOB_ROLES[4][0]:
            self.is_expert = True
            self.is_operator = True

    def __get_message(self, job):
        if self.type not in MESSAGES:
            return None

        try:
            self_notify = self.user.notifications.self_ntf
            settings = json.loads(self.user.notifications.settings)
        except ObjectDoesNotExist:
            return None

        if self.change_user == self.user and not self_notify:
            return None

        if self.type == 0:
            if self.args is not None and 'absurl' in self.args:
                msg = MESSAGES[0][0] % {
                    'url': self.args['absurl'],
                    'id': job.identifier,
                    'user': self.change_user.get_full_name()
                }
            else:
                msg = MESSAGES[0][1] % {
                    'id': job.identifier,
                    'user': self.change_user.get_full_name()
                }
        elif self.type == 1:
            if self.args is not None and 'absurl' in self.args:
                msg = MESSAGES[1][0] % {
                    'url': self.args['absurl'],
                    'id': job.identifier,
                    'user': self.change_user.get_full_name(),
                    'comm': job.versions.get(version=job.version).comment
                }
            else:
                msg = MESSAGES[1][1] % {
                    'id': job.identifier,
                    'user': self.change_user.get_full_name(),
                    'comm': job.versions.get(version=job.version).comment
                }
        elif self.type == 2:
            msg = MESSAGES[self.type] % {
                'id': job.identifier,
                'user': self.change_user.get_full_name()
            }
        elif self.type in [3, 4, 5, 6]:
            msg = MESSAGES[self.type] % {'id': job.identifier}
        else:
            msg = MESSAGES[self.type]

        if self.is_producer and ('%s_0' % self.type) in settings or \
                self.is_operator and ('%s_1' % self.type) in settings or \
                self.is_observer and ('%s_2' % self.type) in settings or \
                self.is_expert and ('%s_3' % self.type) in settings or \
                self.is_manager and ('%s_4' % self.type) in settings:
            mime_msg = MIMEText(msg, 'html')
            mime_msg['To'] = self.user.email
            mime_msg['Subject'] = "%s" % SUBJECTS[self.type]
            return mime_msg


class NotifyData(object):
    def __init__(self, user):
        self.user = user
        self.self_ntf = False
        self.settings = self.__get_settings()
        self.table = self.__get_table()

    def __get_settings(self):
        try:
            self.self_ntf = self.user.notifications.self_ntf
            return json.loads(self.user.notifications.settings)
        except ObjectDoesNotExist:
            return []

    def __get_table(self):
        self.ccc = 1
        col_headers = [
            _('Jobs creation'),
            _('Changes of jobs'),
            _('Jobs deletion'),
            _('Start of job decisions'),
            _('Finish of job decisions'),
            _('New unsafes'),
            _('New unknowns'),
            _('Changes in correlation between marks and leaf reports'),
            _('Marks creation'),
            _('Changes of marks'),
            _('Marks deletion')
        ]
        row_headers = [_('Producer'), _('Operator'), _('Observer'), _('Expert'),
                       _('Manager')]
        table_data = {
            'colspan': len(row_headers),
            'head_0': _('I am'),
            'head_1': row_headers,
            'rows': [],
            'footer': _('Notify about my changes')
        }
        cnt = 0
        for head in col_headers:
            row_data = {'name': head, 'ids': []}
            for r in range(0, len(row_headers)):
                row_data['ids'].append(("%s_%s" % (cnt, r)))
            table_data['rows'].append(row_data)
            cnt += 1
        return table_data
