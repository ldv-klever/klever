from django.core.exceptions import ObjectDoesNotExist

from bridge.utils import logger
from bridge.vars import ASSOCIATION_TYPE
from bridge.rawQuery import RawQuery, EmptyQuery

from reports.models import Component, Report, ReportSafe, ReportUnsafe, ReportUnknown, ReportComponentLeaf,\
    ReportAttr, Attr, AttrName
from marks.models import MarkSafeReport, MarkUnsafeReport, MarkUnknownReport, SafeTag, UnsafeTag,\
    SafeReportTag, UnsafeReportTag, UnknownProblem


class LeavesQuery:
    def __init__(self, model, view, **kwargs):
        self.model = model
        if model not in (ReportSafe, ReportUnsafe, ReportUnknown):
            raise ValueError('Unknown leaf model: %s' % type(model))

        self.view = view
        self.kwargs = kwargs
        self._objects = None

    def __filter_by_report(self):
        if 'report' not in self.kwargs:
            return
        leaf_field = {ReportSafe: 'safe_id', ReportUnsafe: 'unsafe_id', ReportUnknown: 'unknown_id'}
        subquery = RawQuery(ReportComponentLeaf)
        subquery.select(leaf_field[self.model])
        subquery.where('{0} = %s', 'report_id', args_list=[self.kwargs['report'].id])
        subquery.group_by(leaf_field[self.model])
        self.sql.join('INNER', subquery, (leaf_field[self.model], 'id'), table_to=Report)

    def __process_verdict(self):
        if self.model == ReportUnknown:
            # Unknowns don't have verdicts
            return

        # Add column if needed
        if 'report_verdict' in self.view['columns']:
            self.sql.select('verdict')

        operation = "{0} = %s"
        args = []
        if self.kwargs.get('verdict') is not None:
            args.append(self.kwargs['verdict'])
        elif 'verdict' in self.view:
            v_num = len(self.view['verdict'])
            if v_num == 0:
                return
            if v_num == 1:
                args.append(self.view['verdict'][0])
            else:
                args = self.view['verdict']
                operation = "{0} IN (%s)" % ', '.join(['%s'] * len(self.view['verdict']))
        else:
            # There's not filters by verdict
            return
        self.sql.where(operation, 'verdict', args_list=args)

    def __get_ms(self, value, measure):
        if isinstance(value, str):
            value = float(value.replace(',', '.'))
        if measure == 's':
            return value * 1000
        elif measure == 'm':
            return value * 60000
        return value

    def __process_cpu_time(self):
        if 'verifiers:cpu' not in self.view['columns']:
            # We are not going to filter/sort by cpu time if it isn't shown
            return
        self.sql.select('cpu_time')

        # Filter by cpu time
        if 'parent_cpu' in self.view:
            operation = '{0} ' + ('<' if self.view['parent_cpu'][0] == 'lt' else '>') + ' %s'
            value = self.__get_ms(self.view['parent_cpu'][1], self.view['parent_cpu'][2])
            self.sql.where(operation, 'cpu_time', args_list=[value])

        # Order by cpu time
        if 'order' in self.view and self.view['order'][1] == 'parent_cpu':
            self.sql.order_by('cpu_time', 'DESC' if self.view['order'][0] == 'up' else 'ASC')

    def __process_wall_time(self):
        if 'verifiers:wall' not in self.view['columns']:
            # We are not going to filter/sort by wall time if it isn't shown
            return
        self.sql.select('wall_time')

        # Filter by wall time
        if 'parent_wall' in self.view:
            operation = '{0} ' + ('<' if self.view['parent_wall'][0] == 'lt' else '>') + ' %s'
            value = self.__get_ms(self.view['parent_wall'][1], self.view['parent_wall'][2])
            self.sql.where(operation, 'wall_time', args_list=[value])

        # Order by wall time
        if 'order' in self.view and self.view['order'][1] == 'parent_wall':
            self.sql.order_by('wall_time', 'DESC' if self.view['order'][0] == 'up' else 'ASC')

    def __process_memory(self):
        if 'verifiers:memory' not in self.view['columns']:
            # We are not going to filter/sort by memory if it isn't shown
            return
        self.sql.select('memory')

        # Filter by memory
        if 'parent_memory' in self.view:
            operation = '{0} ' + ('<' if self.view['parent_memory'][0] == 'lt' else '>') + ' %s'

            value = float(self.view['parent_memory'][1].replace(',', '.'))
            if self.view['parent_memory'][2] == 'KB':
                value *= 1024
            elif self.view['parent_memory'][2] == 'MB':
                value *= 1024 * 1024
            elif self.view['parent_memory'][2] == 'GB':
                value *= 1024 ** 3

            self.sql.where(operation, 'memory', args_list=[value])

        # Order by memory
        if 'order' in self.view and self.view['order'][1] == 'parent_memory':
            self.sql.order_by('memory', 'DESC' if self.view['order'][0] == 'up' else 'ASC')

    def __process_marks(self):
        if 'marks_number' not in self.view['columns']:
            # We are not going to fitler by number of (confirmed) marks if it isn't shown
            return

        # Is confirmed number shown?
        with_confirmed = 'hidden' not in self.view or 'confirmed_marks' not in self.view['hidden']

        sq_model = {ReportSafe: MarkSafeReport, ReportUnsafe: MarkUnsafeReport, ReportUnknown: MarkUnknownReport}
        # Subquery with marks numbers
        subquery = RawQuery(sq_model[self.model])
        subquery.select('report_id')
        subquery.aggregate('marks_number', 'COUNT({0})', 'id')

        if with_confirmed:
            subquery.aggregate('confirmed', 'COUNT(CASE WHEN {0} = %s THEN 1 ELSE NULL END)', 'type',
                               args_list=[ASSOCIATION_TYPE[1][0]])
        subquery.group_by('report_id')
        self.sql.join('LEFT OUTER', subquery, 'report_id', 'id', table_to=Report)

        self.sql.aggregate('marks_number', '(CASE WHEN {0} IS NULL THEN 0 ELSE {0} END)', ('marks_number', subquery))
        if with_confirmed:
            self.sql.aggregate('confirmed', '(CASE WHEN {0} IS NULL THEN 0 ELSE {0} END)', ('confirmed', subquery))

        # Filter
        if 'marks_number' in self.view:
            operation = '(CASE WHEN {0} IS NULL THEN 0 ELSE {0} END) '
            if self.view['marks_number'][1] == 'lte':
                operation += '<='
            elif self.view['marks_number'][1] == 'gte':
                operation += '>='
            else:  # iexact
                operation += '='
            operation += ' %s'

            if self.view['marks_number'][0] == 'confirmed':
                if not with_confirmed:
                    # Don't filter by confirmed number if it is hidden (wasn't aggregated)
                    return
                field_name = 'confirmed'
            else:
                field_name = 'marks_number'

            self.sql.where(operation, (field_name, subquery), args_list=[int(self.view['marks_number'][2])])

    def __process_tags(self):
        if self.model == ReportUnknown:
            # Unknowns don't have tags
            return
        report_tags_model = {ReportSafe: SafeReportTag, ReportUnsafe: UnsafeReportTag}
        tags_model = {ReportSafe: SafeTag, ReportUnsafe: UnsafeTag}
        if 'tags' in self.view['columns']:
            subquery = RawQuery(report_tags_model[self.model])
            subquery.select('report_id')
            subquery.join('INNER', tags_model[self.model], 'id', 'tag_id')
            subquery.aggregate('tags', 'ARRAY_AGG({0})', ('tag', tags_model[self.model]))
            subquery.group_by('report_id')
            self.sql.join('LEFT OUTER', subquery, 'report_id', 'id', table_to=Report)
            self.sql.select(('tags', subquery))

        # Filter
        operation = '{0} = %s'
        if self.kwargs.get('tag') is not None:
            args = [self.kwargs['tag'].id]
        elif 'tags' in self.view:
            args = self.__get_tags(self.view['tags'][0])
            if len(args) > 1:
                operation = '{0} IN (%s)' % ', '.join(['%s'] * len(args))
        else:
            # There are no filters by tag(s)
            return
        subquery = RawQuery(report_tags_model[self.model])
        subquery.select('report_id')
        subquery.where(operation, 'tag_id', args_list=args)
        subquery.group_by('report_id')
        self.sql.join('INNER', subquery, 'report_id', 'id', table_to=Report)

    def __process_attributes(self):
        # Attributes will be get after pagination to get its order for columns

        # Sorting by attribute value
        if 'order' in self.view and self.view['order'][1] == 'attr':
            subquery = RawQuery(ReportAttr)
            subquery.join('INNER', Attr, 'id', 'attr_id')
            subquery.join('INNER', AttrName, 'id', 'name_id', table_to=Attr)
            subquery.select('report_id', ('value', Attr, 'order'))
            subquery.where('{0} = %s', ('name', AttrName), args_list=[self.view['order'][2]])
            self.sql.join('LEFT OUTER', subquery, 'report_id', 'id', table_to=Report)
            self.sql.order_by(('order', subquery), 'DESC' if self.view['order'][0] == 'up' else 'ASC')

        # Filter by attribute(s)
        operation = '{0} = %s'
        if self.kwargs.get('attr') is not None:
            args = [self.kwargs['attr'].id]
        elif 'attr' in self.view:
            args = list(Attr.objects.filter(**{
                'name__name__iexact': self.view['attr'][0], 'value__' + self.view['attr'][1]: self.view['attr'][2]
            }).values_list('id', flat=True))
            if len(args) == 0:
                raise EmptyQuery('There are no attributes found for filtering by it')

            if len(args) > 1:
                operation = '{0} IN (%s)' % ', '.join(['%s'] * len(args))
        else:
            # Ther are no filters by attribute
            return
        subquery = RawQuery(ReportAttr)
        subquery.select('report_id')
        subquery.where(operation, 'attr_id', args_list=args)
        subquery.group_by('report_id')
        self.sql.join('INNER', subquery, 'report_id', 'id', table_to=Report)

    def __process_component(self):
        if self.model != ReportUnknown:
            return
        self.sql.join('INNER', Component, 'id', 'component_id')
        self.sql.select(('name', Component, 'component'))

        if self.kwargs.get('component') is not None:
            self.sql.where('{0} = %s', ('id', Component), args_list=[int(self.kwargs['component'])])
        elif 'component' in self.view and self.view['component'][0] in {'iexact', 'istartswith', 'icontains'}:
            if self.view['component'][0] == 'iexact':
                value = self.view['component'][1]
                operation = 'UPPER({0}) = UPPER(%s)'
            elif self.view['component'][0] == 'istartswith':
                value = '%' + self.view['component'][1]
                operation = 'UPPER({0}) LIKE UPPER(%s)'
            elif self.view['component'][0] == 'icontains':
                value = '%' + self.view['component'][1] + '%'
                operation = 'UPPER({0}) LIKE UPPER(%s)'
            else:
                # Unsupported operation
                return
            self.sql.where(operation, ('name', Component), args_list=[value])

    def __process_problems(self):
        if self.model != ReportUnknown:
            return

        # Get problems list for each report
        if 'problems' in self.view['columns']:
            subquery = RawQuery(MarkUnknownReport)
            subquery.select('report_id')
            subquery.join('INNER', UnknownProblem, 'id', 'problem_id')
            subquery.aggregate('problems', 'ARRAY_AGG({0})', ('name', UnknownProblem))
            subquery.group_by('report_id')
            self.sql.join('LEFT OUTER', subquery, 'report_id', 'id', table_to=Report)
            self.sql.select(('problems', subquery))

        problem = self.kwargs.get('problem')
        if problem is None and 'problem' in self.view:
            try:
                problem = UnknownProblem.objects.get(name=self.view['problem'][0].strip())
            except ObjectDoesNotExist:
                raise EmptyQuery("Unknown problem wasn't found to filter by it")

        if isinstance(problem, UnknownProblem):
            subquery = RawQuery(MarkUnknownReport)
            subquery.select('report_id')
            subquery.where('{0} = %s', 'problem_id', args_list=[problem.id])
            subquery.group_by('report_id')
            self.sql.join('INNER', subquery, 'report_id', 'id', table_to=Report)
        elif problem == 0:
            subquery = RawQuery(MarkUnknownReport)
            subquery.select('report_id')
            subquery.group_by('report_id')
            self.sql.join('LEFT OUTER', subquery, 'report_id', 'id', table_to=Report)
            # Exclude all reports with marks
            self.sql.where('{0} IS NULL', ('report_id', subquery))

    def __filter_by_has_confirmed(self):
        if self.model != ReportUnknown and self.kwargs.get('confirmed', False):
            self.sql.where('{0} = %s', 'has_confirmed', args_list=[True])

    def __get_tags(self, tags_string):
        tags_model = SafeTag if self.model == ReportSafe else UnsafeTag
        view_tags = set(x.strip() for x in tags_string.split(';'))
        if '' in view_tags:
            view_tags.remove('')
        tags_ids = list(tags_model.objects.filter(tag__in=view_tags).values_list('id', flat=True))

        if len(tags_ids) != len(view_tags):
            raise EmptyQuery("One of the tags wasn't found for filtering by it")
        return tags_ids

    def __generate_sql(self):
        self.sql = RawQuery(self.model)

        if self.model == ReportUnsafe:
            self.sql.select('trace_id')

        # Add fields 'id' and 'parent_id' from Report
        self.sql.join('INNER', Report, 'id', 'report_ptr_id')
        self.sql.select(('id', Report), ('parent_id', Report))

        self.__filter_by_report()
        self.__process_verdict()
        self.__process_cpu_time()
        self.__process_wall_time()
        self.__process_memory()
        self.__process_marks()
        self.__process_tags()
        self.__process_attributes()
        self.__process_component()
        self.__process_problems()
        self.__filter_by_has_confirmed()

    def get_objects(self):
        if self._objects is None:
            try:
                self.__generate_sql()
            except EmptyQuery as e:
                logger.error(e)
                self._objects = []
            else:
                self._objects = self.sql.execute()
        return self._objects
