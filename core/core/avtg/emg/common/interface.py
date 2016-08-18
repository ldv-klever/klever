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

class Interface:
    def _common_declaration(self, category, identifier, manually_specified=False):
        self.category = category
        self.short_identifier = identifier
        self.identifier = "{}.{}".format(category, identifier)
        self.manually_specified = manually_specified
        self.declaration = None
        self.header = None
        self.implemented_in_kernel = False


class Container(Interface):
    def __init__(self, category, identifier, manually_specified=False):
        self._common_declaration(category, identifier, manually_specified)
        self.element_interface = None
        self.field_interfaces = {}

    def contains(self, target):
        if issubclass(type(target), Interface):
            target = target.declaration

        return self.declaration.contains(target)

    def weak_contains(self, target):
        if issubclass(type(target), Interface):
            target = target.declaration

        return self.declaration.weak_contains(target)


class Callback(Interface):
    def __init__(self, category, identifier, manually_specified=False):
        self._common_declaration(category, identifier, manually_specified)
        self.param_interfaces = []
        self.rv_interface = False
        self.called = False
        self.interrupt_context = False


class Resource(Interface):
    def __init__(self, category, identifier, manually_specified=False):
        self._common_declaration(category, identifier, manually_specified)


class KernelFunction(Interface):
    def __init__(self, identifier, header):
        self.identifier = identifier
        if type(header) is list:
            self.header = header
        else:
            self.header = [header]

        self.declaration = None
        self.param_interfaces = []
        self.rv_interface = False
        self.functions_called_at = {}
        self.files_called_at = set()

    def add_call(self, caller):
        if caller not in self.functions_called_at:
            self.functions_called_at[caller] = 1
        else:
            self.functions_called_at[caller] += 1

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
