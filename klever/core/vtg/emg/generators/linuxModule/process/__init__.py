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

import re
import collections
import sortedcontainers

from klever.core.vtg.emg.common.process.labels import Label
from klever.core.vtg.emg.common.c.types import Array, Structure, Pointer
from klever.core.vtg.emg.common.process import Process, Access, ProcessCollection
from klever.core.vtg.emg.generators.linuxModule.interface import Interface, Container
from klever.core.vtg.emg.common.process.actions import Block, Dispatch, Receive, Signal


Peer = collections.namedtuple('Peer', 'process action interfaces')


class Call(Dispatch):

    def __init__(self, name):
        super().__init__(name)
        self.callback = None
        self.parameters = []
        self.retlabel = None
        self.pre_call = []
        self.post_call = []


class CallRetval(Receive):

    def __init__(self, name):
        super().__init__(name)
        self.parameters = []
        self.callback = None
        self.retlabel = None


class ExtendedAccess(Access):
    def __init__(self, expression):
        super().__init__(expression)
        self._interface = None
        self._base_interface = None

    @property
    def interface(self):
        return self._interface

    @interface.setter
    def interface(self, value):
        if not isinstance(value, Interface):
            raise ValueError(f"Cannot set non-interface value as an interface to the access '{str(self)}'")
        self._interface = value

    @property
    def base_interface(self):
        if self._base_interface:
            return self._base_interface
        if self._interface:
            return self._interface

        return None

    @base_interface.setter
    def base_interface(self, value):
        if not isinstance(value, Interface):
            raise ValueError(f"Cannot set non-interface as a base interface to the access '{str(self)}'")
        if not self._interface:
            raise ValueError(f"Set the interface attribute before setting the base interface of '{str(self)}'")
        self._base_interface = value

    def replace_with_label(self, statement, label):
        reg = re.compile(self.expression)
        if reg.search(statement):
            expr = self.access_with_label(label)
            return statement.replace(self.expression, expr)

        return statement

    def access_with_label(self, label):
        # Increase use counter
        if self.label and self.label.declaration and not self.interface:
            target = self.label.declaration
        elif self.label and str(self.interface) in self.label.interfaces:
            target = self.label.get_declaration(str(self.interface))
        else:
            target = self.interface.declaration

        expression = "%{}%".format(label.name)
        accesses = self.list_access[1:]

        if len(accesses) > 0:
            candidate = label.declaration
            previous = None
            while candidate:
                tmp = candidate

                if candidate == target:
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
                        raise ValueError("Cannot build access from given variable {!r}, something wrong with types".
                                         format(self.expression))
                else:
                    raise ValueError("Cannot build access from given variable {!r}, something wrong with types".
                                     format(self.expression))

                previous = tmp

        return expression


class ExtendedLabel(Label):

    def __init__(self, name):
        super().__init__(name)
        self.match_implemented = False
        self.container = False
        self.resource = False
        self.callback = False
        self.parameter = False
        self.retval = False
        self.pointer = False
        self.parameters = []
        self._signature_map = sortedcontainers.SortedDict()

    @property
    def interfaces(self):
        return list(self._signature_map.keys())

    @property
    def declarations(self):
        if self.declaration:
            return [self.declaration]

        return list(self._signature_map.values())

    def get_declaration(self, identifier):
        if identifier in self._signature_map:
            return self._signature_map[identifier]

        return None

    def set_declaration(self, identifier, declaration):
        self._signature_map[identifier] = declaration

    def set_interface(self, interface):
        if isinstance(interface, Container):
            self.set_declaration(str(interface), interface.declaration.take_pointer)
        else:
            self.set_declaration(str(interface), interface.declaration)

    def __eq__(self, label):
        if len(self.interfaces) > 0 and len(label.interfaces) > 0:
            return len(list(set(self.interfaces) & set(label.interfaces))) > 0
        if len(label.interfaces) > 0 or len(self.interfaces) > 0:
            return (self.container and label.container) or (self.resource and label.resource) or \
                    (self.callback and label.callback)

        return super().__eq__(label)


class ExtendedProcess(Process):
    label_re = re.compile(r'%(\w+)((?:\.\w*)*)%')

    def __init__(self, name: str, category: str):
        super().__init__(name, category)
        self.self_parallelism = True
        self.allowed_implementations = sortedcontainers.SortedDict()
        self.instance_number = 0

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, new_name):
        # Extended process allows setting new names if necessary
        self._name = new_name

    @property
    def category(self):
        return self._category

    @category.setter
    def category(self, category):
        # Extended process allows setting categories if necessary
        self._category = category

    @property
    def unmatched_labels(self):
        unmatched = [self.labels[label] for label in self.labels.keys()
                     if not self.labels[label].interface and not self.labels[label].signature]
        return unmatched

    @property
    def unused_labels(self):
        used_labels = set()

        def extract_labels(expr):
            for m in self.label_re.finditer(expr):
                used_labels.add(m.group(1))

        for action in self.actions.values():
            if isinstance(action, (Call, CallRetval)) and action.callback:
                assert action.callback, 'Expect required callback action'
                extract_labels(action.callback)
            if isinstance(action, (Call, Receive, Dispatch)):
                for param in action.parameters:
                    extract_labels(param)
            if isinstance(action, CallRetval) and action.retlabel:
                extract_labels(action.retlabel)
            if isinstance(action, Block):
                for statement in action.statements:
                    extract_labels(statement)
            if action.condition:
                for statement in action.condition:
                    extract_labels(statement)
        return sortedcontainers.SortedSet(self.labels.keys()).difference(used_labels)

    @property
    def calls(self):
        return self.actions.filter(include={Call})

    @property
    def containers(self):
        return [self.labels[name] for name in self.labels if self.labels[name].container]

    @property
    def callbacks(self):
        return [self.labels[name] for name in self.labels if self.labels[name].callback]

    @property
    def resources(self):
        return [self.labels[name] for name in self.labels if self.labels[name].resource]

    def unmatched_signals(self, kind=Signal):
        signals = set(map(str, self.actions.filter(include={kind}, exclude={CallRetval, Call})))
        matched = set()
        for peered in self.peers.values():
            matched.update(peered)
        signals.difference_update(matched)
        return signals

    def extract_label(self, string):
        name, _ = self.extract_label_with_tail(string)
        return name

    def add_access(self, expression, obj):
        self._accesses.setdefault(expression, [])
        if obj not in self._accesses[expression]:
            self._accesses[expression].append(obj)

    def extract_label_with_tail(self, string):
        if self.label_re.fullmatch(string):
            name = self.label_re.fullmatch(string).group(1)
            tail = self.label_re.fullmatch(string).group(2)
            if name not in self.labels:
                raise ValueError("Cannot extract label name from string {!r}: no such label".format(string))

            return self.labels[name], tail

        raise ValueError("Cannot extract label from access {!r} in process {!r}".format(string, format(string)))

    def establish_peers(self, process):
        assert isinstance(process, ExtendedProcess), \
            f'Got a {type(process).__name__} instead of a {type(self).__name__}'

        if str(self) in process.peers:
            del process.peers[str(self)]
        if str(process) in self.peers:
            del self.peers[str(process)]

        for signals in self.get_available_peers(process):
            for index, param in enumerate(self.actions[signals[0]].parameters):
                label1 = self.extract_label(param)
                label2 = process.extract_label(process.actions[signals[1]].parameters[index])

                if len(label1.interfaces) > 0 and not label2.declaration and \
                        not (label2.parameter or label2.retval):
                    for intf in label1.interfaces:
                        if label1.get_declaration(intf) and (intf not in label2.interfaces or
                                                             not label2.get_declaration(intf)):
                            label2.set_declaration(intf, label1.get_declaration(intf))
                if len(label2.interfaces) > 0 and not label1.declaration and \
                        not (label1.parameter or label1.retval):
                    for intf in label2.interfaces:
                        if label2.get_declaration(intf) and (intf not in label1.interfaces or
                                                             not label1.get_declaration(intf)):
                            label1.set_declaration(intf, label2.get_declaration(intf))
                if label1.declaration and not label2.declaration and len(label2.interfaces) == 0:
                    label2.declaration = label1.declaration
                if label2.declaration and not label1.declaration and len(label1.interfaces) == 0:
                    label1.declaration = label2.declaration

            self.peers.setdefault(str(process), set())
            process.peers.setdefault(str(self), set())
            self.peers[str(process)].add(str(signals[1]))
            process.peers[str(self)].add(str(signals[0]))

    def get_available_peers(self, process):
        assert isinstance(process, ExtendedProcess), f'Got a {type(process).__name__} instead of {type(self).__name__}'
        ret = []

        # Match dispatches
        for dispatch, receive in ((d, r) for d in self.actions.filter(include={Dispatch}, exclude={Call})
                                  for r in process.actions.filter(include={Receive}, exclude={CallRetval})):
            match = self.__compare_signals(process, dispatch, receive)
            if match:
                ret.append((dispatch.name, receive.name))

        # Match receives
        for receive, dispatch in ((r, d) for r in self.actions.filter(include={Receive}, exclude={CallRetval})
                                  for d in process.actions.filter(include={Dispatch}, exclude={Call})):
            match = self.__compare_signals(process, receive, dispatch)
            if match:
                ret.append((receive.name, dispatch.name))
        return ret

    def accesses(self, accesses=None, exclude=None, no_labels=False, refresh=False):
        if not exclude:
            exclude = []

        if not accesses:
            accss = sortedcontainers.SortedDict()

            if refresh or (not self._accesses or len(exclude) > 0 or no_labels):
                # Collect all accesses across process subprocesses
                for action in self.actions.filter(exclude=exclude):
                    if isinstance(action, (Call, CallRetval)) and action.callback:
                        accss[action.callback] = []
                    if isinstance(action, (Call, Receive, Dispatch)):
                        for param in action.parameters:
                            accss[param] = []
                    if isinstance(action, CallRetval) and action.retlabel:
                        accss[action.retlabel] = []
                    if isinstance(action, Block):
                        for statement in action.statements:
                            for match in self.label_re.finditer(statement):
                                accss[match.group()] = []
                    if action.condition:
                        for statement in action.condition:
                            for match in self.label_re.finditer(statement):
                                accss[match.group()] = []

                # Add labels with interfaces
                if not no_labels:
                    for label in self.labels.values():
                        access = '%{}%'.format(label.name)
                        if access not in accss:
                            accss[access] = []

                if not self._accesses and len(exclude) == 0 and not no_labels:
                    self._accesses = accss
            else:
                accss = self._accesses

            return accss

        self._accesses = accesses
        return None

    def resolve_access(self, access, interface=None):
        if isinstance(access, Label):
            string = '%{}%'.format(access.name)
        elif isinstance(access, str):
            string = access
        else:
            return None

        if not interface:
            return self._accesses[string]

        cnds = [acc for acc in self._accesses[string] if acc.interface and str(acc.interface) == interface]
        if cnds:
            return cnds[0]

        return None

    def get_implementation(self, access):
        if access.interface:
            if str(access.interface) in self.allowed_implementations[access.expression] and \
                    self.allowed_implementations[access.expression][str(access.interface)] != '':
                return self.allowed_implementations[access.expression][str(access.interface)]

            return False

        return None

    def add_label(self, name, declaration, value=None):
        lb = ExtendedLabel(name)
        lb.declaration = declaration
        if value:
            lb.value = value

        self.labels[str(lb)] = lb
        acc = ExtendedAccess('%{}%'.format(name))
        acc.label = lb
        acc.list_access = [lb.name]
        self._accesses[acc.expression] = [acc]
        return lb

    def __compare_signals(self, process, first, second):
        if first.name == second.name and len(first.parameters) == len(second.parameters):
            match = True
            for index, param in enumerate(first.parameters):
                label = self.extract_label(param)
                if not label:
                    raise ValueError("Provide label in action {!r} at position {!r} in process {!r}".
                                     format(first.name, index, self._name))
                pair = process.extract_label(second.parameters[index])
                if not pair:
                    raise ValueError("Provide label in action {!r} at position {!r} in process {!r}".
                                     format(second.name, index, process.name))

                if label != pair:
                    match = False
                    break
            return match

        return False


class ExtendedProcessCollection(ProcessCollection):

    def peers(self, process, signals=None, processes=None):
        """Add an extra field interfaces in addition to the process and action."""
        peers = super().peers(process, signals, processes)
        return [Peer(*p, []) for p in peers]

    def get_common_parameter(self, action, process, position):
        assert isinstance(action, Signal)
        assert isinstance(process, ExtendedProcess)
        assert isinstance(position, int)

        interfaces = [access.interface for access in process.resolve_access(action.parameters[position])
                      if access.interface]

        for peer in self.peers(process, {action.name}):
            candidates = [access.interface for access
                          in peer.process.resolve_access(peer.action.parameters[position])
                          if access.interface]
            interfaces = set(interfaces) & set(candidates)

        if len(interfaces) == 0:
            raise RuntimeError('Need at least one common interface to send a signal')

        # Todo how to choose between several ones?
        return list(interfaces)[0]
