import copy
import re


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
    processes.extend([pr.actions[name] for name in pr.actions if pr.actions[name].process])
    regexes = generate_regex_set(old_name)
    for process in processes:
        for regex in regexes:
            if regex['regex'].search(process.process):
                # Replace signal entries
                old_match = regex['regex'].search(process.process).group()
                new_match = old_match.replace(old_name, new_name)
                process.process = process.process.replace(old_match, new_match)

########################################### todo: Remove
def get_common_interface(subprocess, process, position):
    pl = process.extract_label(subprocess.parameters[position])
    if not pl.interfaces:
        return []
    else:
        interfaces = pl.interfaces
        for peer in subprocess.peers:
            arg = peer['subprocess'].parameters[position]
            label = peer['process'].extract_label(arg)
            interfaces = set(interfaces) & set(label.interfaces)

        if len(interfaces) == 0:
            raise RuntimeError('Need at least one common interface to send signal')
        elif len(interfaces) > 1:
            raise NotImplementedError
        else:
            return list(interfaces)[0]
#############################################

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
        access = copy.deepcopy(self.list_access)
        access[0] = variable.name

        # Increase use counter
        variable.use += 1

        # todo: this is ugly and incorrect
        if variable.signature.pointer:
            expr = '->'.join(access)
        else:
            expr = '.'.join(access)
        return expr


class Label:

    def __init__(self, name):
        self.container = False
        self.resource = False
        self.callback = False
        self.parameter = False
        self.pointer = False
        self.parameters = []

        self.value = None
        self.name = name
        self.prior_signature = None
        self.__signature_map = {}

    @property
    def interfaces(self):
        return list(self.__signature_map.keys())

    def get_decalration(self, identifier):
        if identifier in self.__signature_map:
            return self.__signature_map[identifier]
        else:
            return None

    def set_declaration(self, identifier, declaration):
        self.__signature_map[identifier] = declaration

    def compare_with(self, label):
        if self.interfaces and label.interfaces:
            if len(list(set(self.interfaces) & set(label.interfaces))) > 0:
                return 'equal'
            else:
                return 'different'
        elif label.interfaces or self.interfaces:
            if (self.container and label.container) or (self.resource and label.resource) or \
               (self.callback and label.callback):
                return 'сompatible'
            else:
                return 'different'
        elif self.signature() and label.signature():
            my_signature = self.signature()
            ret = my_signature.compare_signature(label.signature())
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
        self.process_ast = None
        self.__accesses = None

    @property
    def unmatched_receives(self):
        return [self.actions[act] for act in self.actions if type(self.actions[act]) is Receive and
                len(self.actions[act].peers) == 0]

    @property
    def unmatched_dispatches(self):
        return [self.actions[act] for act in self.actions if type(self.actions[act]) is Dispatch and
                len(self.actions[act].peers) == 0]

    @property
    def unmatched_labels(self):
        unmatched = [self.labels[label] for label in self.labels
                     if not self.labels[label].interface and not self.labels[label].signature]
        return unmatched

    @property
    def containers(self):
        return [container for container in self.labels.values() if container.container]

    @property
    def callbacks(self):
        return [callback for callback in self.labels.values() if callback.callback]

    @property
    def resources(self):
        return [resource for resource in self.labels.values() if resource.resource]

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

                if (not label2.interfaces or len(label2.interfaces) == 0) and \
                        (label1.interfaces and len(label1.interfaces) > 0):
                    label2.interfaces = label1.interfaces
                elif (label2.interfaces and len(label2.interfaces) > 0) and \
                        (not label1.interfaces or len(label1.interfaces) == 0):
                    label1.interfaces = label2.interfaces

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
                for subprocess in [self.actions[name] for name in self.actions]:
                    if subprocess.callback:
                        self.__accesses[subprocess.callback] = []
                    if subprocess.parameters:
                        for index in range(len(subprocess.parameters)):
                            self.__accesses[subprocess.parameters[index]] = []
                    if subprocess.callback_retval:
                        self.__accesses[subprocess.callback_retval] = []
                    if subprocess.condition:
                        for statement in subprocess.condition:
                            for match in self.label_re.finditer(statement):
                                self.__accesses[match.group()] = []
                    if subprocess.statements:
                        for statement in subprocess.statements:
                            for match in self.label_re.finditer(statement):
                                self.__accesses[match.group()] = []

                # Add labels with interfaces
                for label in self.labels.values():
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
            return [acc for acc in self.__accesses[string]
                    if acc.interface and acc.interface.full_identifier == interface][0]


class Subprocess:

    def __init__(self, name):
        self.name = name
        self.process = None
        self.process_ast = None
        self.condition = None


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
        self.condition = None
        self.statements = None


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'