import grako

signature_grammar1 = \
"""
(* Declaration syntax based on Committee Draft — April 12, 2011 ISO/IEC 9899:201x but it is simplified*)

signature = @:declaration $;

declaration = function_declaration |
              primitive_declaration |
              interface_declaration |
              undefined_declaration;

function_declaration = return_value:(declaration | {void_specifiers}+) main_declarator:declarator '(' parameters+:parameter_list ')';

primitive_declaration = specifiers:{declaration_specifiers}+ main_declarator:declarator;

parameter_list = (@+:declaration {',' (@+:declaration | '...')}*) | "void";

declaration_specifiers = storage_class_specifier |
                         type_qualifier |
                         function_specifier |
                         type_specifier;

void_specifiers = "void" |
                  storage_class_specifier |
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

interface_declaration = interface;

interface = pointer:{pointer}* '%' identifier '.' identifier '%';

declarator = pointer:{pointer}* declarator:direct_declarator;

pointer = @:pointer_sign {type_qualifier}*;

direct_declarator = array_declarator |
                    primary_declarator;

primary_declarator = brackets | name_identifier;

brackets = '(' @:declarator ')';

array_declarator = array:primary_declarator ('[' {type_qualifier}* '*' ']' |
                                       '[' {type_qualifier}* ']');

pointer_sign = pointer:'*';

name_identifier = identifier | "%s";

identifier = /\w+/;

undefined_declaration = "$";
"""

process_model = grako.genmodel('signature', signature_grammar1)

strings = [
    "int %s",
    "int *%s",
    "static float %s",
    "int **%s",
    "struct usb_driver %s",
    "struct usb_driver * %s",
    "struct usb_driver * const %s",
    "static float (%s)",
    "int *(*%s)",
    "int %s []",
    "int *%s []",
    "static float %s []",
    "int * (*%s) []",
    "struct usb_driver %s []",
    "struct usb_driver *%s []",
    "struct usb_driver * (* %s) []",
    "struct usb_driver (* %s) []",
    "struct usb_driver * const %s []",
    "struct usb_driver * const (*%s)[]",
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
    "int %s func(int *%s, void (*%s)(void))",
    "int %s func(int %s (*%s)(int %s, ...), ...)",
    "int %s (*%s)(int %s (*%s)(int %s, ...), ...)",
    "void (*%s)(void)",
    "void (*%s)(void (*%s)(void), ...)"
]
asts = []
for string in strings:
    print(string)
    ast = process_model.parse(string, ignorecase=True)
    print(ast)
    asts.append(ast)
a = 1

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
