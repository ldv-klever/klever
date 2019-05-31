from collections import OrderedDict, Mapping
from django.db.models import F, Count, Case, When, BooleanField
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers, fields, exceptions

from bridge.vars import ASSOCIATION_TYPE, SAFE_VERDICTS, UNSAFE_VERDICTS

from jobs.models import Job
from reports.models import (
    ReportRoot, ReportSafe, ReportUnsafe, ReportUnknown, ReportAttr, ReportComponent, Computer,
    OriginalSources
)
from marks.models import MarkSafeReport, MarkSafeTag, MarkUnsafeReport, MarkUnsafeTag, MarkUnknownReport


class ReportsAndMarksSerialzierRO(serializers.ModelSerializer):
    safe_verdicts = fields.SerializerMethodField()
    unsafe_verdicts = fields.SerializerMethodField()
    unknown_verdicts = fields.SerializerMethodField()

    def get_safe_verdicts(self, instance):
        queryset = ReportSafe.objects\
            .filter(root=instance).values('verdict') \
            .annotate(total=Count('id'), confirmed=Count(Case(When(has_confirmed=True, then=1)))) \
            .values('verdict', 'total', 'confirmed').order_by('verdict')
        data = list(queryset)
        data.append({
            'verdict': 'total',
            'total': sum(x['total'] for x in data),
            'confirmed': sum(x['confirmed'] for x in data)
        })
        return data

    def get_unsafe_verdicts(self, instance):
        queryset = ReportUnsafe.objects \
            .filter(root=instance).values('verdict') \
            .annotate(total=Count('id'), confirmed=Count(Case(When(has_confirmed=True, then=1)))) \
            .values('verdict', 'total', 'confirmed').order_by('verdict')
        data = list(queryset)
        data.append({
            'verdict': 'total',
            'total': sum(x['total'] for x in data),
            'confirmed': sum(x['confirmed'] for x in data)
        })
        return data

    def get_unknown_verdicts(self, instance):
        unknowns_data = {}

        # Marked/Unmarked unknowns
        unconfirmed_annotation = Case(
            When(markreport_set__type=ASSOCIATION_TYPE[2][0], then=True),
            default=False, output_field=BooleanField()
        )
        queryset = ReportUnknown.objects.filter(root=instance) \
            .values('component_id', 'markreport_set__problem_id') \
            .annotate(number=Count('id', distinct=True), unconfirmed=unconfirmed_annotation)\
            .values_list('component__name', 'markreport_set__problem__name', 'number', 'unconfirmed')
        for component, problem, number, unconfirmed in queryset:
            data_key = (component, 'Without marks' if problem is None or unconfirmed else problem)
            unknowns_data.setdefault(data_key, 0)
            unknowns_data[data_key] += number
        unknowns_list = list({
            'component': component, 'problem': problem,
            'number': unknowns_data[component, problem]
        } for component, problem in sorted(unknowns_data))

        # Total unknowns for each component
        queryset = ReportUnknown.objects.filter(root=instance)\
            .values('component_id').annotate(number=Count('id'))\
            .values_list('component__name', 'number').order_by('component__name')
        totals_list = list({'component': component, 'problem': 'Total', 'number': number}
                           for component, number in queryset)
        return unknowns_list + totals_list

    def get_safes(self, instance):
        marks = {}
        reports = {}

        # Add reports with marks and their marks
        for mr in MarkSafeReport.objects.filter(report__root=instance).select_related('mark'):
            mark_identifier = str(mr.mark.identifier)
            reports.setdefault(mr.report_id, {'attrs': [], 'marks': {}})
            reports[mr.report_id]['marks'].append(mark_identifier)
            if mark_identifier not in marks:
                marks[mark_identifier] = {
                    'verdict': mr.mark.verdict, 'status': mr.mark.status,
                    'description': mr.mark.description, 'tags': []
                }

        # Add reports without marks
        for s_id in ReportSafe.objects.filter(root=instance, verdict=SAFE_VERDICTS[4][0])\
                .values_list('id', flat=True):
            reports[s_id] = {'attrs': [], 'marks': []}

        # Get reports' attributes
        for r_id, aname, aval in ReportAttr.objects.filter(report_id__in=reports).order_by('attr__name__name')\
                .values_list('report_id', 'attr__name__name', 'attr__value'):
            reports[r_id]['attrs'].append([aname, aval])

        # Get marks' tags
        for identifier, tag in MarkSafeTag.objects \
                .filter(mark_version__mark__identifier__in=marks,
                        mark_version__version=F('mark_version__mark__version')) \
                .order_by('tag__tag').values_list('mark_version__mark__identifier', 'tag__tag'):
            marks[identifier]['tags'].append(tag)

        return {'marks': marks, 'reports': list(reports[r_id] for r_id in sorted(reports))}

    def get_unsafes(self):
        marks = {}
        reports = {}

        # Add reports with marks and their marks
        for mr in MarkUnsafeReport.objects.filter(report__root=self.job.reportroot).select_related('mark'):
            mark_identifier = str(mr.mark.identifier)
            reports.setdefault(mr.report_id, {'attrs': [], 'marks': {}})
            reports[mr.report_id]['marks'][mark_identifier] = mr.result
            if mark_identifier not in marks:
                marks[mark_identifier] = {
                    'verdict': mr.mark.verdict, 'status': mr.mark.status,
                    'description': mr.mark.description, 'tags': []
                }

        # Add reports without marks
        for u_id in ReportUnsafe.objects.filter(root=self.job.reportroot, verdict=UNSAFE_VERDICTS[5][0])\
                .values_list('id', flat=True):
            reports[u_id] = {'attrs': [], 'marks': {}}

        # Get reports' attributes
        for r_id, aname, aval in ReportAttr.objects.filter(report_id__in=reports)\
                .order_by('attr__name__name').values_list('report_id', 'attr__name__name', 'attr__value'):
            reports[r_id]['attrs'].append([aname, aval])

        # Get marks' tags
        for identifier, tag in MarkUnsafeTag.objects\
                .filter(mark_version__mark__identifier__in=marks,
                        mark_version__version=F('mark_version__mark__version'))\
                .order_by('tag__tag').values_list('mark_version__mark__identifier', 'tag__tag'):
            marks[identifier]['tags'].append(tag)

        return {'marks': marks, 'reports': list(reports[r_id] for r_id in sorted(reports))}

    def get_unknowns(self):
        marks = {}
        reports = {}

        # Get reports with marks and their marks
        for mr in MarkUnknownReport.objects.filter(report__root=self.job.reportroot)\
                .select_related('mark', 'mark__component'):
            mark_identifier = str(mr.mark.identifier)
            reports.setdefault(mr.report_id, {'attrs': [], 'marks': []})
            reports[mr.report_id]['marks'].append(mark_identifier)
            if mark_identifier not in marks:
                marks[mark_identifier] = {
                    'component': mr.mark.component.name, 'function': mr.mark.function,
                    'is_regexp': mr.mark.is_regexp, 'status': mr.mark.status,
                    'description': mr.mark.description
                }

        # Get reports without marks
        for f_id in ReportUnknown.objects.filter(root=self.job.reportroot).exclude(id__in=reports)\
                .values_list('id', flat=True):
            reports[f_id] = {'attrs': [], 'marks': []}

        # Get reports' attributes
        for r_id, aname, aval in ReportAttr.objects.filter(report_id__in=reports) \
                .order_by('attr__name__name').values_list('report_id', 'attr__name__name', 'attr__value'):
            reports[r_id]['attrs'].append([aname, aval])

        return {'marks': marks, 'reports': list(reports[r_id] for r_id in sorted(reports))}

    class Meta:
        model = ReportRoot
        fields = ('safe_verdicts', 'unsafe_verdicts', 'unknown_verdicts', 'safes', 'unsafes', 'unknowns')


class DecisionResultsSerializerRO(serializers.ModelSerializer):
    reports_and_marks = ReportsAndMarksSerialzierRO()
    start_date = serializers.SerializerMethodField()
    finish_date = serializers.SerializerMethodField()

    def get_start_date(self, instance):
        start_date = instance.decision.start_date
        return start_date.timestamp() if start_date else None

    def get_finish_date(self, instance):
        finish_date = instance.decision.finish_date
        return finish_date.timestamp() if finish_date else None

    def to_representation(self, instance):
        value = super().to_representation(instance)
        reports_and_marks = value.pop('reports_and_marks')
        value['verdicts'] = {
            'safes': reports_and_marks['safe_verdicts'],
            'unsafes': reports_and_marks['unsafe_verdicts'],
            'unknowns': reports_and_marks['unknown_verdicts'],
        }
        value['safes'] = reports_and_marks['safes']
        value['unsafes'] = reports_and_marks['unsafes']
        value['unknowns'] = reports_and_marks['unknowns']
        return value

    class Meta:
        model = Job
        fields = ('name', 'status', 'reports_and_marks', 'start_date', 'finish_date')


class ComputerDataField(fields.Field):
    initial = []
    default_error_messages = {
        'not_a_list': _('Expected a list of items but got type "{input_type}".'),
        'prop_wrong': _('Computer property has wrong format.'),
    }

    def get_value(self, dictionary):
        if self.field_name not in dictionary:
            if getattr(self.root, 'partial', False):
                return fields.empty
        if fields.html.is_html_input(dictionary):
            val = dictionary.getlist(self.field_name, [])
            if len(val) > 0:
                return val
            return fields.html.parse_html_list(dictionary, prefix=self.field_name, default=fields.empty)
        return dictionary.get(self.field_name, fields.empty)

    def to_internal_value(self, data):
        if fields.html.is_html_input(data):
            data = fields.html.parse_html_list(data, default=[])
        if isinstance(data, str) or isinstance(data, Mapping) or not hasattr(data, '__iter__'):
            self.fail('not_a_list', input_type=type(data).__name__)
        return self.run_child_validation(data)

    def to_representation(self, data):
        return data

    def __validate_property(self, prop):
        if not isinstance(prop, dict) or len(prop) != 1:
            self.fail('prop_wrong')
        prop_key = next(iter(prop))
        prop_value = prop[prop_key]
        if not isinstance(prop_value, (str, int)):
            self.fail('prop_wrong')
        return [prop_key, prop_value]

    def run_child_validation(self, data):
        result = []
        errors = OrderedDict()
        for idx, item in enumerate(data):
            try:
                result.append(self.__validate_property(item))
            except exceptions.ValidationError as e:
                errors[idx] = e.detail
        if not errors:
            return result
        raise exceptions.ValidationError(errors)


class ComputerSerializer(serializers.ModelSerializer):
    data = ComputerDataField()

    def create(self, validated_data):
        try:
            # Do not create the computer with the same identifier again
            return Computer.objects.get(identifier=validated_data['identifier'])
        except Computer.DoesNotExist:
            return super().create(validated_data)

    class Meta:
        model = Computer
        fields = '__all__'


class ReportComponentSerializer(serializers.ModelSerializer):
    parent = serializers.SlugRelatedField(slug_field='identifier', allow_null=True, queryset=ReportComponent.objects)

    def create(self, validated_data):
        # Root, computer, parent must be specified in save() method
        assert 'root' in validated_data, _('Report root is required')
        assert 'computer' in validated_data, _('Report computer is required')
        assert 'parent' in validated_data, _('Report parent is required')

        return super().create(validated_data)

    class Meta:
        model = ReportComponent
        exclude = ('root', 'computer', 'parent')
        # parent, identifier, cpu_time, wall_time, memory,
        # start_date, finish_date, log, verifier_input, data


class ReportAttrSerializer(serializers.ModelSerializer):
    data_id = fields.IntegerField(allow_null=True, required=False)

    class Meta:
        model = ReportAttr
        fields = ('name', 'value', 'compare', 'associate', 'data_id')


class OriginalSourcesSerializer(serializers.ModelSerializer):
    class Meta:
        model = OriginalSources
        fields = '__all__'
