import re

from core.avtg.emg.common.interface import Signature

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

        # todo: investigate deeper why the condition should be so strange
        if self.signature.type_class == "function" and not (not self.signature.return_value and
                        None in self.signature.parameters):
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
            return "{}(sizeof(struct {}))".format(ModelMap.mem_function_map["ALLOC"], signature.structure_name)
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

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
