#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
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

import copy

from klever.core.vtg.emg.generators.linuxModule.interface import StructureContainer, ArrayContainer, Resource, Callback,\
    FunctionInterface
from klever.core.vtg.emg.common.c.types import Structure, Array, import_declaration, reduce_level, parse_declaration


def import_interface_specification(logger, collection, sa, specification):
    def get_clean_declaration(c, desc, i):
        if "declaration" in desc:
            decl = import_declaration(desc["declaration"])
        else:
            raise ValueError("Provide declaration at the interface specification of '{}.{}'".format(c, i))
        return decl

    logger.debug("Found interface categories: {}".format(', '.join(specification["categories"].keys())))
    for category in specification["categories"]:
        description = specification["categories"][category]

        # Import interfaces
        # First, import  containers
        for identifier in description.get('containers', {}):
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

        # Then resources
        for identifier in description.get('resources', {}):
            declaration = get_clean_declaration(category, description['resources'][identifier], identifier)
            intf = Resource(category, identifier)
            intf.declaration = declaration
            __import_interfaces(collection, intf, description["resources"][identifier])

        # Now callbacks that can refer to resources and containers
        for identifier in description.get('callbacks', {}):
            intf = Callback(category, identifier)
            if "declaration" in description['callbacks'][identifier]:
                d, _ = import_interface_declaration(collection, intf,
                                                    description['callbacks'][identifier]["declaration"])
                intf.declaration = d
            else:
                raise ValueError("Provide declaration at the interface specification of '{}.{}'".
                                 format(category, identifier))
            __import_interfaces(collection, intf, description["callbacks"][identifier])

        for identifier in description.get('containers', {}):
            fi = "{}.{}".format(category, identifier)
            intf = collection.get_intf(fi)

            # Import field interfaces
            for field in description['containers'][identifier].get("fields", {}):
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

    logger.info("Import functions description")
    category = 'functions models'
    for identifier in (i for i in specification.get("functions models", {}) if i in sa.source_functions):
        if "declaration" not in specification["functions models"][identifier]:
            raise TypeError("Specify 'signature' for function {!r} at {!r}".format(identifier, category))
        if "header" not in specification[category][identifier] and \
                "headers" not in specification[category][identifier]:
            raise TypeError("Specify 'header' for kernel interface {!r} at {!r}".format(identifier, category))
        interface = FunctionInterface(category, identifier)
        if "declaration" in specification["functions models"][identifier]:
            d, _ = import_interface_declaration(collection, interface,
                                                specification["functions models"][identifier]["declaration"])
            interface.declaration = d
        else:
            raise ValueError("Provide declaration of function {!r}".format(identifier))
        __import_interfaces(collection, interface, specification[category][identifier])


def import_interface_declaration(collection, interface, declaration):
    def check_array(given_ast):
        return 'arrays' in given_ast['declarator'][-1] and len(given_ast['declarator'][-1]['arrays']) > 0

    def check_function(given_ast):
        return len(given_ast['declarator']) == 1 and \
            ('pointer' not in given_ast['declarator'][-1] or given_ast['declarator'][-1]['pointer'] == 0) and \
            ('arrays' not in given_ast['declarator'][-1] or len(given_ast['declarator'][-1]['arrays']) == 0)

    def check_ast(given_ast, declarator, iint):
        try:
            probe_ast = copy.deepcopy(given_ast)
            cl = import_declaration(None, probe_ast)
            expr = cl.to_string(declarator)
            return expr, None
        except KeyError as e:
            if 'specifiers' in given_ast and 'category' in given_ast['specifiers'] and \
                    'identifier' in given_ast['specifiers']:
                n = given_ast['specifiers']['identifier']
                category = given_ast['specifiers']['category']
                i = collection.get_intf("{}.{}".format(category, n))
                if 'pointer' in given_ast['specifiers'] and given_ast['specifiers']['pointer']:
                    d = i.declaration.take_pointer.to_string(declarator)
                else:
                    d = i.declaration.to_string(declarator)
                return d, i

            if check_function(given_ast) and 'specifiers' not in given_ast:
                parameter_declarations = []
                for index, p in enumerate(given_ast['declarator'][0]['function arguments']):
                    if isinstance(p, str):
                        parameter_declarations.append(p)
                    else:
                        expr, i = check_ast(p, 'a', None)
                        if iint and i:
                            iint.set_param_interface(index, i)
                        parameter_declarations.append(expr)

                if len(parameter_declarations) == 0:
                    declarator += '(void)'
                else:
                    declarator += '(' + ', '.join(parameter_declarations) + ')'

                declarator, i = check_ast(given_ast['return value type'], declarator, None)
                if iint and i:
                    iint.rv_interface = i

                return declarator, None

            if check_array(given_ast):
                array = given_ast['declarator'][-1]['arrays'].pop()
                size = array['size']
                given_ast = reduce_level(given_ast)
                if not size:
                    size = ''
                declarator += '[{}]'.format(size)
                return check_ast(given_ast, declarator, iint)
            if 'pointer' in given_ast['declarator'][-1] and given_ast['declarator'][-1]['pointer'] > 0:
                given_ast['declarator'][-1]['pointer'] -= 1
                given_ast = reduce_level(given_ast)
                if check_array(given_ast) or check_function(given_ast):
                    declarator = '(*' + declarator + ')'
                else:
                    declarator = '*' + declarator
                return check_ast(given_ast, declarator, iint)

            raise NotImplementedError from e

    try:
        clean = import_declaration(declaration)
        return clean, None
    except KeyError:
        try:
            ast = parse_declaration(declaration)
            obj, intf = check_ast(ast, 'a', interface)
            # Reimport to get proper object
            declaration = import_declaration(obj)
        except Exception as e:
            raise ValueError("Cannot parse declaration: {!r}".format(declaration)) from e

        return declaration, intf


def __import_interfaces(collection, interface, description):
    exist = collection.get_intf(str(interface))
    if not exist:
        collection.set_intf(interface)
    else:
        raise ValueError('Interface {!r} is described twice'.format(str(interface)))

    interface.header = [description["header"]] if description.get("header") else []
    interface.interrupt_context = description.get("interrupt context", False)

    return interface
