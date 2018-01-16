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

from core.vtg.emg.grammars.process import parse_process


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


def _update_process_ast(obj):
    obj.__process_ast = parse_process(obj.process)


class Access:
    def __init__(self, expression):
        self.expression = expression
        self.label = None
        self.list_access = None


class Label:

    def __init__(self, name):
        self.value = None
        self.prior_signature = None
        self.name = name

    def compare_with(self, label):
        if self.prior_signature and label.prior_signature:
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
        self.category = None
        self.identifier = None
        self.comment = None
        self.labels = {}
        self.actions = {}
        self.process = None
        self.headers = list()
        self.declarations = dict()
        self.definitions = dict()
        self.external_id = None
        self.__process_ast = None
        self.__accesses = dict()

    @property
    def unmatched_receives(self):
        return [self.actions[act] for act in sorted(self.actions.keys()) if isinstance(self.actions[act], Receive) and
                len(self.actions[act].peers) == 0]

    @property
    def unmatched_dispatches(self):
        return [self.actions[act] for act in sorted(self.actions.keys()) if isinstance(self.actions[act], Dispatch) and
                len(self.actions[act].peers) == 0]

    @property
    def process_ast(self):
        if not self.__process_ast:
            self.__process_ast = parse_process(self.process)
        return self.__process_ast

    @property
    def calls(self):
        return [self.actions[name] for name in sorted(self.actions.keys()) if isinstance(self.actions[name], Call)]

    def add_label(self, name, declaration, value=None):
        lb = Label(name)
        lb.prior_signature = declaration
        if value:
            lb.value = value

        self.labels[name] = lb
        acc = Access('%{}%'.format(name))
        acc.label = lb
        acc.list_access = [lb.name]
        self.__accesses[acc.expression] = [acc]
        return lb

    def add_condition(self, name, condition, statements, comment):
        new = Condition(name)
        self.actions[name] = new

        new.condition = condition
        new.statements = statements
        new.comment = comment
        return new

    def insert_action(self, old, new, position):
        if not old or old not in self.actions:
            raise KeyError('Cannot rename action {!r} in process {!r} because it does not exist'.
                           format(old, self.name))
        if position == 'instead':
            # Delete old subprocess
            del self.actions[old]

        # Replace action entries
        processes = [self]
        processes.extend(
            [self.actions[name] for name in sorted(self.actions.keys()) if isinstance(self.actions[name], Subprocess)])
        regexes = generate_regex_set(old)
        for process in processes:
            for regex in regexes:
                m = regex['regex'].search(process.process)
                if m:
                    # Replace signal entries
                    curr_expr = m.group(0)
                    if position == 'before':
                        next_expr = "{}.{}".format(new, curr_expr)
                    elif position == 'after':
                        next_expr = "{}.{}".format(curr_expr, new)
                    elif position == 'instead':
                        next_expr = new
                    else:
                        next_expr = '({} | {})'.format(curr_expr, new)

                    process.process = process.process.replace(curr_expr, next_expr)
                    break
            process.update_process_ast()

    def rename_action(self, name, new_name):
        if name not in self.actions:
            raise KeyError('Cannot rename subprocess {} in process {} because it does not exist'.
                           format(name, self.name))

        action = self.actions[name]
        action.name = new_name

        # Delete old subprocess
        del self.actions[name]

        # Set new subprocess
        self.actions[action.name] = action

        # Replace subprocess entries
        processes = [self]
        processes.extend(
            [self.actions[name] for name in sorted(self.actions.keys()) if isinstance(self.actions[name], Subprocess)])
        regexes = generate_regex_set(name)
        for process in processes:
            for regex in regexes:
                if regex['regex'].search(process.process):
                    # Replace signal entries
                    old_match = regex['regex'].search(process.process).group()
                    new_match = old_match.replace(name, new_name)
                    process.process = process.process.replace(old_match, new_match)
            process.update_process_ast()

    def accesses(self, accesses=None, exclude=list(), no_labels=False):
        if not accesses:
            accss = dict()

            if not self.__accesses or len(exclude) > 0 or no_labels:
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

                if not self.__accesses and len(exclude) == 0 and not no_labels:
                    self.__accesses = accss
            else:
                accss = self.__accesses

            return accss
        else:
            self.__accesses = accesses

    def resolve_access(self, access):
        if isinstance(access, Label):
            string = '%{}%'.format(access.name)
        elif isinstance(access, str):
            string = access
        else:
            raise TypeError('Unsupported access token')
        return self.__accesses[string]

    def update_process_ast(self):
        _update_process_ast(self)


class Action:

    def __init__(self, name):
        self.name = name
        self.comment = None


class Subprocess(Action):

    def __init__(self, name):
        super().__init__(name)
        self.process = None
        self.condition = None
        self.__process_ast = None

    @property
    def process_ast(self):
        if not self.__process_ast:
            self.__process_ast = parse_process(self.process)
        return self.__process_ast

    def update_process_ast(self):
        _update_process_ast(self)


class Dispatch(Action):

    def __init__(self, name):
        super().__init__(name)
        self.condition = None
        self.parameters = []
        self.broadcast = False
        self.peers = []


class Receive(Action):

    def __init__(self, name):
        super().__init__(name)
        self.parameters = []
        self.condition = None
        self.replicative = False
        self.peers = []


class Call(Action):

    def __init__(self, name):
        super().__init__(name)
        self.condition = None
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
        self.condition = None


class Condition(Action):

    def __init__(self, name):
        super().__init__(name)
        self.statements = []
        self.condition = None
