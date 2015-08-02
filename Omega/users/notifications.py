import json
import smtplib
from email.mime.text import MIMEText
from django.utils.translation import ugettext_lazy as _, activate
from django.core.exceptions import ObjectDoesNotExist
from Omega.vars import JOB_ROLES, USER_ROLES
from jobs.job_model import Job
from django.contrib.auth.models import User
from django.db.models import Q


SUBJECTS = {
    0: _("New verification job was created"),
    1: _("Verification job was changed"),
    2: _("Verification job was deleted"),
    3: _("Verification job has started to decide"),
    4: _("Verification job deciding has finished"),
    5: _("New unsafe was found"),
    6: _("New problem in component was found"),
    7: _("Mark is connected with another verification report already"),
    8: _("New Mark was created"),
    9: _("Mark was changed"),
    10: _("Mark was deleted"),
}

MESSAGES = {
    0: _('Job with identifier %(id)s was created by %(user)s.'),
    1: _('Job with identifier %(id)s was changed by %(user)s.'),
    2: _("Job with identifier %(id)s was deleted by %(user)s."),
    3: _("Job with identifier %(id)s has just started to decide."),
    4: _("Verification job with identifier %(id)s deciding has finished"),
    5: _("New unsafe for job with identifier %(id)s was found"),
    6: _("New problem in component was found for job with identifier %(id)s"),
    7: _("Mark is connected with another verification report already"),
    8: _("New Mark was created"),
    9: _("Mark was changed"),
    10: _("Mark was deleted"),
}


class Notify(object):
    def __init__(self, job, ntf_type):
        self.server = 'motor.intra.ispras.ru'
        self.omega_email = 'omega-noreply@ispras.ru'
        self.type = ntf_type
        self.job = job
        if isinstance(job, Job):
            self.__notify()

    def __notify(self):
        s = smtplib.SMTP(self.server)
        for user in User.objects.filter(
                ~Q(notifications__settings='[]') & ~Q(notifications=None)):
            if user.email is not None and len(user.email) > 0:
                message = UserMessage(user, self.job, self.type).message
                activate(user.extended.language)
                if isinstance(message, MIMEText):
                    message['From'] = self.omega_email
                    try:
                        s.send_message(message)
                    except Exception as e:
                        print("ERROR:", e)
        s.quit()


class UserMessage(object):

    def __init__(self, user, job, ntf_type):
        self.user = user
        try:
            self.type = int(ntf_type)
        except ValueError:
            return
        self.is_producer = False
        self.is_operator = False
        self.is_observer = False
        self.is_expert = False
        self.is_manager = (self.user.extended.role == USER_ROLES[2][0])
        self.change_user = None
        self.__get_job_prop(job)
        self.message = self.__get_message(job)

    def __get_job_prop(self, job):
        try:
            first_version = job.jobhistory_set.get(version=1)
            last_version = job.jobhistory_set.get(version=job.version)
        except ObjectDoesNotExist:
            return None
        self.is_producer = (self.user == first_version.change_author)
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

        if self.type in [0, 1, 2]:
            msg = MESSAGES[self.type] % {
                'id': job.identifier,
                'user': ("%s %s" % (
                    self.change_user.extended.last_name,
                    self.change_user.extended.first_name
                ))
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
            mime_msg = MIMEText(msg)
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
            'Job creation',
            'Job changes',
            'Job deletion',
            'Start of job deciding',
            'End of job deciding',
            'New unsafes',
            'New unknowns',
            'Changes in links between marks and leaf reports',
            'Marks creation',
            'Marks changes',
            'Marks deletion'
        ]
        row_headers = [_('Producer'), _('Operator'), _('Observer'), _('Expert'),
                       _('Manager')]
        table_data = {
            'colspan': len(row_headers),
            'head_0': _('Me'),
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
