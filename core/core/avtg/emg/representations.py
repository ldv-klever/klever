import re
import copy

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

    @staticmethod
    def copy_signature(old, new):
        cp = copy.deepcopy(new)
        cp.array = old.array
        cp.pointer = old.pointer
        cp.interface = old.interface
        return cp

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
            elif self.type_class == "struct":
                if self.structure_name == signature.structure_name:
                    return True
                elif len(self.fields.keys()) > 0 and len(signature.fields.keys()) > 0 \
                        and len(set(signature.fields.keys()).intersection(self.fields.keys())) > 0:
                    for param in self.fields:
                        if param in signature.fields:
                            if not self.fields[param].compare_signature(signature.fields[param]):
                                return False
                    for param in signature.fields:
                        if param in self.fields:
                            if not signature.fields[param].compare_signature(self.fields[param]):
                                return False
                    return True
                return False
        else:
            return True

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
        self.fields = None

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

    def get_string(self):
        # Dump signature as a string
        if self.type_class == "function":
            # Add return value
            if self.return_value and self.return_value.type_class != "primitive":
                string = "$ "
            else:
                string = "{} ".format(self.return_value.expression)

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
            declaration = self.name_re.sub("(* {})".format(self.name), declaration)
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

    mem_function_re = "\$({})\(%(\w+)%(?:,\s?(\w+))?\)"
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

        # Create function call
        if label_name not in self.process.labels:
            raise ValueError("Process {} has no label {}".format(self.process.name, label_name))
        signature = self.process.labels[label_name].signature
        if signature.type_class in ["struct", "primitive"] and signature.pointer:
            return "{}(sizeof(struct {}))".format(self.mem_function_map[function], signature.structure_name)
        else:
            raise NotImplementedError("Cannot initialize signature {} which is not pointer to structure or primitive".
                                      format(signature.expression, signature.type_class))

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

    def replace_models(self, process, string):
        self.process = process
        ret = string
        # Memory functions
        for function in self.mem_function_map:
            regex = re.compile(self.mem_function_re.format(function))
            ret = regex.sub(self.__replace_mem_call, ret)

        # Free functions
        for function in self.free_function_map:
            regex = re.compile(self.mem_function_re.format(function))
            ret = regex.sub(self.__replace_free_call, ret)

        # IRQ functions
        for function in self.irq_function_map:
            regex = re.compile(self.irq_function_re.format(function))
            ret = regex.sub(self.__replace_irq_call, ret)
        return ret

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'