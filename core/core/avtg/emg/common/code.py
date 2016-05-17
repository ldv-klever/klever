import re

from core.avtg.emg.common.signature import Declaration, Pointer, Structure, Array, Union, Function, Primitive, \
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
        elif issubclass(type(signature), Declaration):
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

    mem_function_template = "\$({})\(%({})%(?:,\s?(\w+))?\)"
    simple_function_template = "\$({})\("
    access_template = '\w+(?:(?:[.]|->)\w+)*'
    mem_function_re = re.compile(mem_function_template.format('\w+', access_template))
    simple_function_re = re.compile(simple_function_template.format('\w+'))
    access_re = re.compile('(%{}%)'.format(access_template))

    @staticmethod
    def init_pointer(signature):
        #return "{}(sizeof({}))".format(FunctionModels.mem_function_map["ALLOC"], signature.points.to_string(''))
        return "{}(sizeof({}))".format(FunctionModels.mem_function_map["ALLOC"], '0')

    @staticmethod
    def text_processor(automaton, statement):
        # Replace model functions
        mm = FunctionModels()

        # Replace function names
        stms = []
        matched = False
        for fn in mm.simple_function_re.findall(statement):
            matched = True

            # Bracket is required to ignore CIF expressions like $res or $arg1
            if fn in mm.mem_function_map or fn in mm.free_function_map:
                access = mm.mem_function_re.search(statement).group(2)
                if fn in mm.mem_function_map:
                    replacement = mm._replace_mem_call
                else:
                    replacement = mm._replace_free_call

                accesses = automaton.process.resolve_access('%{}%'.format(access))
                for access in accesses:
                    if access.interface:
                        signature = access.label.get_declaration(access.interface.identifier)
                    else:
                        signature = access.label.prior_signature

                    if signature:
                        if access.interface:
                            var = automaton.determine_variable(access.label, access.list_interface[0].identifier)
                        else:
                            var = automaton.determine_variable(access.label)

                        if type(var.declaration) is Pointer:
                            mm.signature = var.declaration
                            new = mm.mem_function_re.sub(replacement, statement)
                            new = access.replace_with_variable(new, var)
                            stms.append(new)
            elif fn in mm.irq_function_map:
                statement = mm.simple_function_re.sub(mm.irq_function_map[fn] + '(', statement)
                stms.append(statement)
            else:
                raise NotImplementedError("Model function '${}' is not supported".format(fn))

        if not matched:
            stms = [statement]

        # Replace rest accesses
        final = []
        matched = False
        for stm in stms:
            for expression in mm.access_re.findall(stm):
                matched = True

                accesses = automaton.process.resolve_access(expression)
                for access in accesses:
                    if access.interface:
                        var = automaton.determine_variable(access.label, access.list_interface[0].identifier)
                    else:
                        var = automaton.determine_variable(access.label)

                    final.append(access.replace_with_variable(stm, var))

        if not matched:
            final = stms
        return final

    def _replace_mem_call(self, match):
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

    def _replace_free_call(self, match):
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

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
