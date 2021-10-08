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


def calculate_load_order(logger, modules):
    """
    Get dependencies between modules and output modules list with order of possible loading according to solution of a
    topological sorting problem yielded with Tarjan algorithm.

    :param logger: logging object.
    :param modules: Dictionary with modules dependencies.
    :return: List with modules names.
    """
    sorted_list = []

    unmarked = sorted(list(modules))
    marked = {}
    while unmarked:
        selected = unmarked.pop(0)
        if selected not in marked:
            __visit(logger, selected, marked, sorted_list, modules)

    return sorted_list


def __visit(logger, selected, marked, sorted_list, modules):
    if selected in marked and marked[selected] == 0:
        logger.debug('Given graph is not a DAG')

    elif selected not in marked:
        marked[selected] = 0

        if selected in modules:
            for m in modules[selected]:
                __visit(logger, m, marked, sorted_list, modules)

        marked[selected] = 1
        sorted_list.append(selected)
