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

from core.vtg.emg.common.process import Process, Label, Access, Condition, Dispatch, Receive, Action
from core.vtg.emg.common.c.types import Array, Structure, Pointer


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


class Call(Action):

    def __init__(self, name):
        super().__init__(name)
        self.callback = None
        self.parameters = []
        self.retlabel = None
        self.pre_call = []
        self.post_call = []


class CallRetval(Action):

    def __init__(self, name):
        super().__init__(name)
        self.parameters = []
        self.callback = None
        self.retlabel = None


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
    def unused_labels(self):
        used_labels = set()

        def extract_labels(expr):
            for m in self.label_re.finditer(expr):
                used_labels.add(m.group(1))

        for action in self.actions.values():
            if isinstance(action, Call) or isinstance(action, CallRetval) and action.callback:
                extract_labels(action.callback)
            if isinstance(action, Call):
                for param in action.parameters:
                    extract_labels(param)
            if isinstance(action, Receive) or isinstance(action, Dispatch):
                for param in action.parameters:
                    extract_labels(param)
            if isinstance(action, CallRetval) and action.retlabel:
                extract_labels(action.retlabel)
            if isinstance(action, Condition):
                for statement in action.statements:
                    extract_labels(statement)
            if action.condition:
                for statement in action.condition:
                    extract_labels(statement)
        unused_labels = set(self.labels.keys()).difference(used_labels)
        return unused_labels

    @property
    def calls(self):
        return [self.actions[name] for name in sorted(self.actions.keys()) if isinstance(self.actions[name], Call)]

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

    def accesses(self, accesses=None, exclude=list(), no_labels=False):
        if not accesses:
            accss = dict()

            if not self._accesses or len(exclude) > 0 or no_labels:
                # Collect all accesses across process subprocesses
                for action in [self.actions[name] for name in sorted(self.actions.keys())]:
                    tp = type(action)
                    if tp not in exclude:
                        if isinstance(action, Call) or isinstance(action, CallRetval) and action.callback:
                            accss[action.callback] = []
                        if isinstance(action, Call):
                            for index in range(len(action.parameters)):
                                accss[action.parameters[index]] = []
                        if isinstance(action, Receive) or isinstance(action, Dispatch):
                            for index in range(len(action.parameters)):
                                accss[action.parameters[index]] = []
                        if isinstance(action, CallRetval) and action.retlabel:
                            accss[action.retlabel] = []
                        if isinstance(action, Condition):
                            for statement in action.statements:
                                for match in self.label_re.finditer(statement):
                                    accss[match.group()] = []
                        if action.condition:
                            for statement in action.condition:
                                for match in self.label_re.finditer(statement):
                                    accss[match.group()] = []

                # Add labels with interfaces
                if not no_labels:
                    for label in [self.labels[name] for name in sorted(self.labels.keys())]:
                        access = '%{}%'.format(label.name)
                        if access not in accss:
                            accss[access] = []

                if not self._accesses and len(exclude) == 0 and not no_labels:
                    self._accesses = accss
            else:
                accss = self._accesses

            return accss
        else:
            self._accesses = accesses

    def resolve_access(self, access, interface=None):
        if isinstance(access, Label):
            string = '%{}%'.format(access.name)
        elif isinstance(access, str):
            string = access
        else:
            raise TypeError('Unsupported access token')

        if not interface:
            return self._accesses[string]
        else:
            return [acc for acc in sorted(self._accesses[string], key=lambda acc: acc.interface.identifier)
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

    def add_label(self, name, declaration, value=None):
        lb = AbstractLabel(name)
        lb.prior_signature = declaration
        if value:
            lb.value = value

        self.labels[name] = lb
        acc = AbstractAccess('%{}%'.format(name))
        acc.label = lb
        acc.list_access = [lb.name]
        self._accesses[acc.expression] = [acc]
        return lb

    def add_condition(self, name, condition, statements, comment):
        new = Condition(name)
        self.actions[name] = new

        new.condition = condition
        new.statements = statements
        new.comment = comment
        return new
