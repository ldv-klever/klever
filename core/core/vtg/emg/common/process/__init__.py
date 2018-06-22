#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

from core.vtg.emg.common.process.Parser import parse_process


def generate_regex_set(self, subprocess_name):
    """
    Function generates regexes to parse out actions from process descriptions and determine their kind.

    :param self: This a formal useless parameter to allow using this function as a method.
    :param subprocess_name:
    :return: List of dictionary pairs [{'regex': re obj, 'type': Action class obj}]
    """
    dispatch_template = '\[@?{}(?:\[[^)]+\])?\]'
    receive_template = '\(!?{}(?:\[[^)]+\])?\)'
    condition_template = '<{}(?:\[[^)]+\])?>'
    subprocess_template = '{}'

    subprocess_re = re.compile("{" + subprocess_template.format(subprocess_name) + "}")
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
    """
    Class to represent expressions based on labels from process descriptions.

    For instance: %mylabel%.
    """

    def __init__(self, expression):
        self.expression = expression
        self.label = None
        self.list_access = None


class Label:
    """
    The class represent Label from process descriptions.

    A label is a C variable without a strictly given scope. It can be local, global depending on translation of the
    environment model to C code. Process state consists of labels and from current action.
    """
    def __init__(self, name):
        self.value = None
        self.declaration = None
        self.name = name

    def compare_with(self, label):
        """
        Compare the label with a given one comparing their declarations.

        :param label: Label object.
        :return: Return 'different' or 'equal'.
        """
        if self.declaration and label.declaration:
            my_signature = self.declaration
            ret = my_signature.compare_signature(label.declaration)
            if not ret:
                return 'different'
            else:
                return 'equal'
        else:
            raise NotImplementedError("Cannot compare label '{}' with label '{}'".format(label.name, label.name))


class Process:
    """
    Represents a process.

    The process is a part of an environment. It can be a separate thread, a process or just a function which is
    executed within the same program context (Model of non-defined function). A process has a state which consists of
    labels and a process which specifies a sequence (potentially it can be infinite) of actions. An action can send or
    receive data across processes,  just contain a code to execute or represent an operator to direct control flow.
    """

    label_re = re.compile('%(\w+)((?:\.\w*)*)%')

    def __init__(self, name):
        self.name = name
        self.category = None
        self.pretty_id = None
        self.comment = None
        self.labels = {}
        self.actions = {}
        self.process = None
        self.headers = list()
        self.declarations = dict()
        self.definitions = dict()
        self.identifier = None
        self._process_ast = None
        self._accesses = dict()

    @property
    def unmatched_receives(self):
        """
        Returns Receive actions that do not have peers.

        :return: A list of Action objects.
        """
        return [self.actions[act] for act in self.actions.keys() if isinstance(self.actions[act], Receive) and
                len(self.actions[act].peers) == 0]

    @property
    def unmatched_dispatches(self):
        """
        Returns Dispatch actions that do not have peers.

        :return: A list of Action objects.
        """
        return [self.actions[act] for act in self.actions.keys() if isinstance(self.actions[act], Dispatch) and
                len(self.actions[act].peers) == 0]

    @property
    def dispatches(self):
        """
        Returns Dispatch actions.

        :return: A list of Action objects.
        """
        return [self.actions[act] for act in self.actions.keys() if isinstance(self.actions[act], Dispatch)]

    @property
    def receives(self):
        """
        Returns Receive actions.

        :return: A list of Action objects.
        """
        return [self.actions[act] for act in self.actions.keys() if isinstance(self.actions[act], Receive)]

    @property
    def unused_labels(self):
        """
        Returns a set of label names which are not referenced in the process description. They are candidates to be
        deleted.

        :return: A set of label names.
        """
        used_labels = set()

        def extract_labels(expr):
            for m in self.label_re.finditer(expr):
                used_labels.add(m.group(1))

        for action in self.actions.values():
            if isinstance(action, Receive) or isinstance(action, Dispatch):
                for param in action.parameters:
                    extract_labels(param)
            if isinstance(action, Condition):
                for statement in action.statements:
                    extract_labels(statement)
            if action.condition:
                for statement in action.condition:
                    extract_labels(statement)
        unused_labels = set(self.labels.keys()).difference(used_labels)
        return unused_labels

    @property
    def process_ast(self):
        """
        Return an abstract syntax tree generated by a process parser on base of process description expressed in the
        DSL.

        :return: An abstract syntax tree (dict).
        """
        if not self._process_ast:
            self._process_ast = parse_process(self.process)
        return self._process_ast

    def insert_action(self, old, new, position):
        """
        Insert a new action to the process between, before or instead of a given action.

        :param old: An existing Action representation (<action_name>, {action_name}, ....).
        :param new: A new Action representation (<action_name>, {action_name}, ....).
        :param position: One of the following values: "before", "after", "instead".
        :return: None
        """
        if not old or old not in self.actions:
            raise KeyError('Cannot rename action {!r} in process {!r} because it does not exist'.
                           format(old, self.name))
        if position == 'instead':
            # Delete old subprocess
            del self.actions[old]

        # Replace action entries
        processes = [self]
        processes.extend(
            [self.actions[name] for name in self.actions.keys() if isinstance(self.actions[name], Subprocess)])
        regexes = generate_regex_set(None, old)
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
        """
        Rename given action. It replaces also process strings and corresponding abstract syntax trees.

        :param name: An old name.
        :param new_name: A new name.
        :return: None
        """
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
            [self.actions[name] for name in self.actions.keys() if isinstance(self.actions[name], Subprocess)])
        regexes = generate_regex_set(None, name)
        for process in processes:
            for regex in regexes:
                if regex['regex'].search(process.process):
                    # Replace signal entries
                    old_match = regex['regex'].search(process.process).group()
                    new_match = old_match.replace(name, new_name)
                    process.process = process.process.replace(old_match, new_match)
            process.update_process_ast()

    def accesses(self, accesses=None, exclude=list(), no_labels=False):
        """
        Go through the process description or retrieve from the cache dictionary with possible label accesses.

        :param accesses: Add to the cache an existing dictionary with accesses (Dictionary: {'%blblb%': [Access objs]}).
        :param exclude: Exclude accesses from descriptions of actions of given types (List of Action class names).
        :param no_labels: Exclude accesses based on labels which are not referred anywhere (Bool).
        :return:
        """
        if not accesses:
            accss = dict()

            if len(self._accesses) == 0 or len(exclude) > 0 or no_labels:
                # Collect all accesses across process subprocesses
                for action in [self.actions[name] for name in self.actions.keys()]:
                    tp = type(action)
                    if tp not in exclude:
                        if isinstance(action, Receive) or isinstance(action, Dispatch):
                            for index in range(len(action.parameters)):
                                accss[action.parameters[index]] = []
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
                    for label in [self.labels[name] for name in self.labels.keys()]:
                        access = '%{}%'.format(label.name)
                        if access not in accss or len(accss[access]) == 0:
                            accss[access] = []
                            new = Access(access)
                            new.label = label
                            new.list_access = [label.name]
                            accss[access] = [new]

                if not self._accesses and len(exclude) == 0 and not no_labels:
                    self._accesses = accss
            else:
                accss = self._accesses

            return accss
        else:
            self._accesses = accesses

    def resolve_access(self, access):
        """
        Get a string access and return a matching list of Access objects.

        :param access: String access like "%mylabel%".
        :return: List with Access objects.
        """
        if isinstance(access, Label):
            string = '%{}%'.format(access.name)
        elif isinstance(access, str):
            string = access
        else:
            raise TypeError('Unsupported access token')
        return self._accesses[string]

    def update_process_ast(self):
        """
        Parse process descriptions again and reconstruct an abstract syntax tree.

        :return: None.
        """
        _update_process_ast(self)

    def add_declaration(self, file, name, string):
        """
        Add a C declaration which should be added to the environment model as a global variable alongside with the code
        generated for this process.

        :param file: File to add ("environment model" if it is not a particular program file).
        :param name: Variable or function name to add.
        :param string: String with the declaration.
        :return: None.
        """
        if file not in self.declarations:
            self.declarations[file] = dict()

        if name not in self.declarations:
            self.declarations[file][name] = string

    def add_definition(self, file, name, strings):
        """
        Add a C function definition which should be added to the environment model alongside with the code generated
        for this process.

        :param file: File to add ("environment model" if it is not a particular program file).
        :param name: Function name.
        :param strings: Strings with the definition.
        :return: None.
        """
        if file is None:
            raise ValueError("You have to give file name to add definition of function {!r}".format(name))

        if file not in self.definitions:
            self.definitions[file] = dict()

        if name not in self.definitions:
            self.definitions[file][name] = strings

    def add_label(self, name, declaration, value=None):
        """
        Add to the process a new label. Do not rewrite existing labels - it is a more complicated operation, since it
        would require updating of accesses in the cache and actions.

        :param name: Label name.
        :param declaration: Declaration object.
        :param value: Value string or None.
        :return: New Label object.
        """
        lb = Label(name)
        lb.declaration = declaration
        if value:
            lb.value = value
        self.labels[name] = lb
        acc = Access('%{}%'.format(name))
        acc.label = lb
        acc.list_access = [lb.name]
        self._accesses[acc.expression] = [acc]
        return lb

    def add_condition(self, name, condition, statements, comment):
        """
        Add new Condition action. Later you can add it to a particular place to execute using an another method.

        :param name: Action name.
        :param condition: List of conditional expresstions.
        :param statements: List with statements to execute.
        :param comment: A comment for the action (A short sentence).
        :return: A new Condition object.
        """
        new = Condition(name)
        self.actions[name] = new

        new.condition = condition
        new.statements = statements
        new.comment = comment
        return new


class Action:
    """
    Base class for actions which can be executed in terms of a Process. Each action of a process is executed strictly
    one after another. All they are executed in the same context (depending on chosen translator).
    """

    def __init__(self, name):
        self.name = name
        self.comment = None
        self.condition = None


class Subprocess(Action):
    """
    An action to direct the control flow. It implies execution of given sequence of actions instead of the current one.
    In contrast to C functions there is no any return or exit from the current process sequence given in the action.
    If the sequence is finite then the process just will stop execution of actions. It means that it is useless to
    place any actions after this one.

    An example of action string: "{mynewsequence}".
    """

    def __init__(self, name):
        super(Subprocess, self).__init__(name)
        self.process = None
        self.__process_ast = None

    @property
    def process_ast(self):
        """
        Get or calculate an return an abstract syntax tree for the process sequence given as an attribete of the action.

        :return: An abstract syntax tree (dict).
        """
        if not self.__process_ast:
            self.__process_ast = parse_process(self.process)
        return self.__process_ast

    def update_process_ast(self):
        """
        Update the cache or caclulate the abstract syntax tree for the first time.

        :return:
        """
        _update_process_ast(self)


class Dispatch(Action):
    """
    An action that implies to send a signal to an another environmental process. It allows to save values from labels
    of the dispatcher in labels of the receiver via parameters. If there is no peer receivers then the signal will not
    be sent. If there is no receiver at the moment the semantics of sending would be sleeping. If it is possible to send
    a signal or do an another action then it still can be executed.

    An example of action string: "[mysend]".
    """

    def __init__(self, name):
        super(Dispatch, self).__init__(name)
        self.parameters = []
        self.broadcast = False
        self.peers = []


class Receive(Action):
    """
    Class to represent receiver actions. Semantics of receiving is instant. If there is no sender at the moment then
    the action is skipped. If there is no sender at the moment then the process will sleep or do an another possible
    action.

    An example of action string: "(mysend)".
    """

    def __init__(self, name):
        super(Receive, self).__init__(name)
        self.parameters = []
        self.replicative = False
        self.peers = []


class Condition(Action):
    """
    Class represents a C code base block with some code. You also can add a condition. In contrast to other actions
    if a condition is not satisfied and the action is the one possible action in a choose operator (|) then this
    conditional branch will not be chosen. Note then in other actions the whole action is just skipped.

    An example of action string: "<mycondition>".
    """

    def __init__(self, name):
        super(Condition, self).__init__(name)
        self.statements = []
