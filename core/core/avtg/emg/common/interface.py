import ply.lex as lex
import ply.yacc as yacc
import json

tokens = (
    'TYPE_SPECIFIER',
    'STORAGE_CLASS_SPECIFIER',
    'TYPE_QUALIFIER',
    'FUNCTION_SPECIFIER',
    'ENUM',
    'STRUCT',
    'UNION',
    'STAR_SIGN',
    'SQUARE_BOPEN_SIGN',
    'SQUARE_BCLOSE_SIGN',
    'PARENTH_OPEN',
    'PARENTH_CLOSE',
    'COMMA',
    'DOTS',
    'NUMBER',
    'IDENTIFIER',
    'INTERFACE',
    'UNKNOWN'
)

t_TYPE_SPECIFIER = r'void|char|short|int|long|float|double|signed|unsigned|_Bool|_Complex'

t_STORAGE_CLASS_SPECIFIER = r'extern|static|_Thread_local|auto|register'

t_TYPE_QUALIFIER = r'const|restrict|volatile|_Atomic'

t_FUNCTION_SPECIFIER = r'inline|_Noreturn'

t_STRUCT = 'struct'

t_UNION = 'union'

t_ENUM = 'enum'

t_IDENTIFIER = r"\w+"

t_STAR_SIGN = r"\*"

t_SQUARE_BOPEN_SIGN = r"\["

t_SQUARE_BCLOSE_SIGN = r"\]"

t_PARENTH_OPEN = r"\("

t_PARENTH_CLOSE = r"\)"

t_COMMA = r","

t_DOTS = r"\.\.\."

t_UNKNOWN = r"\$"

t_ignore = ' \t'


def t_NUMBER(t):
    r'\d+'
    t.value = int(t.value)
    return t


def t_INTERFACE(t):
    r'%(\w+)\.(\w+)%'
    category, identifier = str(t.value[1:-1]).split('.')
    t.value = {
        "category": category,
        "identifier": identifier
    }
    return t


def t_error(t):
    raise TypeError("Unknown text '%s'" % (t.value,))


def p_declaration(p):
    """
    declaration : declaration_specifiers_list declarator
                | UNKNOWN declarator
                | INTERFACE declarator
                | UNKNOWN
                | INTERFACE
    """
    declaration_processing(p)


def p_declaration_specifiers_list(p):
    """
    declaration_specifiers_list : prefix_specifiers_list type_specifier suffix_specifiers_list
                                | prefix_specifiers_list type_specifier
                                | type_specifier suffix_specifiers_list
                                | type_specifier
    """
    p[0] = {}
    if len(p) == 2:
        p[0]['type specifier'] = p[1]
    elif len(p) == 3 and type(p[1]) is list:
        p[0]['type specifier'] = p[2]
        p[0]['specifiers'] = p[1]
    elif len(p) == 3 and type(p[1]) is dict:
        p[0]['type specifier'] = p[1]
        p[0]['specifiers'] = p[2]
    else:
        p[0]['type specifier'] = p[2]
        p[0]['specifiers'] = p[1] + p[3]


def p_prefix_specifiers_list(p):
    """
    prefix_specifiers_list : prefix_specifiers_option prefix_specifiers_list
                           | prefix_specifiers_option
    """
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = [p[1]] + list(p[2])


def p_prefix_specifiers_option(p):
    """
    prefix_specifiers_option : STORAGE_CLASS_SPECIFIER
                             | TYPE_QUALIFIER
                             | FUNCTION_SPECIFIER
    """
    p[0] = p[1]


def p_suffix_specifiers_list(p):
    """
    suffix_specifiers_list : suffix_specifiers_option suffix_specifiers_list
                           | suffix_specifiers_option
    """
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = [p[1]] + list(p[2])


def p_suffix_specifiers_option(p):
    """
    suffix_specifiers_option : STORAGE_CLASS_SPECIFIER
                             | TYPE_QUALIFIER
    """
    p[0] = p[1]


def p_declaration_specifier(p):
    """
    declaration_specifier : STORAGE_CLASS_SPECIFIER
                          | TYPE_QUALIFIER
                          | FUNCTION_SPECIFIER
    """
    p[0] = p[1]


def p_type_specifier(p):
    """
    type_specifier : TYPE_SPECIFIER
                   | struct_specifier
                   | union_specifier
                   | enum_specifier
                   | typedef
    """
    if type(p[1]) is str:
        p[0] = {
            'class': 'Primitive',
            'name': p[1]
        }
    else:
        p[0] = p[1]


def p_struct_specifier(p):
    """
    struct_specifier : STRUCT IDENTIFIER
    """
    p[0] = {
        'class': 'structure',
        'name': p[2]
    }


def p_union_specifier(p):
    """
    union_specifier : UNION IDENTIFIER
    """
    p[0] = {
        'class': 'union',
        'name': p[2]
    }


def p_enum_specifier(p):
    """
    enum_specifier : ENUM IDENTIFIER
    """
    p[0] = {
        'class': 'enum',
        'name': p[2]
    }


def p_typedef(p):
    """
    typedef : IDENTIFIER
    """
    p[0] = {
        'class': 'typedef',
        'name': p[1]
    }


def p_declarator(p):
    """
    declarator : pointer direct_declarator
               | direct_declarator
    """
    declarator_processing(p)


def p_pointer(p):
    """
    pointer : STAR_SIGN suffix_specifiers_list pointer
            | STAR_SIGN suffix_specifiers_list
            | STAR_SIGN pointer
            | STAR_SIGN
    """
    if len(p) == 2:
        p[0] = 1
    elif len(p) == 3 and type(p[2]) is int:
        p[0] = int(p[2]) + 1
    elif len(p) == 3 and type(p[2]) is list:
        p[0] = 1
    else:
        p[0] = int(p[3]) + 1


def p_direct_declarator(p):
    """
    direct_declarator : direct_declarator array_list
                      | direct_declarator PARENTH_OPEN function_parameters_list PARENTH_CLOSE
                      | PARENTH_OPEN declarator PARENTH_CLOSE
                      | IDENTIFIER
    """
    direct_declarator_processing(p)


def p_array_list(p):
    """
    array_list : array_expression array_list
               | array_expression
    """
    p[0] = []
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = [p[1]] + p[2]


def p_array_expression(p):
    """
    array_expression : SQUARE_BOPEN_SIGN array_size SQUARE_BCLOSE_SIGN
                     | SQUARE_BOPEN_SIGN SQUARE_BCLOSE_SIGN
    """
    if len(p) == 4:
        p[0] = p[2]
    else:
        p[0] = {"size": None}


def p_array_size(p):
    """
    array_size : suffix_specifiers_list STAR_SIGN
               | suffix_specifiers_list NUMBER
               | STAR_SIGN
               | NUMBER
    """
    if len(p) == 3 and type(p[2]) is str:
        p[0] = {"size": None}
    elif len(p) == 3 and type(p[2]) is int:
        p[0] = {"size": p[2]}
    elif len(p) == 2 and type(p[1]) is str:
        p[0] = {"size": None}
    else:
        p[0] = {"size": p[1]}


def p_function_parameters_list(p):
    """
    function_parameters_list : parameter_declaration COMMA function_parameters_list
                             | parameter_declaration
    """
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = [p[1]] + p[3]


def p_parameter_declaration(p):
    """
    parameter_declaration : declaration_specifiers_list declarator
                          | declaration_specifiers_list abstract_declarator
                          | UNKNOWN declarator
                          | INTERFACE declarator
                          | UNKNOWN abstract_declarator
                          | INTERFACE abstract_declarator
                          | declaration_specifiers_list
                          | UNKNOWN
                          | INTERFACE
                          | DOTS
    """
    declaration_processing(p)


def p_abstract_declarator(p):
    """
    abstract_declarator : pointer direct_abstract_declarator
                        | direct_abstract_declarator
                        | pointer
    """
    declarator_processing(p)


def p_direct_abstract_declarator(p):
    """
    direct_abstract_declarator : direct_abstract_declarator array_list
                               | direct_abstract_declarator PARENTH_OPEN function_parameters_list PARENTH_CLOSE
                               | PARENTH_OPEN abstract_declarator PARENTH_CLOSE
    """
    direct_declarator_processing(p)


def declaration_processing(p):
    """
    [parameter_]declaration : declaration_specifiers_list declarator
                            | declaration_specifiers_list abstract_declarator
                            | UNKNOWN declarator
                            | INTERFACE declarator
                            [| UNKNOWN abstract_declarator]
                            [| INTERFACE abstract_declarator]
                            [| declaration_specifiers_list]
                            | UNKNOWN
                            | INTERFACE
                            [| DOTS]
    """
    if len(p) == 3:
        p[0] = {
            'specifiers': p[1],
            'declarator': p[2]
        }
    elif type(p[1]) is list:
        p[0] = {
            'specifiers': p[1],
            'declarator': {'identifier': None}
        }
    else:
        p[0] = p[1]

    # Move return value types and declarators to separate attributes
    if 'declarator' in p[0]:
        separators = [index for index in range(len(p[0]['declarator']))
                      if 'function arguments' in p[0]['declarator'][index]]

        current_ast = p[0]
        while len(separators) > 0:
            separator = separators.pop()
            declarator = current_ast['declarator'][separator:]
            ret_declarator = current_ast['declarator'][0:separator]
            current_ast['declarator'] = declarator
            current_ast['return value type'] = {'declarator': ret_declarator}
            current_ast = current_ast['return value type']

        current_ast['specifiers'] = p[0]['specifiers']
        del p[0]['specifiers']


def declarator_processing(p):
    """
    [abstract_]declarator : pointer direct_[abstract_]declarator
                        | direct_[abstract_]declarator
                        [| pointer]
    """
    if len(p) == 2 and type(p[1]) is int:
        new = {
            'pointer': p[1],
            'identifier': None
        }
        p[0] = [new]
    elif len(p) == 2 and type(p[1]) is list:
        p[0] = p[1]
    else:
        p[0] = p[2]
        if 'pointer' in p[0][0] and ('arrays' in p[0][0] or 'function arguments' in p[0][0]):
            new = {'pointer': p[1]}
            p[0] = [new] + p[0]
        else:
            if 'pointer' in p[0][0]:
                p[0][0]['pointer'] = p[1] + p[0][0]['pointer']
            else:
                p[0][0]['pointer'] = p[1]


def direct_declarator_processing(p):
    """
    [abstract_]declarator : direct_[abstract_]declarator array_list
                          | direct_[abstract_]declarator PARENTH_OPEN function_parameters_list PARENTH_CLOSE
                          | PARENTH_OPEN [abstract_]declarator PARENTH_CLOSE
                          [| IDENTIFIER]
    """
    if len(p) == 2:
        p[0] = [
            {
                'identifier': p[1]
            }
        ]
    else:
        if 'size' in p[2][0] and 'pointer' not in p[1][0]:
            p[0] = p[1]
            p[0][0]['arrays'] = p[2]
        elif 'size' in p[2][0] and 'pointer' in p[1][0]:
            new = {'arrays': p[2]}
            p[0] = [new] + p[1]
        else:
            if len(p) == 5:
                p[0] = p[1]

                if len(p[3]) == 1 and type(p[3][0]) is dict and 'type specifier' in p[3][0] and \
                                p[3][0]['type specifier']['name'] == 'void' and 'declarator' not in p[3][0]:
                    p[0][0]['function arguments'] = []
                else:
                    p[0][0]['function arguments'] = p[3]
            else:
                p[0] = p[2]


lex.lex()
yacc.yacc(debug=0, write_tables=0)

tests = [
    'int a',
    'static int a',
    'static const int a',
    'static int const a',
    'int * a',
    'int ** a',
    'int * const a',
    'int * const * a',
    'int * const ** a',
    'int ** const ** a',
    'struct usb a',
    'const struct usb a',
    'const struct usb * a',
    'struct usb * const a',
    'union usb * const a',
    'enum usb * const a',
    'mytypedef * a',
    'int a []',
    'int a [1]',
    'int a [const 1]',
    'int a [*]',
    'int a [const *]',
    'int a [const *][1]',
    'int a [const *][1][]',
    'static struct usb ** a [const 1][2][*]',
    'int (a)',
    'int *(*a)',
    'int *(**a)',
    'int *(* const a [])',
    'int *(* const a) []',
    'int *(* const a []) [*]',
    'int *(*(a))',
    'int (*(*(a) [])) []',
    'int (*(*(*(a) []))) []',
    'int a(int)',
    'int a(int, int)',
    'int a(void)',
    'void a(void)',
    'void a(int, ...)',
    'void (*a) (int, ...)',
    "int func(int, void (*)(void))",
    "int func(void (*)(void), int)",
    "int func(int, int (*)(int))",
    "int func(int, void (*)(void *))",
    "int func(int *, void (*)(void))",
    "int func(int, int (*)(int))",
    "int func(int *, int (*)(int, int))",
    "int func(int *, int (*)(int, int), ...)",
    "int (*f)(int *)",
    "int (*f)(int *, int *)",
    "int func(struct nvme_dev *, void *)",
    "int (*f)(struct nvme_dev *, void *)",
    "void (**a)(struct nvme_dev *, void *)",
    "void (**a)",
    "void func(struct nvme_dev *, void *, struct nvme_completion *)",
    "void (**a)(void)",
    "void (**a)(struct nvme_dev * a)",
    "void (**a)(struct nvme_dev * a, int)",
    "void (**a)(struct nvme_dev * a, void * a)",
    "void (**a)(struct nvme_dev *, void *)",
    "void (**a)(struct nvme_dev *, void *, struct nvme_completion *)",
    "void (**a)(struct nvme_dev *, void *, int (*)(void))",
    "int func(int (*)(int))",
    "int func(int (*)(int *), ...)",
    "int func(int (*)(int, ...))",
    "int func(int (*)(int, ...), ...)",
    "int (*a)(int (*)(int, ...), ...)",
    'void (*((*a)(int, ...)) []) (void) []',
    '%usb.driver%',
    '$ my_function($, %usb.driver%, int)',
    '%usb.driver% function(int, void *)',
]

if True:
    string = 'void (*((*a)(int, ...)) []) (void) []'
    ast = yacc.parse(string, debug=False)
    ast["origin expression"] = string
    print(json.dumps(ast, indent=4, sort_keys=True))
else:
    for test in tests:
        print(test)
        ast = yacc.parse(test, debug=False)
        ast["origin expression"] = test
        print(json.dumps(ast, indent=4, sort_keys=True))
        a = 1


__declaration_model = None
__declaration_grammar = \
    """
    (* Declaration syntax based on Committee Draft — April 12, 2011 ISO/IEC 9899:201x but it is rather simplified *)

    signature = @:declaration $;

    declaration = function_declaration~ |
                  primitive_declaration~ |
                  interface_declaration~ |
                  undefined_declaration;

    function_declaration = return_value:declaration main_declarator:declarator '(' parameters+:(parameter_list | void) ')' ~ |
                           return_value:void main_declarator:declarator '(' parameters+:(parameter_list | void) ')';

    primitive_declaration = specifiers:{declaration_specifiers}* main_declarator:declarator;

    parameter_list = @:{ [','] @:(function_declaration~ | primitive_declaration~ | interface_declaration~ | undefined_declaration~ | '...') }+;

    declaration_specifiers = storage_class_specifier:storage_class_specifier |
                             type_qualifier:type_qualifier |
                             function_specifier:function_specifier |
                             type_specifier:type_specifier;

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

    name_identifier = [identifier | "%s"];

    identifier = /\w+/;

    undefined_declaration = undefined:"$";
    """


def extract_identifier(string):
    if '%' not in string:
        string = "%{}%".format(string)

    intf = import_signature()

    # todo: extract
    category = None
    identifier = None

    if category and identifier:
        return category, identifier
    else:
        raise ValueError("Given string {} is not an identifier".format(string))


def import_signature(signature, ast=None):
    if not ast:
        __check_grammar()

        try:
            ast = __declaration_model.parse(signature, ignorecase=True)
        except:
            raise ValueError("Cannot parse signature: {}".format(signature))

    if "return_value" in ast:
        return Function(ast)
    elif "interface" in ast:
        return InterfaceReference(ast)
    elif "undefined" in ast:
        return UndefinedReference(ast)
    elif 'specifiers' in ast and 'main_declarator' in ast:
        for specifier in ast['specifiers']:
            if 'type_specifier' in specifier and specifier['type_specifier'] and \
                            'structure' in specifier['type_specifier']:
                return Structure(ast)

        return Primitive(ast)
    else:
        # todo: do we need arrays, enums, unions as an additional class? (issue #6559)
        raise NotImplementedError("Cannot parse signature: {}".format(signature))


def __check_grammar():
    global __declaration_model
    global __declaration_grammar

    if not __declaration_model:
        grako = __import__('grako')
        __declaration_model = grako.genmodel('signature', __declaration_grammar)


class __BaseType:

    def pointer_alias(self, alias):
        if type(self) is type(alias):
            self_pointer = self.to_string(None, True)
            alias_pointer = alias.to_string(None, True)
            self_str = self.to_string()
            alias_str = alias.to_string()

            if self_pointer == alias_str or alias_pointer == self_str:
                return True
        return False

    def add_pointer_implementations(self, alias):
        if self.pointer_alias(alias):
            for implementation in alias.implementations:
                if '&' in implementation.value:
                    implementation.value = implementation.value.split('& ')[-1]
                else:
                    implementation.value = '*({})'.format(implementation.value)

                self.add_implementation(implementation)
        else:
            raise ValueError("Can add implementations only from alias")

    def add_implementation(self, value, path, root_type, root_value, root_sequence):
        if not self.implementations:
            self.implementations = {}

        new = Implementation(value, path, root_type, root_value, root_sequence)
        if new.identifier not in self.implementations:
            self.implementations[new.identifier] = new

    def _main_declarator_constructor(self, replacement=None, pointer=False):
        dl = self.__extract_general_declarator()
        if not replacement:
            replacement = ''

        if pointer and len(dl) > 0:
            dl[0]['pointer'] += 1

        # Generate final expression
        string = ''
        for element in dl:
            if element['terminal']:
                string = str(replacement)
            elif string != '':
                string = '(' + string + ')'

            if element['array']:
                string += ' ' + '[]' * int(element['array'])
            if element['pointer']:
                string = '*' * int(element['pointer']) + ' ' + string
        return string

    @property
    def identifier(self):
        if not self._identifier:
            self._identifier = self.to_string()
        return self._identifier

    def __extract_general_declarator(self):
        if 'main_declarator' in self._ast:
            ast = self._ast['main_declarator']
        else:
            return []

        declarators = []
        to_process = [ast]

        # Unwrap recursion
        while len(to_process) > 0:
            declarator = to_process.pop()
            result = {
                'terminal': False,
                'array': 0,
                'pointer': 0
            }

            if type(declarator) is str:
                result['terminal'] = True
            if 'declarator' in declarator and declarator['declarator']:
                to_process.append(declarator['declarator'])
            if 'array' in declarator and declarator['array']:
                result['array'] = len(declarator['array'])
            if 'pointer' in declarator and declarator['pointer']:
                result['pointer'] = len(declarator['pointer'])

            declarators.append(result)

        # Remove unnecessary brackets
        final_elements = []
        for element in reversed(declarators):
            if element['terminal']:
                final_elements.append(element)
            elif len(final_elements) > 0:
                if not element['array']:
                    final_elements[-1]['pointer'] += element['pointer']
                elif element['array'] and not final_elements[-1]['pointer']:
                    final_elements[-1]['array'] += element['array']
                    final_elements[-1]['pointer'] += element['pointer']
                else:
                    final_elements.append(element)
        return final_elements

    @property
    def simple_declarator(self):
        gd = self.__extract_general_declarator()

        if len(gd) == 1 and gd[0]['pointer'] <= 1 and gd[0]['array'] == 0:
            return True
        else:
            return False


class Primitive(__BaseType):

    def __init__(self, ast):
        self._ast = ast
        self._identifier = None
        self.implementations = []
        self.path = None

    def to_string(self, replacement=None, pointer=False):
        mc = self._main_declarator_constructor(replacement, pointer)

        type_specifiers = []
        for specifier in reversed([sp['type_specifier'] for sp in self._ast['specifiers'] if sp['type_specifier']]):
            if 'structure' in specifier and specifier['structure']:
                type_specifiers.append("struct {}".format(specifier['identifier']))
            elif 'union' in specifier and specifier['union']:
                type_specifiers.append("union {}".format(specifier['identifier']))
            elif 'enum' in specifier and specifier['enum']:
                type_specifiers.append("enum {}".format(specifier['identifier']))
            elif 'typedef' in specifier and specifier['typedef']:
                type_specifiers.append(str(specifier['typedef']))
            else:
                type_specifiers.append(str(specifier))

        return "{} {}".format(' '.join(type_specifiers), mc)


class Function(__BaseType):

    def __init__(self, ast):
        self._ast = ast
        self._identifier = None
        self.implementations = []
        self.path = None
        self.return_value = None
        self.parameters = []

        if ast['return_value'] == 'void':
            self.return_value = None
        else:
            self.return_value = import_signature(None, ast['return_value'])

        if len(ast['parameters']) != 0:
            list = ast['parameters'][0]
            # The last element is Closure object
            for p_ast in list[:-1]:
                if p_ast != '...':
                    self.parameters.append(import_signature(None, p_ast))
                else:
                    self.varaible_params = True

    @property
    def suits_for_callback(self):
        if self.simple_declarator:
            return True
        else:
            return False

    def to_string(self, replacement=None, pointer=False):
        if self.return_value:
            ret_expr = self.return_value.to_string()
        else:
            ret_expr = 'void'

        parameters = []
        if len(parameters) > 0:
            for param in self.parameters:
                if type(param) is str:
                    parameters.append(param)
                else:
                    parameters.append(param.to_string())
            parameters = ', '.join(parameters)
        else:
            parameters = 'void'

        declarator = self._main_declarator_constructor(replacement, pointer)

        string = "{} ({})({})".format(ret_expr, declarator, parameters)

        return string


class Structure(__BaseType):

    def __init__(self, ast):
        self._ast = ast
        self._identifier = None
        self.implementations = []
        self.path = None
        self.structure = None
        self.fields = {}

        for specifier in [sp['type_specifier'] for sp in self._ast['specifiers'] if sp['type_specifier']]:
            if 'structure' in specifier and specifier['structure']:
                self.structure = specifier['identifier']
        if not self.structure:
            raise RuntimeError("Cannot extract structure name")

    @property
    def suits_for_contatiner(self):
        if self.simple_declarator:
            # todo: support arrays (issue #6559)
            return True
        else:
            return False

    def to_string(self, replacement=None, pointer=False):
        mc = self._main_declarator_constructor(replacement, pointer)

        return "struct {} {}".format(self.structure, mc)


class InterfaceReference(__BaseType):

    def __init__(self, ast):
        self._ast = ast
        self._identifier = None
        self.category = self._ast['interface']['category']
        self.short_identifier = self._ast['interface']['identifier']
        self.interface = "{}.{}".format(self.category, self.short_identifier)

    def _pointer_prefix(self):
        if 'pointer' in self._ast:
            if len(self._ast['pointer']) == 0:
                return ''
            else:
                return '*' * len(self._ast['pointer'])
        else:
            raise ValueError("Expect ast with 'pointer' node")

    def to_string(self):
        return "{}%{}%".format(self._pointer_prefix(), self._interface)


class UndefinedReference(__BaseType):

    def __init__(self, ast):
        self._ast = ast

    @property
    def _identifier(self):
        raise NotImplementedError("UndefinedReference cannot have identifier")

    def to_string(self, replacement=None, pointer=False):
        return '$'


class Implementation:

    def __init__(self, value, file, base_container=None, base_value=None, sequence=None):
        self.base_container = base_container
        self.base_value = base_value
        self.value = value
        self.file = file
        self.sequence = sequence
        self.identifier = str([value, file, base_value])


class Interface:

    def __init__(self, category, identifier):
        self.category = category
        self.short_identifier = identifier
        self.identifier = "{}.{}".format(category, identifier)
        self.declaration = None
        self.header = None
        self.implemented_in_kernel = False
        self.resource = False
        self.callback = False
        self.container = False
        self.field_interfaces = {}
        self.param_interfaces = []
        self.rv_interface = False

    def import_declaration(self, signature):
        if type(signature) is str:
            signature = import_signature(signature)

        if type(signature) is UndefinedReference or \
             type(signature) is InterfaceReference:
            raise TypeError("Cannot assign undefined referene or interface reference to the interface")

        self.declaration = signature

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
