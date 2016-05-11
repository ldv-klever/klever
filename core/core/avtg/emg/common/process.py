import re

from core.avtg.emg.common.signature import Array, Function, Structure, Pointer
from core.avtg.emg.grammars.process import parse_process


def generate_regex_set(subprocess_name):
    dispatch_template = '\[@?{}(?:\[[^)]+\])?\]'
    receive_template = '\(!?{}(?:\[[^)]+\])?\)'
    condition_template = '<{}(?:\[[^)]+\])?>'
    subprocess_template = '{}'

    subprocess_re = re.compile('\{' + subprocess_template.format(subprocess_name) + '\}')
    receive_re = re.compile(receive_template.format(subprocess_name))
    dispatch_re = re.compile(dispatch_template.format(subprocess_name))
    condition_template_re = re.compile(condition_template.format(subprocess_name))
    regexes = [
        {'regex': subprocess_re, 'type': Subprocess},
        {'regex': dispatch_re, 'type': Dispatch},
        {'regex': receive_re, 'type': Receive},
        {'regex': condition_template_re, 'type': Condition}
    ]

    return regexes


def rename_subprocess(pr, old_name, new_name):
    if old_name not in pr.actions:
        raise KeyError('Cannot rename subprocess {} in process {} because it does not exist'.
                       format(old_name, pr.name))

    subprocess = pr.actions[old_name]
    subprocess.name = new_name

    # Delete old subprocess
    del pr.actions[old_name]

    # Set new subprocess
    pr.actions[subprocess.name] = subprocess

    # Replace subprocess entries
    processes = [pr]
    processes.extend([pr.actions[name] for name in sorted(pr.actions.keys()) if type(pr.actions[name]) is Subprocess])
    regexes = generate_regex_set(old_name)
    for process in processes:
        for regex in regexes:
            if regex['regex'].search(process.process):
                # Replace signal entries
                old_match = regex['regex'].search(process.process).group()
                new_match = old_match.replace(old_name, new_name)
                process.process = process.process.replace(old_match, new_match)


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
    elif len(interfaces) > 1:
        raise NotImplementedError('Cannot have several common interfaces for signal transmission')
    else:
        return list(interfaces)[0]

    return interfaces


class Access:
    def __init__(self, expression):
        self.expression = expression
        self.label = None
        self.interface = None
        self.list_access = None
        self.list_interface = None
        self.complete_list_interface = None

    def replace_with_variable(self, statement, variable):
        reg = re.compile(self.expression)
        if reg.search(statement):
            expr = self.access_with_variable(variable)
            return statement.replace(self.expression, expr)
        else:
            return statement

    def access_with_variable(self, variable):
        # Increase use counter
        variable.use += 1

        if self.label and self.label.prior_signature:
            target = self.label.prior_signature
        elif self.label and self.list_interface[-1].identifier in self.label.interfaces:
            target = self.label.get_declaration(self.list_interface[-1].identifier)
        else:
            target = self.list_interface[-1].declaration

        expression = variable.name
        accesses = self.list_access[1:]

        if len(accesses) > 0:
            candidate = variable.declaration
            previous = None
            while candidate:
                tmp = candidate

                if candidate.compare(target):
                    candidate = None
                    if type(previous) is Pointer:
                        expression = "*({})".format(expression)
                elif type(candidate) is Pointer:
                    candidate = candidate.points
                elif type(candidate) is Array:
                    candidate = candidate.element
                    expression += '[{}]'.format(accesses.pop(0))
                elif type(candidate) is Structure:
                    field = accesses.pop(0)
                    if field in candidate.fields:
                        candidate = candidate.fields[field]
                        if type(previous) is Pointer:
                            expression += '->{}'.format(field)
                        else:
                            expression += '.{}'.format(field)
                    else:
                        raise ValueError('Cannot build access from given variable')
                else:
                    raise ValueError('CAnnot build access from given variable')

                previous = tmp

        return expression


class Label:

    def __init__(self, name):
        self.container = False
        self.resource = False
        self.callback = False
        self.parameter = False
        self.pointer = False
        self.parameters = []
        self.file = None
        self.value = None
        self.name = name
        self.prior_signature = None
        self.__signature_map = {}

    @property
    def interfaces(self):
        return sorted(self.__signature_map.keys())

    @property
    def declarations(self):
        if self.prior_signature:
            return [self.prior_signature]
        else:
            return sorted(self.__signature_map.values())

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
        elif self.prior_signature and label.prior_signature:
            my_signature = self.prior_signature
            ret = my_signature.compare_signature(label.prior_signature)
            if not ret:
                return 'different'
            else:
                return 'equal'
        else:
            raise NotImplementedError("Cannot compare label '{}' with label '{}'".format(label.name, label.name))


class Process:
    label_re = re.compile('%(\w+)((?:\.\w*)*)%')

    def __init__(self, name):
        self.name = name
        self.identifier = None
        self.labels = {}
        self.actions = {}
        self.category = None
        self.process = None
        self.__process_ast = None
        self.__accesses = None
        self.__forbidded_implementations = set()

    @property
    def unmatched_receives(self):
        return [self.actions[act] for act in sorted(self.actions.keys()) if type(self.actions[act]) is Receive and
                len(self.actions[act].peers) == 0]

    @property
    def unmatched_dispatches(self):
        return [self.actions[act] for act in sorted(self.actions.keys()) if type(self.actions[act]) is Dispatch and
                len(self.actions[act].peers) == 0]

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

    @property
    def process_ast(self):
        if not self.__process_ast:
            self.__process_ast = parse_process(self.process)
        return self.__process_ast

    @property
    def calls(self):
        return [self.actions[name] for name in sorted(self.actions.keys()) if type(self.actions[name]) is Call]

    def add_label(self, name, declaration, value):
        lb = Label(name)
        lb.prior_signature = declaration
        lb.value = value

        self.labels[name] = lb
        acc = Access('%{}%'.format(name))
        acc.label = lb
        acc.list_access = [lb.name]
        self.__accesses[acc.expression] = [acc]
        return lb

    def add_condition(self, name, condition, statements):
        new = Condition(name)
        self.actions[name] = new

        new.condition = condition
        new.statements = statements
        return new

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

                if len(label1.interfaces) > 0 and not label2.prior_signature and not label2.parameter:
                    for intf in label1.interfaces:
                        if label1.get_declaration(intf) and (intf not in label2.interfaces or
                                                             not label2.get_declaration(intf)):
                            label2.set_declaration(intf, label1.get_declaration(intf))
                if len(label2.interfaces) > 0 and not label1.prior_signature and not label1.parameter:
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

    def accesses(self, accesses=None):
        if not accesses:
            if not self.__accesses:
                self.__accesses = {}

                # Collect all accesses across process subprocesses
                for action in [self.actions[name] for name in sorted(self.actions.keys())]:
                    if type(action) is Call or type(action) is CallRetval and action.callback:
                        self.__accesses[action.callback] = []
                    if type(action) is Call:
                        for index in range(len(action.parameters)):
                            self.__accesses[action.parameters[index]] = []
                    if type(action) is Receive or type(action) is Dispatch:
                        for index in range(len(action.parameters)):
                            self.__accesses[action.parameters[index]] = []
                    if type(action) is CallRetval and action.retlabel:
                        self.__accesses[action.retlabel] = []
                    if type(action) is Condition:
                        for statement in action.statements:
                            for match in self.label_re.finditer(statement):
                                self.__accesses[match.group()] = []
                    if action.condition:
                        for statement in action.condition:
                            for match in self.label_re.finditer(statement):
                                self.__accesses[match.group()] = []

                # Add labels with interfaces
                for label in [self.labels[name] for name in sorted(self.labels.keys())]:
                    access = '%{}%'.format(label.name)
                    if access not in self.__accesses:
                        self.__accesses[access] = []

            return self.__accesses
        else:
            self.__accesses = accesses

    def resolve_access(self, access, interface=None):
        if type(access) is Label:
            string = '%{}%'.format(access.name)
        elif type(access) is str:
            string = access
        else:
            raise TypeError('Unsupported access token')

        if not interface:
            return self.__accesses[string]
        else:
            return [acc for acc in sorted(self.__accesses[string], key=lambda acc: acc.expression)
                    if acc.interface and acc.interface.identifier == interface][0]

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

    def forbide_except(self, analysis, implementation):
        accesses = self.accesses()
        for access_list in [accesses[name] for name in sorted(accesses.keys())]:
            for access in access_list:
                implementations = self.get_implementations(analysis, access)
                base_values = set([i.base_value for i in implementations])
                identifiers = set([i.identifier for i in implementations])

                if implementation.value in base_values:
                    for candidate in [i for i in implementations if i.base_value != implementation.value]:
                        self.__forbidded_implementations.add(candidate.identifier)
                elif implementation.identifier in identifiers:
                    for candidate in [i for i in implementations if i.identifier != implementation.identifier]:
                        self.__forbidded_implementations.add(candidate.identifier)

    def get_implementations(self, analysis, access):
        if access.interface:
            implementations = analysis.implementations(access.interface)
            return [impl for impl in implementations if impl.identifier not in self.__forbidded_implementations]
        elif access.label and len(access.list_access) == 1:
            return []
        else:
            raise ValueError("Cannot resolve access '{}'".format(access.expression))


class Subprocess:

    def __init__(self, name):
        self.name = name
        self.process = None
        self.condition = None
        self.__process_ast = None

    @property
    def process_ast(self):
        if not self.__process_ast:
            self.__process_ast = parse_process(self.process)
        return self.__process_ast


class Dispatch:

    def __init__(self, name):
        self.name = name
        self.condition = None
        self.parameters = []
        self.broadcast = False
        self.peers = []


class Receive:

    def __init__(self, name):
        self.name = name
        self.parameters = []
        self.condition = None
        self.replicative = False
        self.peers = []


class Call:

    def __init__(self, name):
        self.name = name
        self.condition = None
        self.callback = None
        self.parameters = []
        self.retlabel = None
        self.pre_call = []
        self.post_call = []


class CallRetval:

    def __init__(self, name):
        self.name = name
        self.parameters = []
        self.callback = None
        self.retlabel = None
        self.condition = None


class Condition:

    def __init__(self, name):
        self.name = name
        self.statements = []
        self.condition = None


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'