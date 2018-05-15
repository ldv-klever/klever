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

import os
import re
import json

from django.db.models import ProtectedError, F
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from bridge.vars import USER_ROLES, MARK_STATUS, MARK_TYPE, ASSOCIATION_TYPE, PROBLEM_DESC_FILE
from bridge.utils import unique_id, BridgeException, logger, ArchiveFileContent

from users.models import User
from reports.models import ReportAttr, ReportUnknown, ReportComponentLeaf, Component, Attr, AttrName
from marks.models import MarkUnknown, MarkUnknownHistory, MarkUnknownAttr, MarkUnknownReport, UnknownProblem,\
    ComponentMarkUnknownProblem, UnknownAssociationLike


class NewMark:
    def __init__(self, user, args):
        self._user = user
        self._args = args
        self.changes = {}
        self.__check_args()

    def __check_args(self):
        if not isinstance(self._args, dict):
            raise ValueError('Wrong type: args (%s)' % type(self._args))
        if not isinstance(self._user, User):
            raise ValueError('Wrong type: user (%s)' % type(self._user))
        if self._args.get('status') not in set(x[0] for x in MARK_STATUS):
            raise ValueError('Unsupported status: %s' % self._args.get('status'))
        if not isinstance(self._args.get('comment'), str):
            self._args['comment'] = ''

        if self._user.extended.role != USER_ROLES[2][0]:
            self._args['is_modifiable'] = MarkUnknown._meta.get_field('is_modifiable').default
        elif not isinstance(self._args.get('is_modifiable'), bool):
            raise ValueError('Wrong type: is_modifiable (%s)' % type(self._args.get('is_modifiable')))

        if 'function' not in self._args or len(self._args['function']) == 0:
            raise BridgeException(_('The pattern is required'))
        try:
            re.search(self._args['function'], '')
        except Exception as e:
            logger.exception("Wrong mark function (%s): %s" % (self._args['function'], e), stack_info=True)
            raise BridgeException(_('The pattern is wrong, please refer to documentation on the standard Python '
                                    'library for processing reqular expressions'))

        if 'problem' not in self._args or len(self._args['problem']) == 0:
            raise BridgeException(_('The problem is required'))
        elif len(self._args['problem']) > 15:
            raise BridgeException(_('The problem length must be less than 15 characters'))
        if 'is_regexp' not in self._args or not isinstance(self._args['is_regexp'], bool):
            raise BridgeException()

        if 'link' not in self._args or len(self._args['link']) == 0:
            self._args['link'] = None

        if 'autoconfirm' in self._args and not isinstance(self._args['autoconfirm'], bool):
            raise ValueError('Wrong type: autoconfirm (%s)' % type(self._args['autoconfirm']))

    def create_mark(self, report):
        if MarkUnknown.objects.filter(component=report.component, problem_pattern=self._args['problem']).count() > 0:
            raise BridgeException(_('Could not create a new mark since the similar mark exists already'))

        mark = MarkUnknown.objects.create(
            identifier=unique_id(), author=self._user, change_date=now(), format=report.root.job.format,
            job=report.root.job, description=str(self._args.get('description', '')), status=self._args['status'],
            is_modifiable=self._args['is_modifiable'], component=report.component, function=self._args['function'],
            problem_pattern=self._args['problem'], link=self._args['link'], is_regexp=self._args['is_regexp']
        )
        try:
            markversion = self.__create_version(mark)
            self.__create_attributes(markversion.id, report)
        except Exception:
            mark.delete()
            raise
        self.changes = ConnectMark(mark, prime_id=report.id).changes
        return mark

    def change_mark(self, mark, recalculate_cache=True):
        last_v = MarkUnknownHistory.objects.get(mark=mark, version=F('mark__version'))

        if MarkUnknown.objects.filter(component=mark.component, problem_pattern=self._args['problem']) \
                .exclude(id=mark.id).count() > 0:
            raise BridgeException(_('Could not change the mark since it would be similar to the existing mark'))

        do_recalc = (self._args['function'] != mark.function or self._args['problem'] != mark.problem_pattern
                     or self._args['is_regexp'] != mark.is_regexp)

        mark.author = self._user
        mark.change_date = now()
        mark.status = self._args['status']
        mark.description = str(self._args.get('description', ''))
        mark.version += 1
        mark.is_modifiable = self._args['is_modifiable']
        mark.link = self._args['link']
        mark.function = self._args['function']
        mark.is_regexp = self._args['is_regexp']
        mark.problem_pattern = self._args['problem']
        markversion = self.__create_version(mark)

        try:
            do_recalc |= self.__create_attributes(markversion.id, last_v)
        except Exception:
            markversion.delete()
            raise
        mark.save()

        if recalculate_cache:
            if do_recalc or not self._args.get('autoconfirm', False):
                MarkUnknownReport.objects.filter(mark_id=mark.id).update(type=ASSOCIATION_TYPE[0][0])
                UnknownAssociationLike.objects.filter(association__mark=mark).delete()
            if do_recalc:
                self.changes = ConnectMark(mark).changes
            else:
                self.changes = self.__create_changes(mark)
        return mark

    def upload_mark(self):
        if 'component' not in self._args or len(self._args['component']) == 0:
            raise BridgeException(_("Component name is required"))
        if len(self._args['component']) > 15:
            raise BridgeException(_("Component name is too long"))
        component = Component.objects.get_or_create(name=self._args['component'])[0]
        if 'format' not in self._args:
            raise BridgeException(_('Unknown mark format is required'))
        if isinstance(self._args.get('identifier'), str) and 0 < len(self._args['identifier']) < 255:
            if MarkUnknown.objects.filter(identifier=self._args['identifier']).count() > 0:
                raise BridgeException(_("The mark with identifier specified in the archive already exists"))
        else:
            self._args['identifier'] = unique_id()
        if MarkUnknown.objects.filter(component=component, problem_pattern=self._args['problem']).count() > 0:
            raise BridgeException(_('Could not change the mark since it would be similar to the existing mark'))
        mark = MarkUnknown.objects.create(
            identifier=self._args['identifier'], author=self._user, change_date=now(),
            description=str(self._args.get('description', '')),
            status=self._args['status'], is_modifiable=self._args['is_modifiable'],
            problem_pattern=self._args['problem'], function=self._args['function'], link=self._args['link'],
            component=component, format=self._args['format'], type=MARK_TYPE[2][0], is_regexp=self._args['is_regexp']
        )
        try:
            markversion = self.__create_version(mark)
            self.__create_attributes(markversion.id)
        except Exception:
            mark.delete()
            raise
        return mark

    def __create_changes(self, mark):
        self.__is_not_used()
        changes = {}
        for mr in mark.markreport_set.all().select_related('report'):
            if mr.report not in changes:
                changes[mr.report] = {'kind': '=', 'problems': {}}
        for mr in MarkUnknownReport.objects.filter(report__in=changes):
            if mr.problem_id not in changes[mr.report]['problems']:
                changes[mr.report]['problems'][mr.problem_id] = [0, 0]
            changes[mr.report]['problems'][mr.problem_id][0] += 1
            changes[mr.report]['problems'][mr.problem_id][1] += 1

        return changes

    def __create_version(self, mark):
        return MarkUnknownHistory.objects.create(
            mark=mark, version=mark.version, status=mark.status, description=mark.description,
            author=mark.author, change_date=mark.change_date, comment=self._args['comment'],
            function=mark.function, problem_pattern=mark.problem_pattern, link=mark.link, is_regexp=mark.is_regexp
        )

    def __create_attributes(self, markversion_id, inst=None):
        if 'attrs' in self._args and (not isinstance(self._args['attrs'], list) or len(self._args['attrs']) == 0):
            del self._args['attrs']
        if 'attrs' in self._args:
            for a in self._args['attrs']:
                if not isinstance(a, dict) or not isinstance(a.get('attr'), str) \
                        or not isinstance(a.get('is_compare'), bool):
                    raise ValueError('Wrong attribute found: %s' % a)
                if inst is None and not isinstance(a.get('value'), str):
                    raise ValueError('Wrong attribute found: %s' % a)

        need_recalc = False
        new_attrs = []
        if isinstance(inst, ReportUnknown):
            for a_id, a_name, associate in inst.attrs.order_by('id')\
                    .values_list('attr_id', 'attr__name__name', 'associate'):
                if 'attrs' in self._args:
                    for a in self._args['attrs']:
                        if a['attr'] == a_name:
                            new_attrs.append(MarkUnknownAttr(
                                mark_id=markversion_id, attr_id=a_id, is_compare=a['is_compare']
                            ))
                            break
                    else:
                        raise ValueError('Not enough attributes in args')
                else:
                    print('Creating attr: ', a_name, associate)
                    new_attrs.append(MarkUnknownAttr(mark_id=markversion_id, attr_id=a_id, is_compare=associate))
        elif isinstance(inst, MarkUnknownHistory):
            for a_id, a_name, is_compare in inst.attrs.order_by('id')\
                    .values_list('attr_id', 'attr__name__name', 'is_compare'):
                if 'attrs' in self._args:
                    for a in self._args['attrs']:
                        if a['attr'] == a_name:
                            new_attrs.append(MarkUnknownAttr(
                                mark_id=markversion_id, attr_id=a_id, is_compare=a['is_compare']
                            ))
                            if a['is_compare'] != is_compare:
                                need_recalc = True
                            break
                    else:
                        raise ValueError('Not enough attributes in args')
                else:
                    new_attrs.append(MarkUnknownAttr(mark_id=markversion_id, attr_id=a_id, is_compare=is_compare))
        elif 'attrs' in self._args:
            for a in self._args['attrs']:
                attr = Attr.objects.get_or_create(
                    name=AttrName.objects.get_or_create(name=a['attr'])[0], value=a['value']
                )[0]
                new_attrs.append(MarkUnknownAttr(mark_id=markversion_id, attr=attr, is_compare=a['is_compare']))
        MarkUnknownAttr.objects.bulk_create(new_attrs)
        return need_recalc

    def __is_not_used(self):
        pass


class ConnectMark:
    def __init__(self, mark, prime_id=None):
        self.mark = mark
        self._prime_id = prime_id
        self.changes = {}
        self._mark_attrs = self.__get_mark_attrs()
        self._unknowns_attrs = self.__get_unknowns_attrs()
        if len(self._mark_attrs) > 0 and len(self._unknowns_attrs) == 0:
            return
        self.__clear_connections()
        self.__connect_unknown_mark()

    def __get_mark_attrs(self):
        return set(a_id for a_id, in MarkUnknownAttr.objects.filter(
            mark__mark=self.mark, is_compare=True, mark__version=F('mark__mark__version')
        ).values_list('attr_id'))

    def __get_unknowns_attrs(self):
        if len(self._mark_attrs) == 0:
            return {}

        unknowns_attrs = {}
        for r_id, a_id in ReportAttr.objects.exclude(report__reportunknown=None)\
                .filter(attr_id__in=self._mark_attrs, report__reportunknown__component=self.mark.component)\
                .values_list('report_id', 'attr_id'):
            if r_id not in unknowns_attrs:
                unknowns_attrs[r_id] = set()
            unknowns_attrs[r_id].add(a_id)
        return unknowns_attrs

    def __clear_connections(self):
        for mr in self.mark.markreport_set.all():
            if mr.report not in self.changes:
                self.changes[mr.report] = {'kind': '-', 'problems': {}}

        for mr in MarkUnknownReport.objects.filter(report__in=self.changes):
            if mr.problem_id not in self.changes[mr.report]['problems']:
                self.changes[mr.report]['problems'][mr.problem_id] = [0, 0]
            self.changes[mr.report]['problems'][mr.problem_id][0] += 1
            if mr.mark_id != self.mark.id:
                self.changes[mr.report]['problems'][mr.problem_id][1] += 1
        self.mark.markreport_set.all().delete()

    def __connect_unknown_mark(self):
        reports_filter = {'component': self.mark.component}

        if len(self._mark_attrs) > 0:
            reports_filter['id__in'] = set()
            for unknown_id in self._unknowns_attrs:
                if self._mark_attrs.issubset(self._unknowns_attrs[unknown_id]):
                    reports_filter['id__in'].add(unknown_id)

        new_markreports = []
        problems = {}
        for unknown in ReportUnknown.objects.filter(**reports_filter):
            try:
                problem_description = ArchiveFileContent(unknown, 'problem_description', PROBLEM_DESC_FILE)\
                    .content.decode('utf8')
            except Exception as e:
                logger.exception("Can't get problem description for unknown '%s': %s" % (unknown.id, e))
                return
            problem = MatchUnknown(
                problem_description, self.mark.function, self.mark.problem_pattern, self.mark.is_regexp
            ).problem
            if problem is None:
                continue
            elif len(problem) > 15:
                problem = 'Too long!'
                logger.error("Problem '%s' for mark %s is too long" % (problem, self.mark.identifier), stack_info=True)
            if problem not in problems:
                problems[problem] = UnknownProblem.objects.get_or_create(name=problem)[0]
            ass_type = ASSOCIATION_TYPE[0][0]
            if self._prime_id == unknown.id:
                ass_type = ASSOCIATION_TYPE[1][0]
            new_markreports.append(MarkUnknownReport(
                mark=self.mark, report=unknown, problem=problems[problem], type=ass_type, author=self.mark.author
            ))
            if unknown in self.changes:
                self.changes[unknown]['kind'] = '='
            else:
                self.changes[unknown] = {'kind': '+', 'problems': {}}

            if problems[problem].id not in self.changes[unknown]['problems']:
                self.changes[unknown]['problems'][problems[problem].id] = [0, 0]
            self.changes[unknown]['problems'][problems[problem].id][1] += 1

        MarkUnknownReport.objects.bulk_create(new_markreports)
        update_unknowns_cache(list(self.changes))


class ConnectReport:
    def __init__(self, report, update_cache=True):
        self._update_cache = update_cache
        self.report = report
        self._marks_attrs = self.__get_marks_attrs()
        self.__connect()

    def __get_marks_attrs(self):
        attr_filters = {'is_compare': True, 'mark__version': F('mark__mark__version')}
        marks_attrs = {}
        for attr_id, mark_id in MarkUnknownAttr.objects.filter(**attr_filters).values_list('attr_id', 'mark__mark_id'):
            if mark_id not in marks_attrs:
                marks_attrs[mark_id] = set()
            marks_attrs[mark_id].add(attr_id)
        return marks_attrs

    def __connect(self):
        self.report.markreport_set.all().delete()
        unknown_attrs = set(a_id for a_id, in self.report.attrs.values_list('attr_id'))

        try:
            problem_desc = ArchiveFileContent(self.report, 'problem_description', PROBLEM_DESC_FILE)\
                .content.decode('utf8')
        except Exception as e:
            logger.exception("Can't get problem desc for unknown '%s': %s" % (self.report.id, e))
            return
        new_markreports = []
        problems = {}
        for mark in MarkUnknown.objects.filter(component=self.report.component):
            if mark.id in self._marks_attrs and not self._marks_attrs[mark.id].issubset(unknown_attrs):
                continue

            problem = MatchUnknown(problem_desc, mark.function, mark.problem_pattern, mark.is_regexp).problem
            if problem is None:
                continue
            elif len(problem) > 15:
                problem = 'Too long!'
                logger.error(
                    "Generated problem '%s' for mark %s is too long" % (problem, mark.identifier), stack_info=True
                )
            if problem not in problems:
                problems[problem] = UnknownProblem.objects.get_or_create(name=problem)[0]
            new_markreports.append(MarkUnknownReport(mark=mark, report=self.report, problem=problems[problem]))
        MarkUnknownReport.objects.bulk_create(new_markreports)
        if self._update_cache:
            update_unknowns_cache([self.report])


class RecalculateConnections:
    def __init__(self, roots):
        self._roots = roots
        self.__recalc()
        for problem in UnknownProblem.objects.all():
            try:
                problem.delete()
            except ProtectedError:
                pass

    def __recalc(self):
        MarkUnknownReport.objects.filter(report__root__in=self._roots).delete()
        ComponentMarkUnknownProblem.objects.filter(report__root__in=self._roots).delete()
        # TODO: optiomizations: connect all reports at once
        for unknown in ReportUnknown.objects.filter(root__in=self._roots):
            ConnectReport(unknown, False)
        update_unknowns_cache(ReportUnknown.objects.filter(root__in=self._roots))


class CheckFunction:
    def __init__(self, description, mark_function, pattern, is_regexp):
        self._desc = description
        self._func = mark_function
        self._pattern = pattern
        self._regexp = json.loads(is_regexp)
        if self._regexp:
            self.problem, self.match = self.__match_desc_regexp()
        else:
            self.problem, self.match = self.__match_desc()

        if isinstance(self.problem, str) and len(self.problem) == 0:
            self.problem = '-'
        if self.problem is not None and len(self.problem) > 15:
            raise BridgeException(_('The problem length must be less than 15 characters'))

    def __match_desc_regexp(self):
        try:
            m = re.search(self._func, self._desc, re.MULTILINE)
        except Exception as e:
            logger.exception("Regexp error: %s" % e, stack_info=True)
            return None, str(e)
        if m is not None:
            try:
                return self._pattern.format(*m.groups()), self.__get_matched_text(*m.span())
            except IndexError:
                return self._pattern, self.__get_matched_text(*m.span())
        return None, ''

    def __match_desc(self):
        start = self._desc.find(self._func)
        if start < 0:
            return None, ''
        end = start + len(self._func)
        return self._pattern, self.__get_matched_text(start, end)

    def __get_matched_text(self, start, end):
        line_breaks = list(a.start() for a in re.finditer('\n', self._desc))
        prev = -1
        f = 0
        for i in line_breaks:
            if i > start and f == 0:
                start = prev + 1
                f += 1
            prev = i
            if i >= end and f == 1:
                end = prev
                break
        else:
            end = len(self._desc)
        return self._desc[start:end]


class MatchUnknown:
    def __init__(self, description, func, pattern, is_regexp):
        self.description = description
        self.function = func
        self.pattern = pattern
        if is_regexp:
            self.problem = self.__match_desc_regexp()
        else:
            self.problem = self.__match_desc()

        if isinstance(self.problem, str) and len(self.problem) == 0:
            self.problem = None

    def __match_desc_regexp(self):
        try:
            m = re.search(self.function, self.description, re.MULTILINE)
        except Exception as e:
            logger.exception("Regexp error: %s" % e, stack_info=True)
            return None
        if m is not None:
            try:
                return self.pattern.format(*m.groups())
            except IndexError:
                return self.pattern
        return None

    def __match_desc(self):
        if self.description.find(self.function) < 0:
            return None
        return self.pattern


class PopulateMarks:
    def __init__(self, manager):
        self._author = manager
        self.total = 0
        self.created = 0
        self._markattrs = {}
        self._marks = self.__get_data()
        self.__get_attrnames()
        self.__get_attrs()

        self.new_marks = self.__create_marks()
        self.__create_related()
        for mark in self.new_marks.values():
            ConnectMark(mark)

    def __get_attrnames(self):
        attrnames = {}
        for a in AttrName.objects.all():
            attrnames[a.name] = a.id
        for mid in self._markattrs:
            for a in self._markattrs[mid]:
                if a['attr'] in attrnames:
                    a['attr'] = attrnames[a['attr']]
                else:
                    a['attr'] = AttrName.objects.create(name=a['attr']).id

    def __get_attrs(self):
        attrs_in_db = {}
        for a in Attr.objects.all():
            attrs_in_db[(a.name_id, a.value)] = a.id
        attrs_to_create = []
        for mid in self._markattrs:
            for a in self._markattrs[mid]:
                if (a['attr'], a['value']) not in attrs_in_db:
                    attrs_to_create.append(Attr(name_id=a['attr'], value=a['value']))
        if len(attrs_to_create) > 0:
            Attr.objects.bulk_create(attrs_to_create)
            self.__get_attrs()
        else:
            for mid in self._markattrs:
                for a in self._markattrs[mid]:
                    a['attr'] = attrs_in_db[(a['attr'], a['value'])]
                    del a['value']

    def __get_data(self):
        presets_dir = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'unknowns')
        new_marks = []
        for component_dir in [os.path.join(presets_dir, x) for x in os.listdir(presets_dir)]:
            component = os.path.basename(component_dir)
            if not 0 < len(component) <= 20:
                raise ValueError('Wrong component length: "%s". 1-20 is allowed.' % component)
            for mark_settings in [os.path.join(component_dir, x) for x in os.listdir(component_dir)]:
                data = None
                identifier = os.path.splitext(os.path.basename(mark_settings))[0]
                try:
                    MarkUnknown.objects.get(identifier=identifier)
                    # The mark was already uploaded
                    continue
                except ObjectDoesNotExist:
                    pass

                with open(mark_settings, encoding='utf8') as fp:
                    try:
                        data = json.load(fp)
                    except Exception as e:
                        fp.seek(0)
                        try:
                            path_to_json = os.path.abspath(os.path.join(component_dir, fp.read()))
                            with open(path_to_json, encoding='utf8') as fp2:
                                data = json.load(fp2)
                        except Exception:
                            raise BridgeException("Can't parse json data of unknown mark: %s (\"%s\")" % (
                                e, os.path.relpath(mark_settings, presets_dir)
                            ))
                if not isinstance(data, dict) or any(x not in data for x in ['pattern', 'problem']):
                    raise BridgeException('Wrong unknown mark data format: %s' % mark_settings)
                try:
                    re.compile(data['pattern'])
                except re.error:
                    raise ValueError('Wrong regular expression: "%s"' % data['pattern'])
                if 'link' not in data:
                    data['link'] = ''
                if 'description' not in data:
                    data['description'] = ''
                if 'status' not in data:
                    data['status'] = MARK_STATUS[0][0]
                if 'is_modifiable' not in data:
                    data['is_modifiable'] = True
                if 'is regexp' not in data:
                    data['is regexp'] = False

                if data['status'] not in list(x[0] for x in MARK_STATUS) or len(data['pattern']) == 0 \
                        or not 0 < len(data['problem']) <= 15 or not isinstance(data['is_modifiable'], bool):
                    raise BridgeException('Wrong unknown mark data: %s' % mark_settings)
                if 'attrs' in data:
                    if not isinstance(data['attrs'], list):
                        raise BridgeException(_('Corrupted preset unknown mark: attributes is not a list'))
                    if any(not isinstance(x, dict) for x in data['attrs']) \
                            or any(x not in y for x in ['attr', 'value', 'is_compare'] for y in data['attrs']):
                        raise BridgeException(_('Corrupted preset unknown mark: one of attributes has wrong format'))

                self.total += 1
                try:
                    MarkUnknown.objects.get(component__name=component, problem_pattern=data['problem'])
                except ObjectDoesNotExist:
                    new_marks.append(MarkUnknown(
                        identifier=identifier, component=Component.objects.get_or_create(name=component)[0],
                        author=self._author, change_date=now(), is_modifiable=data['is_modifiable'],
                        status=data['status'], function=data['pattern'], problem_pattern=data['problem'],
                        description=data['description'], type=MARK_TYPE[1][0], is_regexp=data['is regexp'],
                        link=data['link'] if len(data['link']) > 0 else None
                    ))
                    self._markattrs[identifier] = data['attrs']
                    self.created += 1
                except MultipleObjectsReturned:
                    raise Exception('There are similar unknown marks in the system')
        return new_marks

    def __create_marks(self):
        marks_in_db = {}
        for ma in MarkUnknownAttr.objects.values('mark_id', 'attr_id', 'is_compare'):
            if ma['mark_id'] not in marks_in_db:
                marks_in_db[ma['mark_id']] = set()
            marks_in_db[ma['mark_id']].add((ma['attr_id'], ma['is_compare']))
        MarkUnknown.objects.bulk_create(self._marks)

        created_marks = {}
        marks_versions = []
        for mark in MarkUnknown.objects.filter(versions=None):
            created_marks[mark.identifier] = mark
            marks_versions.append(MarkUnknownHistory(
                mark=mark, version=mark.version, author=mark.author, status=mark.status,
                function=mark.function, problem_pattern=mark.problem_pattern, link=mark.link,
                change_date=mark.change_date, description=mark.description, is_regexp=mark.is_regexp, comment=''
            ))
        MarkUnknownHistory.objects.bulk_create(marks_versions)
        return created_marks

    def __create_related(self):
        versions = {}
        for mh in MarkUnknownHistory.objects.filter(mark__in=self.new_marks.values()).select_related('mark'):
            versions[mh.mark.identifier] = mh.id

        new_attrs = []
        for mid in self._markattrs:
            for a in self._markattrs[mid]:
                new_attrs.append(MarkUnknownAttr(mark_id=versions[mid], attr_id=a['attr'], is_compare=a['is_compare']))
        MarkUnknownAttr.objects.bulk_create(new_attrs)


def update_unknowns_cache(unknowns):
    reports = set()
    for leaf in ReportComponentLeaf.objects.filter(unknown__in=list(unknowns)):
        reports.add(leaf.report_id)

    all_unknowns = {}
    components_data = {}
    for leaf in ReportComponentLeaf.objects.filter(report_id__in=reports).exclude(unknown=None)\
            .values('report_id', 'unknown_id', 'unknown__component_id'):
        if leaf['report_id'] not in all_unknowns:
            all_unknowns[leaf['report_id']] = set()
        all_unknowns[leaf['report_id']].add(leaf['unknown_id'])
        if leaf['unknown__component_id'] not in components_data:
            components_data[leaf['unknown__component_id']] = set()
        components_data[leaf['unknown__component_id']].add(leaf['unknown_id'])

    unknowns_ids = set()
    for rc_id in all_unknowns:
        unknowns_ids = unknowns_ids | all_unknowns[rc_id]
    marked_unknowns = set()
    problems_data = {}
    for mr in MarkUnknownReport.objects.filter(report_id__in=unknowns_ids).exclude(type=ASSOCIATION_TYPE[2][0]):
        if mr.problem_id not in problems_data:
            problems_data[mr.problem_id] = set()
        problems_data[mr.problem_id].add(mr.report_id)
        marked_unknowns.add(mr.report_id)

    problems_data[None] = unknowns_ids - marked_unknowns

    new_cache = []
    for r_id in all_unknowns:
        for p_id in problems_data:
            for c_id in components_data:
                number = len(all_unknowns[r_id] & problems_data[p_id] & components_data[c_id])
                if number > 0:
                    new_cache.append(ComponentMarkUnknownProblem(
                        report_id=r_id, component_id=c_id, problem_id=p_id, number=number
                    ))
    ComponentMarkUnknownProblem.objects.filter(report_id__in=reports).delete()
    ComponentMarkUnknownProblem.objects.bulk_create(new_cache)


def delete_marks(marks):
    changes = {}
    for mark in marks:
        changes[mark.id] = {}
    MarkUnknown.objects.filter(id__in=changes).update(version=0)
    for mr in MarkUnknownReport.objects.filter(mark__in=marks).select_related('report'):
        changes[mr.mark_id][mr.report] = {'kind': '-'}
    MarkUnknown.objects.filter(id__in=changes).delete()
    unknowns_changes = {}
    for m_id in changes:
        for report in changes[m_id]:
            unknowns_changes[report] = changes[m_id][report]
    update_unknowns_cache(unknowns_changes)
    return unknowns_changes
