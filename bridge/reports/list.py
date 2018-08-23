from django.core.exceptions import ObjectDoesNotExist
from django.db import connection

from bridge.utils import logger
from bridge.vars import ASSOCIATION_TYPE

from reports.models import Component, Report, ReportSafe, ReportUnsafe, ReportUnknown, ReportComponentLeaf,\
    ReportAttr, Attr, AttrName
from marks.models import MarkSafeReport, MarkUnsafeReport, MarkUnknownReport, SafeTag, UnsafeTag,\
    SafeReportTag, UnsafeReportTag, UnknownProblem


class EmptyQuery(Exception):
    pass


class RawJoin:
    def __init__(self, join_type, table_from, table_to, on_from, on_to, name=None):
        self.type = join_type
        self.table_from = table_from  # 'name' or RawQuery instance
        self.table_to = table_to  # '"name"' or 'T1'
        self.on_from = on_from
        self.on_to = on_to
        self.name = name  # 'T2' or None

    @property
    def sql(self):
        if isinstance(self.table_from, RawQuery):
            if self.name is None:
                raise ValueError('Subquery join should have the name')
            table_from = '(%s) %s' % (self.table_from.get_objects_sql(), self.name)
            field_from = '{0}."{1}"'.format(self.name, self.on_from)
        elif self.name is None:
            table_from = '"%s"' % self.table_from
            field_from = '"{0}"."{1}"'.format(self.table_from, self.on_from)
        else:
            table_from = '"{0}" {1}'.format(self.table_from, self.name)
            field_from = '{0}."{1}"'.format(self.name, self.on_from)

        field_to = '{0}."{1}"'.format(self.table_to, self.on_to)

        return '{0} JOIN {1} ON ({2} = {3})'.format(self.type, table_from, field_to, field_from)


class RawQuery:
    def __init__(self, model):
        self._table = self.__table(model)
        self._fields = []

        self._joins = []
        self._joins_args = []

        self._where = []
        self._where_args = []

        self._having = []
        self._having_args = []

        self._order = None
        self._group_by = []
        self._names_in_use = set()

        self.sql = None

    def __table(self, model):
        return getattr(model, '_meta').db_table

    def __table_name(self, model):
        if model is None:
            return '"%s"' % self._table
        elif isinstance(model, str):
            return model
        return '"%s"' % self.__table(model)

    def __field_name(self, field, model):
        return '{0}."{1}"'.format(self.__table_name(model), field)

    def __get_unique_tname(self):
        t_id = 0
        if len(self._names_in_use) > 0:
            t_id += max(self._names_in_use)
        t_id += 1
        self._names_in_use.add(t_id)
        return 'T%s' % t_id

    def add_field(self, field, model=None, as_name=None):
        field_name = self.__field_name(field, model)
        if as_name is not None:
            field_name = '{0} as {1}'.format(field_name, as_name)
        if field_name not in self._fields:
            self._fields.append(field_name)

    def add_aggregation(self, aggr_name, aggregation, *args):
        formatted_fields = []
        for field, field_model in args:
            formatted_fields.append(self.__field_name(field, field_model))

        aggr_field = '{0} AS "{1}"'.format(aggregation.format(*formatted_fields), aggr_name)
        if aggr_field not in self._fields:
            self._fields.append(aggr_field)

    def add_join(self, join_type, model_from, field_from, field_to, model_to=None, named=False):
        # model_from is model class
        # model_to is eigher model ot string (name of previously joined table).

        if not named and self.__has_join(model_from, model_to):
            return

        name = None
        if named:
            name = self.__get_unique_tname()

        self._joins.append(RawJoin(join_type, self.__table(model_from), self.__table_name(model_to),
                                   field_from, field_to, name=name))
        return name

    def add_subquery_join(self, join_type, subquery, field_from, field_to, *args, model_to=None):
        name = self.__get_unique_tname()
        self._joins.append(RawJoin(join_type, subquery, self.__table_name(model_to), field_from, field_to, name=name))
        if len(args):
            self._joins_args.extend(args)
        return name

    def __has_join(self, model_from, model_to=None):
        # model_from is model class
        # model_to is eigher model ot string (name of previously joined table).

        table_from = self.__table(model_from)

        if model_to is None:
            table_to = self._table
        elif isinstance(model_to, str):
            table_to = model_to
        else:
            table_to = self.__table(model_to)

        for table_join in self._joins:
            if table_join.table_from == table_from and table_join.table_to == table_to:
                return True
        return False

    def add_where(self, field, filter_pattern, *args, model=None):
        # Expected that pattern has {0} for field name
        self._where.append(filter_pattern.format(self.__field_name(field, model)))
        self._where_args.extend(args)

    def add_having(self, field, filter_pattern, *args):
        self._having.append(filter_pattern.format(field))
        self._having_args.extend(args)

    def add_group_by(self, field, model=None):
        grp_by = self.__field_name(field, model)
        if grp_by not in self._group_by:
            self._group_by.append(grp_by)

    def add_order(self, field, order_direction, model=None):
        self._order = ('ORDER BY {0} %s NULLS LAST' % order_direction).format(self.__field_name(field, model))

    def get_objects_sql(self):
        sql = 'SELECT {0} FROM "{1}" {2}'.format(', '.join(self._fields), self._table,
                                                 ' '.join(list(j.sql for j in self._joins)))
        if len(self._where):
            sql += ' WHERE ({0})'.format(' AND '.join(self._where))
        if self._group_by:
            sql += ' GROUP BY {0}'.format(', '.join(self._group_by))
        if len(self._having):
            sql += ' HAVING ({0})'.format(' AND '.join(self._having))
        if self._order:
            sql += ' ' + self._order
        return sql

    def execute(self):
        if self.sql is None:
            self.sql = self.get_objects_sql()
        with connection.cursor() as cursor:
            # with open('sql_final.txt', mode='wb') as fp:
            #     fp.write(cursor.mogrify(self.sql, self._joins_args + self._where_args + self._having_args))
            cursor.execute(self.sql, self._joins_args + self._where_args + self._having_args)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


class LeavesQuery:
    def __init__(self, model, view, **kwargs):
        self.model = model
        if model not in (ReportSafe, ReportUnsafe, ReportUnknown):
            raise ValueError('Unknown leaf type: %s' % type(model))

        self.view = view
        self.page = kwargs.get('page', 1)
        self.kwargs = kwargs
        self.sql = RawQuery(self.model)
        self._objects = None

    def __filter_by_report(self):
        if 'report' not in self.kwargs:
            return
        leaf_field = {ReportSafe: 'safe_id', ReportUnsafe: 'unsafe_id', ReportUnknown: 'unknown_id'}
        subquery = RawQuery(ReportComponentLeaf)
        subquery.add_field(leaf_field[self.model])
        subquery.add_where('report_id', '{0} = %s')
        subquery.add_group_by(leaf_field[self.model])
        self.sql.add_subquery_join('INNER', subquery, leaf_field[self.model], 'id',
                                   self.kwargs['report'].id, model_to=Report)

    def __process_verdict(self):
        if self.model == ReportUnknown:
            # Unknowns don't have verdicts
            return

        # Add column if needed
        if 'report_verdict' in self.view['columns']:
            self.sql.add_field('verdict')

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

        self.sql.add_where('verdict', operation, *args)

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
        self.sql.add_field('cpu_time')

        # Filter by cpu time
        if 'parent_cpu' in self.view:
            operation = '{0} '
            operation += '<' if self.view['parent_cpu'][0] == 'lt' else '>'
            operation += ' %s'
            value = self.__get_ms(self.view['parent_cpu'][1], self.view['parent_cpu'][2])
            if self.model == ReportUnknown:
                self.sql.add_where('cpu_time', '{0} NOTNULL')
            self.sql.add_where('cpu_time', operation, value)

        # Order by cpu time
        if 'order' in self.view and self.view['order'][1] == 'parent_cpu':
            self.sql.add_order('cpu_time', 'DESC' if self.view['order'][0] == 'up' else 'ASC')

    def __process_wall_time(self):
        if 'verifiers:wall' not in self.view['columns']:
            # We are not going to filter/sort by wall time if it isn't shown
            return
        self.sql.add_field('wall_time')

        # Filter by wall time
        if 'parent_wall' in self.view:
            operation = '{0} '
            operation += '<' if self.view['parent_wall'][0] == 'lt' else '>'
            operation += ' %s'
            value = self.__get_ms(self.view['parent_wall'][1], self.view['parent_wall'][2])
            if self.model == ReportUnknown:
                self.sql.add_where('wall_time', '{0} NOTNULL')
            self.sql.add_where('wall_time', operation, value)

        # Order by wall time
        if 'order' in self.view and self.view['order'][1] == 'parent_wall':
            self.sql.add_order('wall_time', 'DESC' if self.view['order'][0] == 'up' else 'ASC')

    def __process_memory(self):
        if 'verifiers:memory' not in self.view['columns']:
            # We are not going to filter/sort by memory if it isn't shown
            return
        self.sql.add_field('memory')

        # Filter by memory
        if 'parent_memory' in self.view:
            operation = '{0} '
            operation += '<' if self.view['parent_memory'][0] == 'lt' else '>'
            operation += ' %s'

            value = float(self.view['parent_memory'][1].replace(',', '.'))
            if self.view['parent_memory'][2] == 'KB':
                value *= 1024
            elif self.view['parent_memory'][2] == 'MB':
                value *= 1024 * 1024
            elif self.view['parent_memory'][2] == 'GB':
                value *= 1024 ** 3
            if self.model == ReportUnknown:
                self.sql.add_where('memory', '{0} NOTNULL')
            self.sql.add_where('memory', operation, value)

        # Order by memory
        if 'order' in self.view and self.view['order'][1] == 'parent_memory':
            self.sql.add_order('memory', 'DESC' if self.view['order'][0] == 'up' else 'ASC')

    def __process_marks(self):
        if 'marks_number' not in self.view['columns']:
            # We are not going to fitler by number of (confirmed) marks if it isn't shown
            return

        # Is confirmed number shown?
        with_confirmed = 'hidden' not in self.view or 'confirmed_marks' not in self.view['hidden']

        subquery_model = {ReportSafe: MarkSafeReport, ReportUnsafe: MarkUnsafeReport, ReportUnknown: MarkUnknownReport}
        # Subquery with marks numbers
        subquery = RawQuery(subquery_model[self.model])
        subquery.add_field('report_id')
        subquery.add_aggregation('marks_number', 'COUNT({0})', ('id', subquery_model[self.model]))

        if with_confirmed:
            subquery.add_aggregation(
                'confirmed', "COUNT(CASE WHEN {0} = '%s' THEN 1 ELSE NULL END)" % ASSOCIATION_TYPE[1][0],
                ('type', subquery_model[self.model])
            )
        subquery.add_group_by('report_id')
        marks_sq_name = self.sql.add_subquery_join('LEFT OUTER', subquery, 'report_id', 'id', model_to=Report)

        self.sql.add_field('marks_number', model=marks_sq_name)
        if with_confirmed:
            self.sql.add_field('confirmed', model=marks_sq_name)

        # Filter
        if 'marks_number' not in self.view:
            # If there are no filters by numbers, just return
            return

        operation = '{0} '
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
        self.sql.add_where(field_name, operation, int(self.view['marks_number'][2]), model=marks_sq_name)

    def __process_tags(self):
        if self.model == ReportUnknown:
            # Unknowns don't have tags
            return
        report_tags_model = {ReportSafe: SafeReportTag, ReportUnsafe: UnsafeReportTag}
        tags_model = {ReportSafe: SafeTag, ReportUnsafe: UnsafeTag}
        if 'tags' in self.view['columns']:
            subquery = RawQuery(report_tags_model[self.model])
            subquery.add_field('report_id')
            subquery.add_join('INNER', tags_model[self.model], 'id', 'tag_id')
            subquery.add_aggregation('tags', 'ARRAY_AGG({0})', ('tag', tags_model[self.model]))
            subquery.add_group_by('report_id')
            tags_sq_name = self.sql.add_subquery_join('LEFT OUTER', subquery, 'report_id', 'id', model_to=Report)
            self.sql.add_field('tags', model=tags_sq_name)

        # Filter
        operation = '{0} = %s'
        if self.kwargs.get('tag') is not None:
            operation %= self.kwargs['tag'].id
        elif 'tags' in self.view:
            tags_ids = tags_model[self.model].objects\
                .filter(tag__in=set(x.strip() for x in self.view['tags'][0].split(';'))).values_list('id', flat=True)

            if len(tags_ids) == 0:
                raise EmptyQuery('There are no tags found for filtering by it')
            elif len(tags_ids) == 1:
                operation %= tags_ids[0]
            else:
                operation = '{0} IN (%s)' % ', '.join(str(t) for t in tags_ids)
        else:
            # There are no filters by tag(s)
            return
        subquery = RawQuery(report_tags_model[self.model])
        subquery.add_field('report_id')
        subquery.add_where('tag_id', operation)
        subquery.add_group_by('report_id')
        self.sql.add_subquery_join('INNER', subquery, 'report_id', 'id', model_to=Report)

    def __process_attributes(self):
        # Attributes will be get after pagination
        # subquery = RawQuery(ReportAttr)
        # subquery.add_field('report_id')
        # subquery.add_join('INNER', Attr, 'id', 'attr_id', model_to=ReportAttr)
        # subquery.add_join('INNER', AttrName, 'id', 'name_id', model_to=Attr)
        # subquery.add_aggregation('attributes', 'JSON_OBJECT_AGG({0}, {1})', ('name', AttrName), ('value', Attr))
        # subquery.add_group_by('report_id')
        # sq_name = self.sql.add_subquery_join('LEFT OUTER', subquery, 'report_id', 'id', model_to=Report)
        # self.sql.add_field('attributes', model=sq_name)

        # Sorting by attribute value
        if 'order' in self.view and self.view['order'][1] == 'attr':
            subquery = RawQuery(ReportAttr)
            subquery.add_field('report_id')
            subquery.add_join('INNER', Attr, 'id', 'attr_id')
            subquery.add_join('INNER', AttrName, 'id', 'name_id', model_to=Attr)
            subquery.add_field('value', model=Attr, as_name='order')
            subquery.add_where('name', '{0} = %s', model=AttrName)
            sq_name = self.sql.add_subquery_join('LEFT OUTER', subquery, 'report_id', 'id',
                                                 self.view['order'][2], model_to=Report)
            self.sql.add_order('order', 'DESC' if self.view['order'][0] == 'up' else 'ASC', model=sq_name)

        # Filter by attribute(s)
        operation = '{0} = %s'
        if self.kwargs.get('attr') is not None:
            operation %= self.kwargs['attr'].id
        elif 'attr' in self.view:
            attrs_ids = Attr.objects.filter(**{
                'name__name__iexact': self.view['attr'][0], 'value__' + self.view['attr'][1]: self.view['attr'][2]
            }).values_list('id', flat=True)
            if len(attrs_ids) == 0:
                raise EmptyQuery('There are no attributes found for filtering by it')
            elif len(attrs_ids) == 1:
                operation %= attrs_ids[0]
            else:
                operation = '{0} IN (%s)' % ', '.join(str(a_id) for a_id in attrs_ids)
        else:
            # Ther are no filters by attribute
            return
        subquery = RawQuery(ReportAttr)
        subquery.add_field('report_id')
        subquery.add_where('attr_id', operation)
        subquery.add_group_by('report_id')
        self.sql.add_subquery_join('INNER', subquery, 'report_id', 'id', model_to=Report)

    def __process_component(self):
        if self.model != ReportUnknown:
            return
        self.sql.add_join('INNER', Component, 'id', 'component_id')
        self.sql.add_field('name', model=Component, as_name='component')

        if self.kwargs.get('component') is not None:
            self.sql.add_where('id', '{0} = %s' % int(self.kwargs['component']), model=Component)
        elif 'component' in self.view and self.view['component'][0] in {'iexact', 'istartswith', 'icontains'}:
            if self.view['component'][0] == 'iexact':
                self.sql.add_where('name', 'UPPER({0}) = UPPER(%s)', self.view['component'][1], model=Component)
            elif self.view['component'][0] == 'istartswith':
                re_pattern = '%%%s' % self.view['component'][1]
                self.sql.add_where('name', 'UPPER({0}) LIKE UPPER(%s)', re_pattern, model=Component)
            elif self.view['component'][0] == 'icontains':
                re_pattern = '%%%s%%' % self.view['component'][1]
                self.sql.add_where('name', 'UPPER({0}) LIKE UPPER(%s)', re_pattern, model=Component)

    def __process_problems(self):
        if self.model != ReportUnknown:
            return

        # Get problems list for each report
        if 'problems' in self.view['columns']:
            subquery = RawQuery(MarkUnknownReport)
            subquery.add_field('report_id')
            subquery.add_join('INNER', UnknownProblem, 'id', 'problem_id')
            subquery.add_aggregation('problems', 'ARRAY_AGG({0})', ('name', UnknownProblem))
            subquery.add_group_by('report_id')
            problems_sq_name = self.sql.add_subquery_join('LEFT OUTER', subquery, 'report_id', 'id', model_to=Report)
            self.sql.add_field('problems', model=problems_sq_name)

        problem = self.kwargs.get('problem')
        if problem is None and 'problem' in self.view:
            try:
                problem = UnknownProblem.objects.get(name=self.view['problem'][0].strip())
            except ObjectDoesNotExist:
                raise EmptyQuery("Unknown problem wasn't found to filter by it")

        if isinstance(problem, UnknownProblem):
            subquery = RawQuery(MarkUnknownReport)
            subquery.add_field('report_id')
            subquery.add_where('problem_id', '{0} = %s' % problem.id)
            subquery.add_group_by('report_id')
            self.sql.add_subquery_join('INNER', subquery, 'report_id', 'id', model_to=Report)
        elif problem == 0:
            subquery = RawQuery(MarkUnknownReport)
            subquery.add_field('report_id')
            subquery.add_group_by('report_id')
            sq_name = self.sql.add_subquery_join('LEFT OUTER', subquery, 'report_id', 'id', model_to=Report)
            # Exclude all reports with marks
            self.sql.add_where('report_id', '{0} IS NULL', model=sq_name)

    def __filter_by_has_confirmed(self):
        if self.model != ReportUnknown and self.kwargs.get('confirmed', False):
            self.sql.add_where('has_confirmed', '{0} = %s', True)

    def __generate_sql(self):
        if self.model == ReportUnsafe:
            self.sql.add_field('trace_id')

        # Add fields 'id' and 'parent_id' from Report
        self.sql.add_join('INNER', Report, 'id', 'report_ptr_id')
        self.sql.add_field('id', model=Report)
        self.sql.add_field('parent_id', model=Report)

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
