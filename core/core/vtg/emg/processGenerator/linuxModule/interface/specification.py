#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from core.vtg.emg.processGenerator.linuxModule.interface import StructureContainer, ArrayContainer, Resource, Callback,\
    FunctionInterface
from core.vtg.emg.common.c.types import Structure, Array, import_declaration, reduce_level, parse_declaration


def import_interface_specification(collection, sa, specification):
    def get_clean_declaration(c, desc, i):
        if "declaration" in desc:
            decl = import_declaration(desc["declaration"])
        else:
            raise ValueError(
                "Provide declaration at the interface specification of '{}.{}'".format(c, i))
        return decl

    for category in specification["categories"]:
        collection.logger.debug("Found interface category {}".format(category))
        description = specification["categories"][category]

        # Import interfaces
        if "containers" in description:
            for identifier in description['containers'].keys():
                declaration = get_clean_declaration(category, description['containers'][identifier], identifier)
                if isinstance(declaration, Structure):
                    intf = StructureContainer(category, identifier)
                elif isinstance(declaration, Array):
                    intf = ArrayContainer(category, identifier)
                else:
                    raise ValueError("Container '{}.{}' should be either a structure or array"
                                     .format(category, identifier))
                intf.declaration = declaration
                __import_interfaces(collection, intf, description["containers"][identifier])
        if "resources" in description:
            for identifier in description['resources'].keys():
                declaration = get_clean_declaration(category, description['resources'][identifier], identifier)
                intf = Resource(category, identifier)
                intf.declaration = declaration
                __import_interfaces(collection, intf, description["resources"][identifier])
        if "callbacks" in description:
            for identifier in description['callbacks'].keys():
                intf = Callback(category, identifier)
                if "declaration" in description['callbacks'][identifier]:
                    d, _ = import_interface_declaration(collection, intf,
                                                        description['callbacks'][identifier]["declaration"])
                    intf.declaration = d
                else:
                    raise ValueError("Provide declaration at the interface specification of '{}.{}'".
                                     format(category, identifier))

        if "containers" in description:
            for identifier in description['containers'].keys():
                fi = "{}.{}".format(category, identifier)
                intf = collection.get_intf(fi)
                # Import field interfaces
                if "fields" in description['containers'][identifier]:
                    for field in description['containers'][identifier]["fields"].keys():
                        declaration, relevant_intf = \
                            import_interface_declaration(collection, None,
                                                         description['containers'][identifier]["fields"][field])
                        intf.field_interfaces[field] = relevant_intf
                        intf.declaration.fields[field] = declaration
                if 'element' in description['containers'][identifier]:
                    declaration, relevant_intf = \
                        import_interface_declaration(collection, None,
                                                     description['containers'][identifier]["element"])
                    intf.element = relevant_intf
                    intf.declaration.element = declaration

    if "functions models" in specification:
        collection.logger.info("Import functions description")
        category = 'kernel functions'
        for identifier in (i for i in specification["functions"].keys() if i in sa.source_functions):
            if "declaration" not in specification["functions"][identifier]:
                raise TypeError("Specify 'signature' for function {} at {}".format(identifier, category))
            elif "header" not in specification[category][identifier] and \
                    "headers" not in specification[category][identifier]:
                raise TypeError("Specify 'header' for kernel interface {} at {}".format(identifier, category))
            interface = FunctionInterface(category, identifier)
            if "declaration" in specification["functions"][identifier]:
                d, _ = import_interface_declaration(collection, interface,
                                                    specification["functions"][identifier]["declaration"])
                interface.declaration = d
            else:
                raise ValueError("Provide declaration of function {!r}".format(identifier))


def import_interface_declaration(collection, interface, declaration):
    def check_ast(given_ast, declarator, iint):
        if 'specifiers' in given_ast and 'category' in given_ast['specifiers'] and \
                'identifier' in given_ast['specifiers']:
            n = given_ast['specifiers']['identifier']
            category = given_ast['specifiers']['category']
            i = collection.get_intf("{}.{}".format(category, n))
            d = i.declaration.to_string(declarator)
            return d, i
        else:
            if len(given_ast['declarator']) == 1 and \
                    ('pointer' not in given_ast['declarator'][-1] or given_ast['declarator'][-1]['pointer'] == 0) and \
                    ('arrays' not in given_ast['declarator'][-1] or len(given_ast['declarator'][-1]['arrays']) == 0):
                if 'specifiers' not in given_ast:
                    parameters = []
                    parameter_declarations = []
                    for index, p in enumerate(given_ast['declarator'][0]['function arguments']):
                        if isinstance(p, str):
                            parameter_declarations.append(p)
                        else:
                            expr, i = check_ast(p, '', None)
                            if iint and i:
                                iint.set_param_interface(index, i)
                            parameter_declarations.append(expr)

                    if len(parameters) == 0:
                        declarator += '(void)'
                    else:
                        declarator += '(' + ', '.join(parameter_declarations) + ')'

                    if 'specifiers' in given_ast['return value type'] and \
                            'type specifier' in given_ast['return value type']['specifiers'] and \
                            given_ast['return value type']['specifiers']['type specifier']['class'] == 'Primitive' and \
                            given_ast['return value type']['specifiers']['type specifier']['name'] == 'void':
                        declarator = 'void {}'.format(declarator)
                    else:
                        declarator, i = check_ast(given_ast['return value type'], declarator, None)
                        if iint and i:
                            iint.rv_interface = i

                    return declarator, None

            elif 'arrays' in given_ast['declarator'][-1] and len(given_ast['declarator'][-1]['arrays']) > 0:
                array = given_ast['declarator'][-1]['arrays'].pop()
                size = array['size']
                given_ast = reduce_level(given_ast)
                if not size:
                    size = ''
                declarator += '[{}]'.format(size)
                return check_ast(given_ast, declarator, iint)
            elif 'pointer' not in given_ast['declarator'][-1] or given_ast['declarator'][-1]['pointer'] > 0:
                given_ast['declarator'][-1]['pointer'] -= 1
                given_ast = reduce_level(given_ast)
                declarator = '*' + declarator
                return check_ast(given_ast, declarator, iint)
            else:
                raise NotImplementedError

    # todo: Check which exceptions can be thrown here
    try:
        clean = import_declaration(declaration)
        return clean, None
    except Exception:
        try:
            ast = parse_declaration(declaration)
        except Exception:
            raise ValueError("Cannot parse declaration: {}".format(declaration))

        obj, intf = check_ast(ast, 'a', interface)
        # Reimport to get proper object
        declaration = import_declaration(obj)
        return declaration, intf


def __import_interfaces(collection, interface, description):
    exist = collection.get_intf(interface.identifier)
    if not exist:
        collection.set_intf(interface)
    else:
        raise ValueError('Interface {!r} is described twice'.format(interface.identifier))

    if "header" in description:
        interface.header = [description["header"]]

    if "interrupt context" in description and description["interrupt context"]:
        interface.interrupt_context = True

    return interface
