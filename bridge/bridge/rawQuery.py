from django.db import connection
from django.db.models import Model
from django.utils.functional import cached_property


def is_model(arg):
    return isinstance(arg, type) and issubclass(arg, Model)


class EmptyQuery(Exception):
    pass


# Doesn't support annnotating the name for real table join
class RawJoin:
    def __init__(self, join_type, table_from, table_to, *joins_on):
        self.type = join_type
        self._t_from = table_from  # model or RawQuery instance
        self._t_to = table_to  # model or table name (real or annotated)
        self._joins_on = joins_on

    @cached_property
    def _table_from(self):
        if isinstance(self._t_from, RawQuery):
            return self._t_from.name
        elif is_model(self._t_from):
            return getattr(self._t_from, '_meta').db_table
        raise ValueError('Unknown join table type: %s' % type(self._t_from))

    @cached_property
    def _table_to(self):
        if isinstance(self._t_to, str):
            return self._t_to
        elif is_model(self._t_to):
            return getattr(self._t_to, '_meta').db_table
        raise ValueError('Unknown join table type: %s' % type(self._t_to))

    def _clause(self, field_from, field_to):
        return '"{0}"."{1}" = "{2}"."{3}"'.format(self._table_from, field_from, self._table_to, field_to)

    def __get_join_clause(self):
        if len(self._joins_on) == 2 and all(isinstance(x, str) for x in self._joins_on):
            return self._clause(*self._joins_on)
        elif len(self._joins_on) > 0 and all(isinstance(x, tuple) and len(x) == 2 for x in self._joins_on):
            return ' AND '.join(list(self._clause(*c_args) for c_args in self._joins_on))
        raise ValueError('Unknown join clause arguments: %s' % str(self._joins_on))

    def __get_target(self):
        if isinstance(self._t_from, RawQuery):
            return '(%s) "%s"' % (self._t_from.sql, self._t_from.name)
        elif is_model(self._t_from):
            return '"%s"' % getattr(self._t_from, '_meta').db_table
        raise ValueError('Unknown join table type: %s' % type(self._t_from))

    @property
    def sql(self):
        return '{0} JOIN {1} ON ({2})'.format(self.type, self.__get_target(), self.__get_join_clause())

    @property
    def subquery(self):
        return self._t_from if isinstance(self._t_from, RawQuery) else None

    @property
    def join_args(self):
        if isinstance(self._t_from, RawQuery):
            return self._t_from.sql_args
        return []


class RawQuery:
    """
    All fields in methods' arguments are either string (field name of current table) or tuple with length 1..3
    Structure of tuple is: (<field name: string>, <table: Model or RawQuery instance>, <name: string>)
    """
    def __init__(self, model):
        self.model = model
        self.name = None
        self._names_in_use = set()

        self._fields = []
        self._fields_args = []

        self._joins = []

        self._where = []
        self._where_args = []

        self._having = []
        self._having_args = []

        self._group_by = []

        self._order = None
        self._order_args = []

    @cached_property
    def table_name(self):
        if not is_model(self.model):
            raise ValueError('Subclass of django Model expected, got: %s (%s)' % (self.model, type(self.model)))
        return getattr(self.model, '_meta').db_table

    def __unique_name(self):
        t_id = 0
        if len(self._names_in_use) > 0:
            t_id += max(self._names_in_use)
        t_id += 1
        self._names_in_use.add(t_id)
        return 'T%s' % t_id

    def __field_sql(self, field, table=None, name=None):
        # Get table name
        if table is None:
            table_name = self.table_name
        elif isinstance(table, RawQuery):
            if table.name is None:
                raise ValueError('RawQuery name must be set')
            table_name = table.name
        elif is_model(table):
            table_name = getattr(table, '_meta').db_table
        else:
            raise ValueError('Unknown table type: %s' % table)

        # Field in sql format
        field_sql = '"{0}"."{1}"'.format(table_name, field)

        # Annotate field with name
        if name is not None:
            field_sql += ' AS "%s"' % name

        return field_sql

    def __parse_fields(self, *fields):
        fields_parsed = []
        for field in fields:
            if isinstance(field, str):
                fields_parsed.append(self.__field_sql(field))
            elif isinstance(field, tuple):
                if len(field) == 1:
                    fields_parsed.append(self.__field_sql(field[0]))
                elif len(field) == 2:
                    fields_parsed.append(self.__field_sql(field[0], table=field[1]))
                elif len(field) == 3:
                    fields_parsed.append(self.__field_sql(field[0], table=field[1], name=field[2]))
            else:
                raise ValueError('Unknown field format: %s' % str(field))
        return fields_parsed

    def select(self, *fields):
        self._fields.extend(self.__parse_fields(*fields))

    def aggregate(self, name, aggregation, *fields, args_list=None):
        self._fields.append('{0} AS "{1}"'.format(aggregation.format(*self.__parse_fields(*fields)), name))
        if isinstance(args_list, list):
            self._fields_args.extend(args_list)

    def join(self, join_type, table_from, *joins_on, table_to=None):
        if isinstance(table_from, RawQuery):
            # Add unique table name for subquery join
            table_from.name = self.__unique_name()
        self._joins.append(RawJoin(join_type, table_from, table_to if table_to is not None else self.model, *joins_on))

    def where(self, filter_pattern, *fields, args_list=None):
        self._where.append(filter_pattern.format(*self.__parse_fields(*fields)))
        if isinstance(args_list, list):
            self._where_args.extend(args_list)

    def having(self, aggregation, *fields, args_list=None):
        self._having.append(aggregation.format(*self.__parse_fields(*fields)))
        if isinstance(args_list, list):
            self._having_args.extend(args_list)

    def group_by(self, *fields):
        self._group_by.extend(self.__parse_fields(*fields))

    def order_by(self, field, order_direction):
        # Ordering only by one field is supported now
        self._order = 'ORDER BY {0} {1} NULLS LAST'.format(self.__parse_fields(field)[0], order_direction)

    def order_by_aggregation(self, aggregation, order_direction, *fields, args_list=None):
        target = aggregation.format(*self.__parse_fields(*fields))
        self._order = 'ORDER BY {0} {1} NULLS LAST'.format(target, order_direction)

        if isinstance(args_list, list):
            self._order_args = args_list[:]

    @cached_property
    def sql(self):
        sql_list = ['SELECT', ', '.join(self._fields), 'FROM', '"%s"' % self.table_name]
        if len(self._joins):
            sql_list.extend(list(j.sql for j in self._joins))
        if len(self._where):
            sql_list.append('WHERE ({0})'.format(' AND '.join(self._where)))
        if len(self._group_by):
            sql_list.append('GROUP BY {0}'.format(', '.join(self._group_by)))
        if len(self._having):
            sql_list.append('HAVING ({0})'.format(' AND '.join(self._having)))
        if self._order:
            sql_list.append(self._order)
        # return '\n'.join(sql_list)
        return ' '.join(sql_list)

    def execute(self):
        with connection.cursor() as cursor:
            # with open('sql_final.txt', mode='wb') as fp:
            #     fp.write(cursor.mogrify(self.sql, self.sql_args))
            cursor.execute(self.sql, self.sql_args)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    @property
    def sql_args(self):
        args = self._fields_args[:]
        for j in self._joins:
            # Recursion
            args.extend(j.join_args)
        args.extend(self._where_args)
        args.extend(self._having_args)
        return args
