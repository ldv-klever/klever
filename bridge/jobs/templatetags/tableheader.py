from django import template

register = template.Library()


class TableHeader(template.Node):
    def __init__(self, columns, titles):
        self._columns = columns
        self._titles = titles

    def render_th(self, colspan, rowspan, title):
        return f'<th colspan="{colspan}" rowspan="{rowspan}">{title}</th>'

    def render_items(self, columns, titles):
        max_depth = 0
        column_matrix = []
        for column in columns:
            column_list = column.split(':')
            max_depth = max(max_depth, len(column_list))

            column_prefix_list = []
            for i in range(len(column_list)):
                column_prefix_list.append(':'.join(column_list[:(i + 1)]))
            column_matrix.append(column_prefix_list)

        header_html = ''
        for row in range(max_depth):
            prev_cell = None
            header_html += '<tr>'
            for column in column_matrix:
                if len(column) <= row:
                    continue
                if prev_cell:
                    if column[row] == prev_cell['column']:
                        # Just stretch the previous column
                        prev_cell['columns'] += 1
                        continue
                    else:
                        header_html += self.render_th(prev_cell['columns'], prev_cell['rows'], prev_cell['title'])

                prev_cell = {'column': column[row], 'rows': 1, 'columns': 1}
                if column[row] in titles:
                    prev_cell['title'] = titles[column[row]]
                else:
                    prev_cell['title'] = column[row].split(':')[-1]

                if len(column) == row + 1:
                    # The last item in the list, need vertical stretch
                    prev_cell['rows'] = max_depth - len(column) + 1
            if prev_cell:
                header_html += self.render_th(prev_cell['columns'], prev_cell['rows'], prev_cell['title'])
            header_html += '</tr>'
        return header_html

    def render(self, context):
        columns = self._columns.resolve(context)
        titles = self._titles.resolve(context) or {}
        return self.render_items(columns, titles)


@register.tag
def tableheader(parser, token):
    try:
        tag_name, columns, titles = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError('%r tag requires exactly two arguments: '
                                           'list of columns and its titles' % token.contents.split()[0])
    return TableHeader(parser.compile_filter(columns), parser.compile_filter(titles))
