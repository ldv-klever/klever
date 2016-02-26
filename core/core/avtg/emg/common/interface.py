import re

__fi_regex = None
__fi_extract = None
__declaration_model = None
__declaration_grammar = \
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

def __is_full_identifier(string):
    global __fi_regex
    global __fi_extract

    if not __fi_regex or not __fi_extract:
        __fi_regex = re.compile("(\w*)\.(\w*)")
        __fi_extract = re.compile("\*?%((?:\w*\.)?\w*)%")

    if __fi_regex.fullmatch(string) and len(__fi_regex.fullmatch(string).groups()) == 2:
        return True
    else:
        return False


def extract_full_identifier(string):
    global __fi_regex

    if __is_full_identifier(string):
        category, short_identifier = __fi_regex.fullmatch(string).groups()

        return category, "{}.{}".format(category, short_identifier)
    else:
        raise ValueError("Given string {} is not an identifier".format(string))


def yield_basetype(signature):
    global __declaration_model
    global __declaration_grammar

    if not __declaration_model:
        grako = __import__('grako')
        __declaration_model = grako.genmodel('signature', __declaration_grammar)

    ast = __declaration_model.parse(signature, ignorecase=True)
    if "return_value" in ast:
        return Function(ast)
    elif "interface" in ast:
        return InterfaceReference(ast)
    elif "undefined" in ast:
        return UndefinedReference(ast)
    elif None in ast:
        return Structure(ast)
    elif "main_declarator" in ast:
        return Primitive(ast)
    else:
        raise NotImplementedError("Cannot parse signature: {}".format(signature))


class __BaseType:

    def __init__(self, signature, ast):
        self._signature = signature
        self.implementations = []
        self.path = None

    def pointer_alias(self, value):
        raise NotImplementedError

    def add_pointer_implementations(self):
        raise NotImplementedError

    def add_implementation(self):
        raise NotImplementedError


class Primitive(__BaseType):

    def __init__(self, ast):
        self.__ast = ast


class Function(__BaseType):

    def __init__(self, ast):
        self.parameters = []
        self.return_value = None
        self.call = []

        # parse function
        self.type_class = 'function'
        self.__parse_main_declarator(ast['main_declarator'])

        if ast['return_value'] == 'void':
            ast['return_value'] = None
        else:
            self.return_value = Signature(None, ast['return_value'])

        self.parameters = []
        if 'void' not in ast['parameters']:
            for p_ast in ast['parameters']:
                if p_ast != '...':
                    self.parameters.append(Signature(None, p_ast))
                else:
                    self.varaible_params = True

    @property
    def suits_for_callback(self):
        raise NotImplementedError


class Structure(__BaseType):

    def __init__(self, ast):
        self.structure_name = None


class Array(__BaseType):

    def __init__(self, ast):
        self.element = None

class InterfaceReference(__BaseType):
    pass

class UndefinedReference(__BaseType):
    pass


class Implementation:

    def __init__(self, value, file, base_container_id=None, base_container_value=None):
        self.base_container = base_container_id
        self.base_value = base_container_value
        self.value = value
        self.file = file


class Interface:

    def __init__(self, category, identifier):
        self.category = category
        self.identifier = identifier
        self.declaration = None
        self.header = None
        self.implemented_in_kernel = False
        self.resource = False
        self.callback = False
        self.container = False
        self.field_interfaces = {}
        self.param_interfaces = []
        self.rv_interface = False

    def import_signature(self, signature):
        raise NotImplementedError

#    @property
#    def full_identifier(self, full_identifier=None):
#        if not self.category and not full_identifier:
#            raise ValueError("Cannot determine full identifier {} without interface category")
#        elif full_identifier:
#            category, identifier = extract_full_identifier(full_identifier)
#            self.category = category
#            self.identifier = identifier
#        else:
#            return "{}.{}".format(self.category, self.identifier)

#class Signature:
#
#    def __init__(self, basetype):
#        if type(basetype) is str:
#            self.basetype = BaseType(basetype)
#        elif type(basetype) is BaseType:
#            self.basetype = basetype
#        else:
#            raise NotImplementedError("Signature require type declaration or BaseType object")


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
