import re

from core.avtg.emg.common.signature import BaseType, Pointer, Structure, Array, Union, Function, Primitive, \
    import_signature


class Variable:
    name_re = re.compile("\(?\*?%s\)?")

    def __init__(self, name, file, signature, export=False):
        self.name = name
        self.file = file
        self.export = export
        self.value = None
        self.use = 0

        if type(signature) is str:
            self.declaration = import_signature(signature)
        elif issubclass(type(signature), BaseType):
            self.declaration = signature
        else:
            raise ValueError("Attempt to create variable {} without signature".format(name))

    def declare_with_init(self):
        # Ger declaration
        declaration = self.declare(extern=False)

        # Add memory allocation
        if self.value:
            declaration += " = {}".format(self.value)

        return declaration

    def free_pointer(self, conf):
        expr = None
        if type(self.declaration) is Pointer and\
                ((type(self.declaration.points) is Structure and conf['structures']) or
                 (type(self.declaration.points) is Array and conf['arrays']) or
                 (type(self.declaration.points) is Union and conf['unions']) or
                 (type(self.declaration.points) is Function and conf['functions']) or
                 (type(self.declaration.points) is Primitive and conf['primitives'])):
            expr = "{}({})".format(FunctionModels.free_function_map["FREE"], self.name)
        return expr

    def declare(self, extern=False):
        # Generate declaration
        expr = self.declaration.to_string(self.name)

        # Add extern prefix
        if extern:
            expr = "extern " + expr

        return expr


class FunctionDefinition:

    def __init__(self, name, file, signature=None, export=False):
        self.name = name
        self.file = file
        self.export = export
        self.__body = None

        if not signature:
            signature = 'void f(void)'
        self.declaration = import_signature(signature)

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
        declaration = self.declaration.to_string(self.name)
        declaration += ';'

        if extern:
            declaration = "extern " + declaration
        return [declaration + "\n"]

    def get_definition(self):
        declaration = '{} {}({})'.format(self.declaration.return_value.to_string(), self.name,
                                         ', '.join([self.declaration.parameters[index].to_string('arg{}'.format(index))
                                                    for index in range(len(self.declaration.parameters))]))

        lines = list()
        lines.append(declaration + " {\n")
        lines.extend(self.body.get_lines(1))
        lines.append("}\n")
        return lines


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


class Aspect(FunctionDefinition):

    def __init__(self, name, declaration, aspect_type="after"):
        self.name = name
        self.declaration = declaration
        self.aspect_type = aspect_type
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

    def get_aspect(self):
        lines = list()
        lines.append("after: call({}) ".format("$ {}(..)".format(self.name)) +
                     " {\n")
        lines.extend(self.body.get_lines(1))
        lines.append("}\n")
        return lines


class FunctionModels:

    # todo: implement all models
    mem_function_map = {
        "ALLOC": "ldv_malloc",
        "ZALLOC": "ldv_malloc"
    }
    free_function_map = {
        "FREE": "ldv_free"
    }
    irq_function_map = {
        "IN_INTERRUPT_CONTEXT": 'ldv_in_interrupt_context',
        "SWITCH_TO_IRQ_CONTEXT": 'ldv_switch_to_interrupt_context',
        "SWITCH_TO_PROCESS_CONTEXT": 'ldv_switch_to_process_context'
    }

    mem_function_re = "\$({})\(%({})%(?:,\s?(\w+))?\)"
    irq_function_re = "\$({})"

    @staticmethod
    def init_pointer(signature):
        #return "{}(sizeof({}))".format(FunctionModels.mem_function_map["ALLOC"], signature.points.to_string(''))
        return "{}(sizeof({}))".format(FunctionModels.mem_function_map["ALLOC"], '0')

    def __replace_mem_call(self, match):
        function, label_name, flag = match.groups()
        if function not in self.mem_function_map:
            raise NotImplementedError("Model of {} is not supported".format(function))
        elif not self.mem_function_map[function]:
            raise NotImplementedError("Set implementation for the function {}".format(function))

        if type(self.signature) is Pointer:
            # todo: Implement proper paratmeters initialization (avoid providing sizeof until problem with incomplete
            #       types is solved)
            #return "{}(sizeof({}))".format(self.mem_function_map[function], self.signature.points.to_string(''))
            return "{}(sizeof({}))".format(self.mem_function_map[function], '0')
        else:
            raise ValueError('This is not a pointer')

    def __replace_free_call(self, match):
        function, label_name, flag = match.groups()
        if function not in self.free_function_map:
            raise NotImplementedError("Model of {} is not supported".format(function))
        elif not self.free_function_map[function]:
            raise NotImplementedError("Set implementation for the function {}".format(function))

        # Create function call
        if type(self.signature) is Pointer:
            return "{}(%{}%)".format(self.free_function_map[function], label_name)
        else:
            raise ValueError('This is not a pointer')

    def __replace_irq_call(self, match):
        function = match.groups()[0]
        if function not in self.irq_function_map:
            raise NotImplementedError("Model of {} is not supported".format(function))
        elif not self.irq_function_map[function]:
            raise NotImplementedError("Set implementation for the function {}".format(function))

        # Replace
        return self.irq_function_map[function]

    def replace_models(self, label, signature, string):
        self.signature = signature

        ret = string
        # Memory functions
        for function in sorted(self.mem_function_map.keys()):
            regex = re.compile(self.mem_function_re.format(function, label))
            ret = regex.sub(self.__replace_mem_call, ret)

        # Free functions
        for function in sorted(self.free_function_map.keys()):
            regex = re.compile(self.mem_function_re.format(function, label))
            ret = regex.sub(self.__replace_free_call, ret)

        # IRQ functions
        for function in sorted(self.irq_function_map.keys()):
            regex = re.compile(self.irq_function_re.format(function))
            ret = regex.sub(self.__replace_irq_call, ret)
        return ret

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
