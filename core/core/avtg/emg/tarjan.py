#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
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

def calculate_load_order(logger, modules):
    sorted_list = []

    unmarked = list(sorted(list(modules)))
    marked = {}
    while(unmarked):
        selected = unmarked.pop(0)
        if selected not in marked:
            visit(logger, selected, marked, sorted_list, modules)

    return sorted_list


def visit(logger, selected, marked, sorted_list, modules):
    if selected in marked and marked[selected] == 0:
        logger.debug('Given graph is not a DAG')

    elif selected not in marked:
        marked[selected] = 0

        if selected in modules:
            for m in modules[selected]:
                visit(logger, m, marked, sorted_list, modules)

        marked[selected] = 1
        sorted_list.append(selected)
