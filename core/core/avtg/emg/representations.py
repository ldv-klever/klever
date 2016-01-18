import re
import copy
import grako

fi_regex = re.compile("(\w*)\.(\w*)")
fi_extract = re.compile("\*?%((?:\w*\.)?\w*)%")


def is_full_identifier(string):
    if fi_regex.fullmatch(string) and len(fi_regex.fullmatch(string).groups()) == 2:
        return True
    else:
        return False


def extract_full_identifier(string):
    if is_full_identifier(string):
        category, identifier = fi_regex.fullmatch(string).groups()
        return category, identifier
    else:
        raise ValueError("Given string {} is not a full identifier".format(string))


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


def process_parse(string):
    return process_model.parse(string, ignorecase=True)


class Interface:

    def __init__(self, signature, category, identifier, header, implemented_in_kernel=False):
        self.signature = Signature(signature)
        self.header = header
        self.category = category
        self.identifier = identifier
        self.implemented_in_kernel = implemented_in_kernel
        self.resource = False
        self.callback = False
        self.container = False
        self.kernel_interface = False
        self.called_in_model = False
        self.fields = {}
        self.implementations = []

    @property
    def role(self, role=None):
        if not self.callback:
            raise TypeError("Non-callback interface {} does not have 'role' attribute".format(self.identifier))

        if not role:
            return self.identifier
        else:
            self.identifier = role

    @property
    def full_identifier(self, full_identifier=None):
        if not self.category and not full_identifier:
            raise ValueError("Cannot determine full identifier {} without interface category")
        elif full_identifier:
            category, identifier = extract_full_identifier(full_identifier)
            self.category = category
            self.identifier = identifier
        else:
            return "{}.{}".format(self.category, self.identifier)


class Signature:

    def __init__(self, expression):
        """
        Expect signature expression.
        :param expression:
        :return:
        """
        self.expression = expression
        self.type_class = None
        self.pointer = False
        self.array = False
        self.return_value = None
        self.interface = None
        self.function_name = None
        self.parameters = None
        self.structure_name = None
        self.fields = None

        # TODO: doesn't match "void (**%s)(struct nvme_dev *, void *, struct nvme_completion *)", e.g. for drivers/block/nvme.ko.
        ret_val_re = "(?:\$|(?:void)|(?:[\w\s]*\*?%s)|(?:\*?%[\w.]*%)|(?:[^%]*))"
        identifier_re = "(?:(?:(\*?)%s)|(?:(\*?)%[\w.]*%)|(?:(\*?)\w*))(\s?\[\w*\])?"
        args_re = "(?:[^()]*)"
        function_re = re.compile("^{}\s\(?{}\)?\s?\({}\)\Z".format(ret_val_re, identifier_re, args_re))
        if function_re.fullmatch(self.expression):
            self.type_class = "function"
            groups = function_re.fullmatch(self.expression).groups()
            if (groups[0] and groups[0] != "") or (groups[1] and groups[1] != ""):
                self.pointer = True
            else:
                self.pointer = False
            if groups[2] and groups[2] != "":
                self.array = True
            else:
                self.array = False

        macro_re = re.compile("^\w*\s?\({}\)\Z".format(args_re))
        if macro_re.fullmatch(self.expression):
            self.type_class = "macro"
            self.pointer = False
            self.array = False

        struct_re = re.compile("^struct\s+(?:[\w|*]*\s)+(\**)%s\s?((?:\[\w*\]))?\Z")
        struct_name_re = re.compile("^struct\s+(\w+)")
        self.__check_type(struct_re, "struct")

        # TODO: doesn't match "char const * const %s", e.g. for drivers/block/rsxx/rsxx.ko.
        # TODO: doesn't match "char const * const *%s", e.g. for drivers/staging/comedi/drivers/poc.ko.
        value_re = re.compile("^(\w*\s+)+(\**)%s((?:\[\w*\]))?\Z")
        self.__check_type(value_re, "primitive")

        interface_re = re.compile("^(\*?)%.*%\Z")
        if not self.type_class and interface_re.fullmatch(self.expression):
            self.type_class = "interface"

        if self.type_class in ["function", "macro"]:
            self.__extract_function_interfaces()
        if self.type_class == "interface":
            ptr = interface_re.fullmatch(self.expression).group(1)
            if ptr and ptr != "":
                self.pointer = True
            self.interface = fi_extract.fullmatch(self.expression).group(1)
        if self.type_class == "struct":
            self.fields = {}
            self.structure_name = struct_name_re.match(self.expression).group(1)

        if not self.type_class:
            raise ValueError("Cannot determine signature type (function, structure, primitive or interface) {}".
                             format(self.expression))

    def __check_type(self, regex, type_name):
        if not self.type_class and regex.fullmatch(self.expression):
            self.type_class = type_name
            groups = regex.fullmatch(self.expression).groups()
            if groups[len(groups) - 2] and groups[len(groups) - 2] != "":
                self.pointer = True
            else:
                self.pointer = False

            if groups[len(groups) - 1] and groups[len(groups) - 1] != "":
                self.array = True
            else:
                self.array = False

            return True
        else:
            return False

    def __extract_function_interfaces(self):
        identifier_re = "((?:\*?%s)|(?:\*?%[\w.]*%)|(?:\*?\w*))(?:\s?\[\w*\])?"
        args_re = "([^()]*)"

        if self.type_class == "function":
            ret_val_re = "(\$|(?:void)|(?:[\w\s]*\*?%s)|(?:\*?%[\w.]*%)|(?:[^%]*))"
            function_re = re.compile("^{}\s\(?{}\)?\s?\({}\)\Z".format(ret_val_re, identifier_re, args_re))

            if function_re.fullmatch(self.expression):
                ret_val, name, args = function_re.fullmatch(self.expression).groups()
            else:
                raise ValueError("Cannot parse function signature {}".format(self.expression))

            if ret_val in ["$", "void"] or "%" not in ret_val:
                self.return_value = None
            else:
                self.return_value = Signature(ret_val)
        else:
            identifier_re = "(\w*)"
            macro_re = re.compile("^{}\s?\({}\)\Z".format(identifier_re, args_re))

            if macro_re.fullmatch(self.expression):
                name, args = macro_re.fullmatch(self.expression).groups()
            else:
                raise ValueError("Cannot parse macro signature {}".format(self.expression))
        self.function_name = name

        self.parameters = []
        if args != "void":
            for arg in args.split(", "):
                if arg in ["$", "..."] or "%" not in arg:
                    self.parameters.append(None)
                else:
                    self.parameters.append(Signature(arg))

    def replace(self, new):
        for att_name in ["expression", "type_class", "return_value", "function_name", "parameters", "fields",
                         "structure_name"]:
            setattr(self, att_name, getattr(new, att_name))

    def compare_signature(self, signature):
        # Need this to compare with undefined arguments
        if not signature:
            return False

        # Be sure that the signature is not an interface
        if signature.type_class == "interface" or self.type_class == "interface":
            raise TypeError("Interface signatures cannot be compared")

        if self.type_class != signature.type_class:
            return False
        if self.interface and signature.interface and self.interface.full_identifier != \
                signature.interface.full_identifier:
            return False
        elif self.interface and signature.interface \
                and self.interface.full_identifier == signature.interface.full_identifier:
            return True

        if self.expression != signature.expression:
            if self.type_class == "function":
                if self.return_value and signature.return_value \
                        and not self.return_value.compare_signature(signature.return_value):
                    return False
                elif (self.return_value and not signature.return_value) or \
                        (not self.return_value and signature.return_value):
                    return False

                if len(self.parameters) == len(signature.parameters):
                    for param in range(len(self.parameters)):
                        if not self.parameters[param].compare_signature(signature.parameters[param]):
                            return False
                    return True
                else:
                    return False
            elif self.type_class == "struct" and self.structure_name == signature.structure_name:
                return True
            else:
                return False
        else:
            return True

    def get_string(self):
        # Dump signature as a string
        if self.type_class == "function":
            # Add return value
            if self.return_value and self.return_value.type_class != "primitive":
                string = "{} ".format(self.return_value.expression)
            else:
                string = "$ "

            # Add name
            if self.function_name:
                string += self.function_name
            else:
                string += "%s"

            # Add parameters
            if self.parameters and len(self.parameters) > 0:
                params = []
                for p in self.parameters:
                    if p.interface:
                        params.append("%{}%".format(p.interface.full_identifier))
                    else:
                        params.append("$")

                string += "({})".format(", ".join(params))
            else:
                string += "(void)"

            return string
        else:
            return self.expression


class Variable:
    name_re = re.compile("\(?\*?%s\)?")

    def __init__(self, name, file, signature=Signature("void *%s"), export=False):
        self.name = name
        self.file = file
        if not signature:
            raise ValueError("Attempt to create variable {} without signature".format(name))
        self.signature = signature
        self.value = None
        self.export = export
        self.use = 0

    def declare_with_init(self, init=True):
        # Ger declaration
        declaration = self.declare(extern=False)

        # Add memory allocation
        if not self.value and init:
            if self.signature.pointer and self.signature.type_class == "struct":
                alloc = ModelMap.init_pointer(self.signature)
                self.value = alloc

        # Set value
        if self.value:
            declaration += " = {}".format(self.value)
        return declaration

    def free_pointer(self):
        return "{}({})".format(ModelMap.free_function_map["FREE"], self.name)

    def declare(self, extern=False):
        # Generate declaration
        declaration = self.signature.expression
        if self.signature.type_class == "function":
            if self.signature.return_value:
                declaration = self.signature.return_value.expression.replace("%s", "") + " "
            else:
                declaration = "void "
            declaration += '(*' + self.name + ')'
            params = []
            for param in self.signature.parameters:
                pr = param.expression
                if param.pointer:
                    pr = pr.replace("*%s", "*")
                    pr = pr.replace("%s", "*")
                else:
                    pr = pr.replace("*%s", "")
                    pr = pr.replace("%s", "")
                params.append(pr)
            declaration += '(' + \
                           ", ".join(params) + \
                           ')'
        else:
            if self.signature.pointer:
                declaration = declaration.replace("*%s", "*{}".format(self.name))
                declaration = declaration.replace("%s", "*{}".format(self.name))
            else:
                declaration = declaration.replace("%s", self.name)

        # Add extern prefix
        if extern:
            declaration = "extern " + declaration

        return declaration


class Function:

    def __init__(self, name, file, signature=Signature("void %s(void)"), export=False):
        self.name = name
        self.file = file
        self.signature = signature
        self.export = export
        self.__body = None

    @property
    def body(self, body=None):
        if not body:
            body = []

        if not self.__body:
            self.__body = FunctionBody(body)
        else:
            self.__body.concatenate(body)
        return self.__body

    def get_declaration(self, extern=False):
        declaration = self.signature.expression.replace("%s", self.name)
        declaration += ';'

        if extern:
            declaration = "extern " + declaration
        return [declaration + "\n"]

    def get_definition(self):
        if self.signature.type_class == "function" and not self.signature.pointer:
            lines = list()
            lines.append(self.signature.expression.replace("%s", self.name) + "{\n")
            lines.extend(self.body.get_lines(1))
            lines.append("}\n")
            return lines
        else:
            raise TypeError("Signature '{}' with class '{}' is not a function or it is a function pointer".
                            format(self.signature.expression, self.signature.type_class))


class FunctionBody:
    indent_re = re.compile("^(\t*)([^\s]*.*)")

    def __init__(self, body=None):
        if not body:
            body = []

        self.__body = []

        if len(body) > 0:
            self.concatenate(body)

    def _split_indent(self, string):
        split = self.indent_re.match(string)
        return {
            "indent": len(split.group(1)),
            "statement": split.group(2)
        }

    def concatenate(self, statements):
        if type(statements) is list:
            for line in statements:
                splitted = self._split_indent(line)
                self.__body.append(splitted)
        elif type(statements) is str:
            splitted = self._split_indent(statements)
            self.__body.append(splitted)
        else:
            raise TypeError("Can add only string or list of strings to function body but given: {}".
                            format(str(type(statements))))

    def get_lines(self, start_indent=1):
        lines = []
        for splitted in self.__body:
            line = (start_indent + splitted["indent"]) * "\t" + splitted["statement"] + "\n"
            lines.append(line)
        return lines


class ModelMap:

    # todo: implement all models
    mem_function_map = {
        "ALLOC": "ldv_successful_malloc",
        "ALLOC_RECURSIVELY": "ldv_successful_malloc",
        "ZINIT": "ldv_init_zalloc",
        "ZINIT_STRUCT": None,
        "INIT_STRUCT": None,
        "INIT_RECURSIVELY": None,
        "ZINIT_RECURSIVELY": None,
    }
    free_function_map = {
        "FREE": "ldv_free",
        "FREE_RECURSIVELY": None
    }
    irq_function_map = {
        "GET_CONTEXT": None,
        "IRQ_CONTEXT": None,
        "PROCESS_CONTEXT": None
    }

    mem_function_re = "\$({})\(%({})%(?:,\s?(\w+))?\)"
    irq_function_re = "\$({})"

    @staticmethod
    def init_pointer(signature):
        if signature.type_class in ["struct", "primitive"] and signature.pointer:
            return "{}(sizeof(struct {}))".format(ModelMap.mem_function_map["ZINIT"], signature.structure_name)
        else:
            raise NotImplementedError("Cannot initialize label {} which is not pointer to structure or primitive".
                                      format(signature.name, signature.type_class))

    def __replace_mem_call(self, match):
        function, label_name, flag = match.groups()
        if function not in self.mem_function_map:
            raise NotImplementedError("Model of {} is not supported".format(function))
        elif not self.mem_function_map[function]:
            raise NotImplementedError("Set implementation for the function {}".format(function))

        if self.signature.type_class in ["struct", "primitive"] and self.signature.pointer:
            return "{}(sizeof(struct {}))".format(self.mem_function_map[function], self.signature.structure_name)
        else:
            raise NotImplementedError("Cannot initialize signature {} which is not pointer to structure or primitive".
                                      format(self.signature.expression, self.signature.type_class))

    def __replace_free_call(self, match):
        function, label_name, flag = match.groups()
        if function not in self.free_function_map:
            raise NotImplementedError("Model of {} is not supported".format(function))
        elif not self.free_function_map[function]:
            raise NotImplementedError("Set implementation for the function {}".format(function))

        # Create function call
        return "{}(%{}%)".format(self.free_function_map[function], label_name)

    def __replace_irq_call(self, match):
        function = match.groups()
        if function not in self.mem_function_map:
            raise NotImplementedError("Model of {} is not supported".format(function))
        elif not self.mem_function_map[function]:
            raise NotImplementedError("Set implementation for the function {}".format(function))

        # Replace
        return self.mem_function_map[function]

    def replace_models(self, label, signature, string):
        self.signature = signature

        ret = string
        # Memory functions
        for function in self.mem_function_map:
            regex = re.compile(self.mem_function_re.format(function, label))
            ret = regex.sub(self.__replace_mem_call, ret)

        # Free functions
        for function in self.free_function_map:
            regex = re.compile(self.mem_function_re.format(function, label))
            ret = regex.sub(self.__replace_free_call, ret)

        # IRQ functions
        for function in self.irq_function_map:
            regex = re.compile(self.irq_function_re.format(function))
            ret = regex.sub(self.__replace_irq_call, ret)
        return ret


class Implementation:

    def __init__(self, value, file, base_container_id=None, base_container_value=None):
        self.base_container = base_container_id
        self.base_value = base_container_value
        self.value = value
        self.file = file


class Access:
    def __init__(self, expression):
        self.expression = expression
        self.label = None
        self.interface = None
        self.list_access = None
        self.list_interface = None

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

                if len(label2.interfaces) == 0 and len(label1.interfaces) > 0:
                    label2.interfaces = label1.interfaces
                elif len(label2.interfaces) > 0 and len(label1.interfaces) == 0:
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
