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


# TODO: use mixin?
class Header:
    def __init__(self, columns, titles):
        self.columns = columns
        self.titles = titles
        self.struct = self.head_struct()

    def head_struct(self):
        col_data = []
        depth = self.__max_depth()
        for d in range(1, depth + 1):
            col_data.append(self.__cellspan_level(d, depth))
        return col_data

    def __max_depth(self):
        max_depth = 0
        if len(self.columns):
            max_depth = 1
        for col in self.columns:
            depth = len(col.split(':'))
            if depth > max_depth:
                max_depth = depth
        return max_depth

    def __cellspan_level(self, lvl, max_depth):
        columns_of_lvl = []
        prev_col = ''
        cnt = 0
        for col in self.columns:
            col_start = ''
            col_parts = col.split(':')
            if len(col_parts) >= lvl:
                col_start = ':'.join(col_parts[:lvl])
                if col_start == prev_col:
                    cnt += 1
                else:
                    if prev_col != '':
                        columns_of_lvl.append([prev_col, cnt])
                    cnt = 1
            else:
                if prev_col != '':
                    columns_of_lvl.append([prev_col, cnt])
                cnt = 0
            prev_col = col_start

        if len(prev_col) > 0 and cnt > 0:
            columns_of_lvl.append([prev_col, cnt])

        columns_data = []
        for col in columns_of_lvl:
            nrows = max_depth - lvl + 1
            for column in self.columns:
                if column.startswith(col[0] + ':') and col[0] != column:
                    nrows = 1
                    break
            columns_data.append({
                'column': col[0].split(':')[-1],
                'rows': nrows,
                'columns': col[1],
                'title': self.__title(col[0], col[0].split(':')[-1]),
            })
        return columns_data

    def __title(self, column, last_part):
        if column in self.titles:
            return self.titles[column]
        return last_part


class ComplexHeaderMixin:
    def head_struct(self, columns, titles):
        data = []

        max_depth = 0
        column_matrix = []
        for column in columns:
            column_list = column.split(':')
            max_depth = max(max_depth, len(column_list))

            column_prefix_list = []
            for i in range(len(column_list)):
                column_prefix_list.append(':'.join(column_list[:(i + 1)]))
            column_matrix.append(column_prefix_list)

        for row in range(max_depth):
            prev_cell = None
            row_data = []
            for column in column_matrix:
                if len(column) <= row:
                    continue
                if prev_cell:
                    if column[row] == prev_cell['column']:
                        # Just stretch the previous column
                        prev_cell['columns'] += 1
                        continue
                    else:
                        row_data.append(prev_cell)

                prev_cell = {
                    'column': column[row], 'rows': 1, 'columns': 1,
                    'title': titles.get(column[row], column[row])
                }
                if len(column) == row + 1:
                    # The last item in the list, need vertical stretch
                    prev_cell['rows'] = max_depth - len(column) + 1
            if prev_cell:
                row_data.append(prev_cell)
            data.append(row_data)

        return data
