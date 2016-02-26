import grako

class Signature:
    declarations_grammar = \
    """
    (* Declaration syntax based on Committee Draft — April 12, 2011 ISO/IEC 9899:201x but it is rather simplified *)

    signature = @:declaration $;

    declaration = function_declaration~ |
                  primitive_declaration~ |
                  interface_declaration~ |
                  undefined_declaration;

    function_declaration = return_value:declaration main_declarator:declarator '(' parameters:(parameter_list | void) ')' ~ |
                           return_value:void main_declarator:declarator '(' parameters:(parameter_list | void) ')';

    primitive_declaration = specifiers:{declaration_specifiers}* main_declarator:declarator;

    parameter_list = { [','] @:(function_declaration~ | primitive_declaration~ | interface_declaration~ | undefined_declaration~ | '...') }+;

    declaration_specifiers = storage_class_specifier |
                             type_qualifier |
                             function_specifier |
                             type_specifier;

    void = {void_specifiers}* @:"void";

    void_specifiers = storage_class_specifier |
                      type_qualifier |
                      function_specifier;

    function_specifier = "inline" | "_Noreturn";

    type_qualifier = "const" | "restrict" | "volatile" | "_Atomic";

    storage_class_specifier = "extern" |
                              "static" |
                              "_Thread_local" |
                              "auto" |
                              "register";

    type_specifier = struct |
                     union |
                     enum |
                     ("_Atomic" identifier) |
                     ("void" |
                      "char" |
                      "short" |
                      "int" |
                      "long" |
                      "float" |
                      "double" |
                      "signed" |
                      "unsigned" |
                      "_Bool" |
                      "_Complex") |
                     typedef;

    struct = structure:'struct' identifier:identifier;

    union = union:'union' identifier:identifier;

    enum = enum:"enum" identifier;

    typedef = typedef:identifier;

    interface_declaration = interface:interface;

    interface = pointer:{pointer}* '%' category:identifier '.' identifier:identifier '%';

    declarator = pointer:{pointer}* declarator:direct_declarator;

    pointer = @:pointer_sign {type_qualifier}*;

    direct_declarator = array_declarator |
                        primary_declarator;

    primary_declarator = brackets | name_identifier;

    brackets = '(' @:declarator ')';

    array_declarator = declarator:primary_declarator array:('[' pointer ']' |
                                                 '[' {type_qualifier}* ']');

    pointer_sign = pointer:'*';

    name_identifier = identifier | "%s";

    identifier = /\w+/;

    undefined_declaration = undefined:"$";
    """
    declarations_model = None

    def __init__(self, expression, ast=None):
        # todo: this is ugly but changing it will cause huge refactroing of the other EMG modules
        self.expression = expression
        self.type_class = None
        self.pointer = 0
        self.array = False
        self.return_value = None
        self.interface = None
        self.function_name = None
        self.parameters = None
        self.structure_name = None
        self.fields = None
        self.varaible_params = False

        if ast:
            self._ast = ast
        elif not self.declarations_model:
            import grako
            self.declarations_model = grako.genmodel('signature', self.declarations_grammar)
            self._ast = self.declarations_model.parse(self.expression, ignorecase=True)

        # todo: semantics is too simplified but its changing will cause huge refactoring
        # better solution is hide all properties like pointer, return_value and ets. from users and develop
        # additional methods for particular use (like determine is the signature can be used as a callback)
        if "return_value" in self._ast:
            # parse function
            self.type_class = 'function'
            self.__parse_main_declarator(self._ast['main_declarator'])

            if self._ast['return_value'] == 'void':
                self._ast['return_value'] = None
            else:
                self.return_value = Signature(None, self._ast['return_value'])

            self.parameters = []
            if 'void' not in self._ast['parameters']:
                for p_ast in self._ast['parameters']:
                    if p_ast != '...':
                        self.parameters.append(Signature(None, p_ast))
                    else:
                        self.varaible_params = True
        elif "interface" in self._ast:
            # parse inteface
            self.type_class = 'interface'
            self.__parse_interface(self._ast['interface'])
        elif "undefined" in self._ast:
            # Parse undefined '$'
            self.type_class = 'primitive'
        elif "main_declarator" in self._ast:
            # Parse primitive
            self.type_class = 'primitive'
            self.__parse_main_declarator(self._ast['main_declarator'])
        else:
            raise NotImplementedError("Cannot parse signature: {}".format(self.expression))

    def __parse_main_declarator(self, ast):
        if 'pointer' in ast:
            self.pointer += len(ast['pointer'])
        if 'array' in ast:
            self.array = True
        if 'declarator' in ast:
            self.__parse_main_declarator(ast['declarator'])

    def __parse_interface(self, ast):
        self.interface = "{}.{}".format(ast['category'], ast['identifier'])

    def _construct_expression(self, identifier='%s'):
        if self.type_class == 'function':
            if self.return_value:
                declaration = self.return_value.declare('')
            else:
                declaration = 'void'

            declaration += self._construct_main_declarator(identifier)

            if len(self.parameters) == 0:
                declaration += '(void)'
            else:
                parameters = []
                for parameter in self.parameters:
                    if type(parameter) is str:
                        parameters.append(parameter)
                    else:
                        parameters.append(parameter.declare(''))

                declaration += "({})".format(', '.join(parameters))

        elif self.type_class == 'primitive':
            pass
        elif self.type_class == 'interface':
            return "%{}%".format(self.interface)
        elif self.type_class == 'undefined':
            return '$'

    def _construct_main_declarator(self, identifier):
        pass

    def get_string(self):
        return self.declare('%s')



strings = [
    "int __must_check %s request_percpu_irq($, *%irq.line%, void (*%s)(void (*%s)(void), ...), const char *%s, void __percpu *%s)",
    "*%usb.driver%",
    "int * (*%s) []",
    "int *(*%s)",
    "int %s",
    "int *%s",
    "static float %s",
    "int **%s",
    "struct usb_driver %s",
    "struct usb_driver * %s",
    "struct usb_driver * const %s",
    "static float (%s)",
    "int %s []",
    "int *%s []",
    "static float %s []",
    "struct usb_driver %s []",
    "struct usb_driver *%s []",
    "struct usb_driver * (* %s) []",
    "struct usb_driver (* %s) []",
    "struct usb_driver * const %s []",
    "struct usb_driver * const (*%s)[]",
    "struct usb_driver * const (*%s []) []",
    "$ func($)",
    "$ func($, $)",
    "void %s func($)",
    "void %s func(void %s, void %s)",
    "void func(void)",
    "void func(void %s)",
    "int %s func(void)",
    "int %s func(struct usb_driver *%s)",
    "int %s func(int %s, int %s)",
    "int %s func(int %s, int %s, ...)",
    "int %s (*%s)(int %s)",
    "int %s (*%s)(int %s, int %s)",
    "int %s (*%s)(int %s, ...)",
    "void (*%s)(void)",
    "int %s func(void (*%s)(void), ...)",
    "int %s func(int *%s, int %s (*%s)(int %s))",
    "int %s func(int *%s, void (*%s)(void *%s))",
    "int %s func(int *%s, void (*%s)(void))",
    "void (*%s)(void)",
    "void (*%s)(void (*%s)(void), ...)",
    "int %s func(...)",
    "void (*%s)(*%isb.usb_driver%)",
    "void (*%s)($, *%isb.usb_driver%)",
    "int %s func($, void (*%s)(*%isb.usb_driver%))",
    "int %s (*%s)(...)",
    "void (**%s)(struct nvme_dev *%s, void *%s, struct nvme_completion *%s)",
    "int %s func(int %s (*%s)(...))",
    "int %s func(int %s (*%s)(...), ...)",
    "int %s func(int %s (*%s)(int %s, ...))",
    "int %s func(int %s (*%s)(int %s, ...), ...)",
    "int %s (*%s)(int %s (*%s)(int %s, ...), ...)",
]
asts = []
for string in strings:
    print(string)
    s = Signature(string)
    print(s.get_string())
    asts.append(s)
a = 1

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
