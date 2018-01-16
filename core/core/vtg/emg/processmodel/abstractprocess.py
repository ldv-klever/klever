#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
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

import re

from core.vtg.emg.common.process import Process, Label, Access
from core.vtg.emg.common.signature import Array, Structure, Pointer


def get_common_parameter(action, process, position):
    interfaces = [access.interface for access in process.resolve_access(action.parameters[position])
                  if access.interface]

    for peer in action.peers:
        candidates = [access.interface for access
                      in peer['process'].resolve_access(peer['subprocess'].parameters[position])
                      if access.interface]
        interfaces = set(interfaces) & set(candidates)

    if len(interfaces) == 0:
        raise RuntimeError('Need at least one common interface to send a signal')
    else:
        # Todo how to choose between several ones?
        return list(interfaces)[0]


class AbstractAccess(Access):
    def __init__(self, expression):
        super(AbstractAccess, self).__init__(expression)
        self.interface = None
        self.list_interface = None
        self.complete_list_interface = None

    def replace_with_label(self, statement, label):
        reg = re.compile(self.expression)
        if reg.search(statement):
            expr = self.access_with_label(label)
            return statement.replace(self.expression, expr)
        else:
            return statement

    def access_with_label(self, label):
        # Increase use counter

        if self.label and self.label.prior_signature and not self.interface:
            target = self.label.prior_signature
        elif self.label and self.list_interface[-1].identifier in self.label.interfaces:
            target = self.label.get_declaration(self.list_interface[-1].identifier)
        else:
            target = self.list_interface[-1].declaration

        expression = "%{}%".format(label.name)
        accesses = self.list_access[1:]

        if len(accesses) > 0:
            candidate = label.prior_signature
            previous = None
            while candidate:
                tmp = candidate

                if candidate.compare(target):
                    candidate = None
                    if isinstance(previous, Pointer):
                        expression = "*({})".format(expression)
                elif isinstance(candidate, Pointer):
                    candidate = candidate.points
                elif isinstance(candidate, Array):
                    candidate = candidate.element
                    expression += '[{}]'.format(accesses.pop(0))
                elif isinstance(candidate, Structure):
                    field = accesses.pop(0)
                    if field in candidate.fields:
                        candidate = candidate.fields[field]
                        if isinstance(previous, Pointer):
                            expression += '->{}'.format(field)
                        else:
                            expression += '.{}'.format(field)
                    else:
                        raise ValueError("Cannot build access from given variable '{}', something wrong with types".
                                         format(self.expression))
                else:
                    raise ValueError("Cannot build access from given variable '{}', something wrong with types".
                                     format(self.expression))

                previous = tmp

        return expression


class AbstractLabel(Label):

    def __init__(self, name):
        super(AbstractLabel, self).__init__(name)
        self.container = False
        self.resource = False
        self.callback = False
        self.parameter = False
        self.retval = False
        self.pointer = False
        self.parameters = []
        self.__signature_map = {}

    @property
    def interfaces(self):
        return sorted(self.__signature_map.keys())

    @property
    def declarations(self):
        if self.prior_signature:
            return [self.prior_signature]
        else:
            return sorted(self.__signature_map.values(), key=lambda d: d.identifier)

    def get_declaration(self, identifier):
        if identifier in self.__signature_map:
            return self.__signature_map[identifier]
        else:
            return None

    def set_declaration(self, identifier, declaration):
        self.__signature_map[identifier] = declaration

    def compare_with(self, label):
        if len(self.interfaces) > 0 and len(label.interfaces) > 0:
            if len(list(set(self.interfaces) & set(label.interfaces))) > 0:
                return 'equal'
            else:
                return 'different'
        elif len(label.interfaces) > 0 or len(self.interfaces) > 0:
            if (self.container and label.container) or (self.resource and label.resource) or \
                    (self.callback and label.callback):
                return 'сompatible'
            else:
                return 'different'
        else:
            return super(AbstractLabel, self).compare_with(label)


class AbstractProcess(Process):
    label_re = re.compile('%(\w+)((?:\.\w*)*)%')

    def __init__(self, name):
        super(AbstractProcess, self).__init__(name)
        self.self_parallelism = True
        self.allowed_implementations = dict()

    @property
    def unmatched_labels(self):
        unmatched = [self.labels[label] for label in sorted(self.labels.keys())
                     if not self.labels[label].interface and not self.labels[label].signature]
        return unmatched

    @property
    def containers(self):
        return [self.labels[name] for name in sorted(self.labels.keys()) if self.labels[name].container]

    @property
    def callbacks(self):
        return [self.labels[name] for name in sorted(self.labels.keys()) if self.labels[name].callback]

    @property
    def resources(self):
        return [self.labels[name] for name in sorted(self.labels.keys()) if self.labels[name].resource]

    def extract_label(self, string):
        name, tail = self.extract_label_with_tail(string)
        return name

    def extract_label_with_tail(self, string):
        if self.label_re.fullmatch(string):
            name = self.label_re.fullmatch(string).group(1)
            tail = self.label_re.fullmatch(string).group(2)
            if name not in self.labels:
                raise ValueError("Cannot extract label name from string '{}': no such label".format(string))
            else:
                return self.labels[name], tail
        else:
            raise ValueError('Cannot extract label from access {} in process {}'.format(string, format(string)))

    def establish_peers(self, process):
        peers = self.get_available_peers(process)
        for signals in peers:
            for index in range(len(self.actions[signals[0]].parameters)):
                label1 = self.extract_label(self.actions[signals[0]].parameters[index])
                label2 = process.extract_label(process.actions[signals[1]].parameters[index])

                if len(label1.interfaces) > 0 and not label2.prior_signature and \
                        not (label2.parameter or label2.retval):
                    for intf in label1.interfaces:
                        if label1.get_declaration(intf) and (intf not in label2.interfaces or
                                                             not label2.get_declaration(intf)):
                            label2.set_declaration(intf, label1.get_declaration(intf))
                if len(label2.interfaces) > 0 and not label1.prior_signature and \
                        not (label1.parameter or label1.retval):
                    for intf in label2.interfaces:
                        if label2.get_declaration(intf) and (intf not in label1.interfaces or
                                                             not label1.get_declaration(intf)):
                            label1.set_declaration(intf, label2.get_declaration(intf))
                if label1.prior_signature and not label2.prior_signature and len(label2.interfaces) == 0:
                    label2.prior_signature = label1.prior_signature
                if label2.prior_signature and not label1.prior_signature and len(label1.interfaces) == 0:
                    label1.prior_signature = label2.prior_signature

            self.actions[signals[0]].peers.append(
            {
                'process': process,
                'subprocess': process.actions[signals[1]]
            })
            process.actions[signals[1]].peers.append(
            {
                'process': self,
                'subprocess': self.actions[signals[0]]
            })

    def get_available_peers(self, process):
        ret = []

        # Match dispatches
        for dispatch in self.unmatched_dispatches:
            for receive in process.unmatched_receives:
                match = self.__compare_signals(process, dispatch, receive)
                if match:
                    ret.append([dispatch.name, receive.name])

        # Match receives
        for receive in self.unmatched_receives:
            for dispatch in process.unmatched_dispatches:
                match = self.__compare_signals(process, receive, dispatch)
                if match:
                    ret.append([receive.name, dispatch.name])

        return ret

    def resolve_access(self, access, interface=None):
        if isinstance(access, Label):
            string = '%{}%'.format(access.name)
        elif isinstance(access, str):
            string = access
        else:
            raise TypeError('Unsupported access token')

        if not interface:
            return self.__accesses[string]
        else:
            return [acc for acc in sorted(self.__accesses[string], key=lambda acc: acc.interface.identifier)
                    if acc.interface and acc.interface.identifier == interface][0]

    def get_implementation(self, access):
        if access.interface:
            if self.allowed_implementations[access.expression][access.interface.identifier] != '':
                return self.allowed_implementations[access.expression][access.interface.identifier]
            else:
                return False
        else:
            return None

    def __compare_signals(self, process, first, second):
        if first.name == second.name and len(first.parameters) == len(second.parameters):
            match = True
            for index in range(len(first.parameters)):
                label = self.extract_label(first.parameters[index])
                if not label:
                    raise ValueError("Provide label in subprocess '{}' at position '{}' in process '{}'".
                                     format(first.name, index, self.name))
                pair = process.extract_label(second.parameters[index])
                if not pair:
                    raise ValueError("Provide label in subprocess '{}' at position '{}'".
                                     format(second.name, index, process.name))

                ret = label.compare_with(pair)
                if ret != "сompatible" and ret != "equal":
                    match = False
                    break
            return match
        else:
            return False

