from datetime import timedelta

from django.utils.functional import cached_property
from django.utils.timezone import now

from bridge.utils import logger
from bridge.rawQuery import RawQuery, EmptyQuery

from users.models import User
from reports.models import Component, Attr, AttrName
from marks.models import MarkSafe, MarkUnsafe, MarkUnknown, MarkSafeHistory, MarkUnsafeHistory, MarkUnknownHistory,\
    MarkSafeReport, MarkUnsafeReport, MarkUnknownReport,\
    MarkSafeTag, MarkUnsafeTag, SafeTag, UnsafeTag, MarkSafeAttr, MarkUnsafeAttr, MarkUnknownAttr


class ListQuery:
    def __init__(self, model, view):
        self.model = model
        if model not in (MarkSafe, MarkUnsafe, MarkUnknown):
            raise ValueError('Unknown mark model: %s' % type(model))

        self.view = view

        self._objects = None
        self._version_joined = False
        self._links_subquery = None

    @cached_property
    def _order_direction(self):
        if 'order' not in self.view:
            return 'ASC'
        return 'DESC' if self.view['order'][0] == 'up' else 'ASC'

    def __join_version(self):
        version_model_map = {MarkSafe: MarkSafeHistory, MarkUnsafe: MarkUnsafeHistory, MarkUnknown: MarkUnknownHistory}
        version_model = version_model_map[self.model]
        if self._version_joined:
            return version_model

        self.sql.join('INNER', version_model, ('mark_id', 'id'), ('version', 'version'))
        self._version_joined = True
        return version_model

    def __join_links(self):
        if self._links_subquery is None:
            # Not joined yet
            sq_model = {MarkSafe: MarkSafeReport, MarkUnsafe: MarkUnsafeReport, MarkUnknown: MarkUnknownReport}
            self._links_subquery = RawQuery(sq_model[self.model])
            self._links_subquery.select('mark_id')
            self._links_subquery.group_by('mark_id')
            self.sql.join('LEFT OUTER', self._links_subquery, 'mark_id', 'id')
        return self._links_subquery

    def __process_num_of_links(self):
        links_aggr = '(CASE WHEN {0} IS NULL THEN 0 ELSE {0} END)'

        subquery = self.__join_links()
        subquery.aggregate('num_of_links', 'COUNT({0})', 'id')
        self.sql.aggregate('num_of_links', links_aggr, ('num_of_links', subquery))
        if self.model == MarkUnsafe:
            subquery.aggregate('broken_links', 'COUNT({0}) FILTER (WHERE {1} IS NOT NULL)', 'id', 'error')
            self.sql.aggregate('broken_links', '(CASE WHEN {0} IS NULL THEN 0 ELSE {0} END)',
                               ('broken_links', subquery))

        if 'order' in self.view and self.view['order'][1] == 'num_of_links':
            self.sql.order_by_aggregation(links_aggr, self._order_direction, ('num_of_links', subquery))

    def __process_total_similarity(self):
        if self.model != MarkUnsafe:
            # Only unsafe marks have similarity
            return
        total_sim_aggr = '(CASE WHEN {0} IS NULL THEN 0.0 ELSE {0} END)'
        subquery = self.__join_links()
        subquery.aggregate('total_similarity', '(CASE WHEN COUNT({0}) = 0 THEN 0 ELSE (SUM({0})/COUNT({0})) END)',
                           'result')
        self.sql.aggregate('total_similarity', total_sim_aggr, ('total_similarity', subquery))

        if 'order' in self.view and self.view['order'][1] == 'total_similarity':
            self.sql.order_by_aggregation(total_sim_aggr, self._order_direction, ('total_similarity', subquery))

    def __process_component(self):
        if self.model != MarkUnknown:
            # Only unknown marks have component
            return

        self.sql.join('INNER', Component, 'id', 'component_id')
        self.sql.select(('name', Component, 'component'))

        # Filter by component
        if 'component' in self.view:
            if self.view['component'][0] == 'is':
                operation = '{0} = %s'
                args = [self.view['component'][1]]
            else:
                # startswith
                operation = 'UPPER({0}) LIKE UPPER(%s)'
                args = [self.view['component'][1] + '%']
            self.sql.where(operation, ('name', Component), args_list=args)

        # Sort by component name
        if 'order' in self.view and self.view['order'][1] == 'component':
            self.sql.order_by(('name', Component), self._order_direction)

    def __process_pattern(self):
        if self.model != MarkUnknown:
            # Only unknown marks have pattern
            return
        self.sql.select(('problem_pattern', None, 'pattern'))

    def __process_verdict(self):
        if self.model == MarkUnknown:
            # Unknown marks don't have verdict
            return

        self.sql.select('verdict')

        # Filter
        if 'verdict' in self.view:
            operation = "{0} = %s"
            if self.view['verdict'][0] != 'is':
                operation = 'NOT (%s)' % operation
            self.sql.where(operation, 'verdict', args_list=[self.view['verdict'][1]])

    def __process_tags(self):
        if self.model == MarkUnknown:
            # Unknown marks don't have tags
            return
        v_model = self.__join_version()
        sq_model = MarkSafeTag if self.model == MarkSafe else MarkUnsafeTag
        tags_model = SafeTag if self.model == MarkSafe else UnsafeTag

        subquery = RawQuery(sq_model)
        subquery.select('mark_version_id')
        subquery.join('INNER', tags_model, 'id', 'tag_id')
        subquery.aggregate('tags', 'ARRAY_AGG({0})', ('tag', tags_model))
        subquery.group_by('mark_version_id')
        self.sql.join('LEFT OUTER', subquery, 'mark_version_id', 'id', table_to=v_model)
        self.sql.select(('tags', subquery))

        if 'tags' in self.view:
            args = self.__get_tags(self.view['tags'][0])
            operation = 'COUNT({0}) FILTER (WHERE {0} IN (%s))' % ','.join(['%s'] * len(args))
            subquery.aggregate('tags_filter_cnt', operation, 'tag_id', args_list=args)
            self.sql.where('{0} = %s', ('tags_filter_cnt', subquery), args_list=[len(args)])

    def __process_status(self):
        self.sql.select('status')

        # Filter
        if 'status' in self.view:
            operation = "{0} = %s"
            if self.view['status'][0] != 'is':
                operation = 'NOT (%s)' % operation
            self.sql.where(operation, 'status', args_list=[self.view['status'][1]])

    def __process_author(self):
        self.sql.join('LEFT OUTER', User, 'id', 'author_id')
        self.sql.select('author_id', ('first_name', User), ('last_name', User))

        if 'author' in self.view:
            self.sql.where('{0} = %s', 'author_id', args_list=[int(self.view['author'][0])])

    def __process_change_date(self):
        self.sql.select('change_date')

        if 'change_date' in self.view:
            operation = '{0} ' + ('<' if self.view['change_date'][0] == 'older' else '>') + ' %s'
            # UTC+0
            value = now() - timedelta(**{self.view['change_date'][2]: int(self.view['change_date'][1])})
            self.sql.where(operation, 'change_date', args_list=[value])

        if 'order' in self.view and self.view['order'][1] == 'change_date':
            self.sql.order_by('change_date', self._order_direction)

    def __process_format(self):
        self.sql.select('format')

    def __process_source(self):
        self.sql.select(('type', None, 'source'))

        # Filter by source type
        if 'source' in self.view:
            operation = "{0} = %s"
            if self.view['source'][0] != 'is':
                operation = 'NOT (%s)' % operation
            self.sql.where(operation, 'type', args_list=[self.view['source'][1]])

    def __filter_by_attribute(self):
        mark_attrs_model = {MarkSafe: MarkSafeAttr, MarkUnsafe: MarkUnsafeAttr, MarkUnknown: MarkUnknownAttr}

        if 'attr' in self.view:
            v_model = self.__join_version()
            args = list(Attr.objects.filter(**{
                'name__name__iexact': self.view['attr'][0], 'value__' + self.view['attr'][1]: self.view['attr'][2]
            }).values_list('id', flat=True))
            if len(args) == 0:
                raise EmptyQuery('There are no attributes found for filtering by it')

            operation = ('{0} IN (%s)' % ', '.join(['%s'] * len(args))) if len(args) > 1 else '{0} = %s'

            subquery = RawQuery(mark_attrs_model[self.model])
            subquery.select('mark_id')
            subquery.where(operation, 'attr_id', args_list=args)
            subquery.group_by('mark_id')
            self.sql.join('INNER', subquery, 'mark_id', 'id', table_to=v_model)

        if 'order' in self.view and self.view['order'][1] == 'attr':
            v_model = self.__join_version()
            subquery = RawQuery(mark_attrs_model[self.model])
            subquery.join('INNER', Attr, 'id', 'attr_id')
            subquery.join('INNER', AttrName, 'id', 'name_id', table_to=Attr)
            subquery.where('{0} = %s', ('name', AttrName), args_list=[self.view['order'][2]])
            subquery.group_by('mark_id', ('value', Attr))
            subquery.select('mark_id', ('value', Attr, 'order_attr_value'))

            self.sql.join('LEFT OUTER', subquery, 'mark_id', 'id', table_to=v_model)
            self.sql.order_by(('order_attr_value', subquery), self._order_direction)

    def __get_tags(self, tags_string):
        tags_model = SafeTag if self.model == MarkSafe else UnsafeTag
        view_tags = set(x.strip() for x in tags_string.split(';'))
        if '' in view_tags:
            view_tags.remove('')
        tags_ids = list(tags_model.objects.filter(tag__in=view_tags).values_list('id', flat=True))

        if len(tags_ids) != len(view_tags):
            raise EmptyQuery("One of the tags wasn't found for filtering by it")
        return tags_ids

    def __generate_sql(self):
        self.sql = RawQuery(self.model)
        self.sql.select('id')
        # Default sorting by mark id (it can be overwritten later)
        self.sql.order_by('id', 'ASC')

        for col_name in self.view['columns']:
            method = '_{0}__process_{1}'.format(self.__class__.__name__, col_name)
            if hasattr(self, method):
                getattr(self, method)()
        self.__filter_by_attribute()

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
