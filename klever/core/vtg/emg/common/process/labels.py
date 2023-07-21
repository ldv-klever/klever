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


class Access:
    """
    Class to represent expressions based on labels from process descriptions.

    For instance: %mylabel%.
    """

    def __init__(self, expression):
        self.expression = expression
        self.label = None
        self.list_access = None

    def __str__(self):
        return self.expression

    def __eq__(self, other):
        return str(self) == str(other)

    def __lt__(self, other):
        return str(self) < str(other)


class Label:
    """
    The class represent Label from process descriptions.

    A label is a C variable without a strictly given scope. It can be local, global depending on translation of the
    environment model to C code. Process state consists of labels and from current action.
    """

    def __init__(self, name: str):
        self.value = None
        self.declaration = None
        self._name = name

    @property
    def name(self):
        return self._name

    def __str__(self):
        return self._name

    def __repr__(self):
        return '%{}%'.format(self._name)

    def __eq__(self, other):
        if self.declaration and other.declaration:
            return self.declaration == other.declaration

        return False

    def __hash__(self):
        return hash(self._name)

    def __lt__(self, other):
        return str(self) < str(other)
