import re
import copy
import grako

process_grammar = \
"""
(* Main expression *)
FinalProcess = (Operators | Bracket)$;
Operators = Switch | Sequence;

(* Signle process *)
Process = Null | ReceiveProcess | SendProcess | SubprocessProcess | ConditionProcess | Bracket;
Null = null:"0";
ReceiveProcess = receive:Receive;
SendProcess = dispatch:Send;
SubprocessProcess = subprocess:Subprocess;
ConditionProcess = condition:Condition;
Receive = "("[replicative:"!"]name:identifier[number:Repetition]")";
Send = "["[broadcast:"@"]name:identifier[number:Repetition]"]";
Condition = "<"name:identifier[number:Repetition]">";
Subprocess = "{"name:identifier"}";

(* Operators *)
Sequence = sequence:SequenceExpr;
Switch = options:SwitchExpr;
SequenceExpr = @+:Process{"."@+:Process}*;
SwitchExpr = @+:Sequence{"|"@+:Sequence}+;

(* Brackets *)
Bracket = process:BracketExpr;
BracketExpr = "("@:Operators")";

(* Basic expressions and terminals *)
Repetition = "["@:(number | label)"]";
identifier = /\w+/;
number = /\d+/;
label = /%\w+%/;
"""
process_model = grako.genmodel('process', process_grammar)


def process_parse(string):
    return process_model.parse(string, ignorecase=True)


def generate_regex_set(subprocess_name):
    dispatch_template = "\[@?{}(?:\[[^)]+\])?\]"
    receive_template = "\(!?{}(?:\[[^)]+\])?\)"
    condition_template = "<{}(?:\[[^)]+\])?>"
    subprocess_template = "{}"

    subprocess_re = re.compile("\{" + subprocess_template.format(subprocess_name) + "\}")
    receive_re = re.compile(receive_template.format(subprocess_name))
    dispatch_re = re.compile(dispatch_template.format(subprocess_name))
    condition_template_re = re.compile(condition_template.format(subprocess_name))
    regexes = [
        {"regex": subprocess_re, "type": "subprocess"},
        {"regex": dispatch_re, "type": "dispatch"},
        {"regex": receive_re, "type": "receive"},
        {"regex": condition_template_re, "type": "condition"}
    ]

    return regexes


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
            expr = "->".join(access)
        else:
            expr = ".".join(access)
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
        self.interfaces = None
        self.name = name
        self.__signature = None
        self.__signature_map = {}

    def import_json(self, dic):
        for att in ["container", "resource", "callback", "parameter", "value", "pointer"]:
            if att in dic:
                setattr(self, att, dic[att])

        if "interface" in dic:
            if type(dic["interface"]) is str:
                self.interfaces = [dic["interface"]]
            else:
                self.interfaces = dic["interface"]
        if "signature" in dic:
            self.__signature = Signature(dic["signature"])

    def signature(self, signature=None, interface=None):
        if not signature and not interface:
            return self.__signature
        elif signature and not interface:
            self.__signature = signature
            return self.__signature
        elif not signature and interface and interface in self.__signature_map:
            return self.__signature_map[interface]
        elif not signature and interface and interface not in self.__signature_map:
            return None
        elif signature and interface and interface in self.__signature_map:
            if self.signature(None, interface).compare_signature(signature):
                return self.__signature_map[interface]
            else:
                raise ValueError("Incompatible signature {} with interface {}".
                                 format(signature.expression, interface))
        elif signature and interface and interface not in self.__signature_map:
            self.__signature_map[interface] = signature

    def compare_with(self, label):
        if self.interfaces and label.interfaces:
            if len(list(set(self.interfaces) & set(label.interfaces))) > 0:
                return "equal"
            else:
                return "different"
        elif label.interfaces or self.interfaces:
            if (self.container and label.container) or (self.resource and label.resource) or \
               (self.callback and label.callback):
                return "сompatible"
            else:
                return "different"
        elif self.signature() and label.signature():
            my_signature = self.signature()
            ret = my_signature.compare_signature(label.signature())
            if not ret:
                return "different"
            else:
                return "equal"
        else:
            raise NotImplementedError("Cannot compare label '{}' with label '{}'".format(label.name, label.name))


class Process:
    label_re = re.compile("%(\w+)((?:\.\w*)*)%")

    def __init__(self, name, dic=None):
        # Default values
        self.labels = {}
        self.subprocesses = {}
        self.category = None
        self.process = None
        self.identifier = None
        self.__accesses = None
        if not dic:
            dic = {}

        # Provided values
        self.name = name

        # Import labels
        if "labels" in dic:
            for name in dic["labels"]:
                label = Label(name)
                label.import_json(dic["labels"][name])
                self.labels[name] = label

        # Import process
        if "process" in dic:
            self.process = dic["process"]

        # Import subprocesses
        if "subprocesses" in dic:
            for name in dic["subprocesses"]:
                subprocess = Subprocess(name, dic["subprocesses"][name])
                self.subprocesses[name] = subprocess

        # Check subprocess type
        self.__determine_subprocess_types()

        # Parse process
        if self.process:
            self.process_ast = process_parse(self.process)

    def __determine_subprocess_types(self):
        processes = [self.subprocesses[process_name].process for process_name in self.subprocesses
                     if self.subprocesses[process_name].process]
        processes.append(self.process)

        for subprocess_name in self.subprocesses:
            regexes = generate_regex_set(subprocess_name)

            match = 0
            process_type = None
            for regex in regexes:
                for process in processes:
                    if regex["regex"].search(process):
                        match += 1
                        process_type = regex["type"]
                        if process_type == "dispatch":
                            if "@{}".format(subprocess_name) in process:
                                self.subprocesses[subprocess_name].broadcast = True
                        break

            if match == 0:
                raise KeyError("Subprocess '{}' from process '{}' is not used actually".
                               format(subprocess_name, self.name))
            elif match > 1:
                raise KeyError("Subprocess '{}' from process '{}' was used differently at once".
                               format(subprocess_name, self.name))
            else:
                self.subprocesses[subprocess_name].type = process_type

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

    @property
    def unmatched_receives(self):
        unmatched = [self.subprocesses[subprocess] for subprocess in self.subprocesses
                     if self.subprocesses[subprocess].type == "receive" and
                     len(self.subprocesses[subprocess].peers) == 0 and not
                     self.subprocesses[subprocess].callback]
        return unmatched

    @property
    def unmatched_dispatches(self):
        unmatched = [self.subprocesses[subprocess] for subprocess in self.subprocesses
                     if self.subprocesses[subprocess].type == "dispatch" and
                     len(self.subprocesses[subprocess].peers) == 0 and not
                     self.subprocesses[subprocess].callback]
        return unmatched

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
            raise ValueError("Cannot extract label from access {} in process {}".format(string, format(string)))

    def establish_peers(self, process):
        peers = self.get_available_peers(process)
        for signals in peers:
            for index in range(len(self.subprocesses[signals[0]].parameters)):
                label1 = self.extract_label(self.subprocesses[signals[0]].parameters[index])
                label2 = process.extract_label(process.subprocesses[signals[1]].parameters[index])

                if (not label2.interfaces or len(label2.interfaces) == 0) and \
                        (label1.interfaces and len(label1.interfaces) > 0):
                    label2.interfaces = label1.interfaces
                elif (label2.interfaces and len(label2.interfaces) > 0) and \
                        (not label1.interfaces or len(label1.interfaces) == 0):
                    label1.interfaces = label2.interfaces

            self.subprocesses[signals[0]].peers.append(
                    {
                        "process": process,
                        "subprocess": process.subprocesses[signals[1]]
                    })
            process.subprocesses[signals[1]].peers.append(
                    {
                        "process": self,
                        "subprocess": self.subprocesses[signals[0]]
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

    def rename_subprocess(self, old_name, new_name):
        if old_name not in self.subprocesses:
            raise KeyError("Cannot rename subprocess {} in process {} because it does not exist".
                           format(old_name, self.name))

        subprocess = self.subprocesses[old_name]
        subprocess.name = new_name

        # Delete old subprocess
        del self.subprocesses[old_name]

        # Set new subprocess
        self.subprocesses[subprocess.name] = subprocess

        # Replace subprocess entries
        processes = [self]
        processes.extend([self.subprocesses[name] for name in self.subprocesses if self.subprocesses[name].process])
        regexes = generate_regex_set(old_name)
        for process in processes:
            for regex in regexes:
                if regex["regex"].search(process.process):
                    # Replace signal entries
                    old_match = regex["regex"].search(process.process).group()
                    new_match = old_match.replace(old_name, new_name)
                    process.process = process.process.replace(old_match, new_match)

                    # Recalculate AST
                    process.process_ast = process_parse(process.process)

    def accesses(self, accesses=None):
        if not accesses:
            if not self.__accesses:
                self.__accesses = {}

                # Collect all accesses across process subprocesses
                for subprocess in [self.subprocesses[name] for name in self.subprocesses]:
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
                    access = "%{}%".format(label.name)
                    if access not in self.__accesses:
                        self.__accesses[access] = []

            return self.__accesses
        else:
            self.__accesses = accesses

    def resolve_access(self, access, interface=None):
        if type(access) is Label:
            string = "%{}%".format(access.name)
        elif type(access) is str:
            string = access
        else:
            raise TypeError("Unsupported access token")

        if not interface:
            return self.__accesses[string]
        else:
            return [acc for acc in self.__accesses[string]
                    if acc.interface and acc.interface.full_identifier == interface][0]


class Subprocess:

    def __init__(self, name, dic):
        # Default values
        self.type = None
        self.process = None
        self.process_ast = None
        self.parameters = []
        self.callback = None
        self.callback_retval = None
        self.peers = []
        self.condition = None
        self.statements = None
        self.broadcast = False

        # Provided values
        self.name = name

        # Values from dictionary
        if "callback" in dic:
            self.callback = dic["callback"]

        # Add parameters
        if "parameters" in dic:
            self.parameters = dic["parameters"]

        # Add callback return value
        if "callback return value" in dic:
            self.callback_retval = dic["callback return value"]

        # Import condition
        if "condition" in dic:
            self.condition = dic["condition"]

        # Import statements
        if "statements" in dic:
            self.statements = dic["statements"]

        # Import process
        if "process" in dic:
            self.process = dic["process"]

            # Parse process
            self.process_ast = process_parse(self.process)

    def get_common_interface(self, process, position):
        pl = process.extract_label(self.parameters[position])
        if not pl.interfaces:
            return []
        else:
            interfaces = pl.interfaces
            for peer in self.peers:
                arg = peer["subprocess"].parameters[position]
                label = peer["process"].extract_label(arg)
                interfaces = set(interfaces) & set(label.interfaces)

            if len(interfaces) == 0:
                raise RuntimeError("Need at least one common interface to send signal")
            elif len(interfaces) > 1:
                raise NotImplementedError
            else:
                return list(interfaces)[0]

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'