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
from core.vtg.emg.common.interface import SourceFunction
from core.vtg.emg.common.signature import Structure, Union, Array, import_declaration, import_typedefs, extract_name, \
    check_null, is_static
from core.vtg.emg.interfacespec.tarjan import calculate_load_order


def import_code_analysis(collection, avt, analysis):
    """
    Perform main routin with import of interface categories specification and then results of source analysis.
    After that object contains only relevant to environment generation interfaces and their implementations.

    :param collection: InterfaceCategoriesSpecification object.
    :param avt: Abstract verification task dictionary.
    :param analysis: Dictionary with content of source analysis.
    :return: None.
    """
    # Import typedefs if there are provided
    if analysis and 'typedefs' in analysis:
        import_typedefs(analysis['typedefs'])

    collection.logger.info("Import modules init and exit functions")
    __import_inits_exits(collection, analysis, avt)

    collection.logger.info("Extract complete types definitions")
    __extract_types(collection, analysis)


def __import_inits_exits(collection, analysis, avt):
    collection.logger.debug("Move module initilizations functions to the modules interface specification")
    deps = {}
    for module, dep in avt['deps'].items():
        deps[module] = list(sorted(dep))
    order = calculate_load_order(collection.logger, deps)
    order_c_files = []
    for module in order:
        for module2 in avt['grps']:
            if module2['id'] != module:
                continue
            order_c_files.extend([file['in file'] for file in module2['cc extra full desc files']])
    if "init" in analysis:
        for module in (m for m in order_c_files if m in analysis["init"]):
            collection.add_init(module, analysis['init'][module])
    if len(collection.inits) == 0:
        raise ValueError('There is no module initialization function provided')

    collection.logger.debug("Move module exit functions to the modules interface specification")
    if "exit" in analysis:
        for module in (m for m in reversed(order_c_files) if m in analysis['exit']):
            collection.add_exit(module, analysis['exit'][module])
    if len(collection.exits) == 0:
        collection.logger.warning('There is no module exit function provided')


def __extract_types(collection, analysis):
    entities = []
    # todo: this section below is slow enough
    if 'global variable initializations' in analysis:
        collection.logger.info("Import types from global variables initializations")
        for variable in sorted(analysis["global variable initializations"],
                               key=lambda var: str(var['declaration'])):
            variable_name = extract_name(variable['declaration'])
            if not variable_name:
                raise ValueError('Global variable without a name')

            signature = import_declaration(variable['declaration'])
            if type(signature) is Structure or type(signature) is Array or type(signature) is Union:
                entity = {
                    "path": variable['path'],
                    "description": variable,
                    "root value": variable_name,
                    "root type": None,
                    "root sequence": [],
                    "type": signature
                }
                signature.add_implementation(
                    variable_name,
                    variable['path'],
                    None,
                    None,
                    [],
                    is_static(variable['declaration'])
                )
                entities.append(entity)

            if variable_name not in collection._global_variables:
                collection._global_variables[variable_name] = dict()
            collection._global_variables[variable_name][variable['path']] = \
                {'declaration': signature, 'original declaration': variable['declaration']}
        __import_entities(collection, analysis, entities)

    if 'kernel functions' in analysis:
        collection.logger.info("Import types from kernel functions")
        for func in sorted(analysis['kernel functions'].keys()):
            collection.logger.debug("Parse signature of function {}".format(func))
            declaration = import_declaration(analysis['kernel functions'][func]['signature'])

            if func in collection.kernel_functions:
                collection.get_kernel_function(func).update_declaration(declaration)
            else:
                new_intf = SourceFunction(func, analysis['kernel functions'][func]['header'])
                new_intf.declaration = declaration
                collection.set_kernel_function(new_intf)

            collection.get_kernel_function(func).files_called_at. \
                update(set(analysis['kernel functions'][func]["called at"]))

    # Remove dirty declarations
    collection.refine_interfaces()

    # Import modules functions
    modules_functions = {}
    # todo: refactoring of this is required. I would propse to introduce to use SourceFunction for these functions.
    if 'modules functions' in analysis:
        collection.logger.info("Import modules functions and implementations from kernel functions calls in it")
        for func in [name for name in sorted(analysis["modules functions"].keys())
                     if 'files' in analysis["modules functions"][name]]:
            modules_functions[func] = {}
            module_function = analysis["modules functions"][func]
            for path in sorted(module_function["files"].keys()):
                collection.logger.debug("Parse signature of function {} from file {}".format(func, path))
                modules_functions[func][path] = \
                    {'declaration': import_declaration(module_function["files"][path]["signature"]),
                     'original declaration': module_function["files"][path]["signature"]}

                if "called at" in module_function["files"][path]:
                    modules_functions[func][path]["called at"] = \
                        set(module_function["files"][path]["called at"])
                if "calls" in module_function["files"][path]:
                    modules_functions[func][path]['calls'] = module_function["files"][path]['calls']
                    for kernel_function in [name for name in sorted(module_function["files"][path]["calls"].keys())
                                            if name in collection.kernel_functions]:
                        kf = collection.get_kernel_function(kernel_function)
                        for call in module_function["files"][path]["calls"][kernel_function]:
                            kf.add_call(func)

                            for index in [index for index in range(len(call))
                                          if call[index] and check_null(kf.declaration, call[index])]:
                                new = kf.declaration.parameters[index]. \
                                    add_implementation(call[index], path, None, None, [],
                                                       is_static(
                                                           analysis['kernel functions'][kf.identifier]['signature']))
                                if len(kf.param_interfaces) > index and kf.param_interfaces[index]:
                                    new.fixed_interface = kf.param_interfaces[index].identifier

    collection.logger.info("Remove kernel functions which are not called at driver functions")
    for func in collection.kernel_functions:
        obj = collection.get_kernel_function(func)
        if len(obj.functions_called_at) == 0 or func in modules_functions:
            collection.remove_kernel_function(func)

    # todo: refactoring is required
    collection._modules_functions = modules_functions


def __import_entities(collection, analysis, entities):
    while len(entities) > 0:
        entity = entities.pop()
        bt = entity["type"]

        if "value" in entity["description"] and isinstance(entity["description"]['value'], str):
            if check_null(bt, entity["description"]["value"]):
                if "declaration" in entity:
                    static = is_static(entity["declaration"])
                else:
                    # Try to find it in global variables and module_functions
                    rn = collection.refined_name(entity["description"]["value"])
                    val = rn if isinstance(rn, str) else entity["description"]["value"]
                    match = False
                    static = False
                    for variable in analysis["global variable initializations"]:
                        variable_name = extract_name(variable['declaration'])
                        if variable_name == val:
                            static = is_static(variable['declaration'])
                            match = True
                            break

                    if not match:
                        for mf in [name for name in sorted(analysis["modules functions"].keys())
                                   if 'files' in analysis["modules functions"][name] and name == val]:
                            module_function = analysis["modules functions"][mf]
                            for path in module_function["files"].keys():
                                static = is_static(module_function["files"][path]["signature"])
                                match = True
                                break

                            if match:
                                break

                bt.add_implementation(
                    entity["description"]["value"],
                    entity["path"],
                    entity["root type"],
                    entity["root value"],
                    entity["root sequence"],
                    static)
            else:
                collection.logger.debug('Skip null pointer value for function pointer {}'.format(bt.to_string('%s')))
        elif "value" in entity["description"] and isinstance(entity["description"]['value'], list):
            if isinstance(bt, Array):
                for entry in entity["description"]['value']:
                    if not entity["root type"]:
                        new_root_type = bt
                    else:
                        new_root_type = entity["root type"]

                    e_bt = bt.element
                    new_sequence = list(entity["root sequence"])
                    new_sequence.append(entry['index'])

                    new_desc = {
                        "type": e_bt,
                        "description": entry,
                        "path": entity["path"],
                        "root type": new_root_type,
                        "root value": entity["root value"],
                        "root sequence": new_sequence
                    }

                    entities.append(new_desc)
            elif isinstance(bt, Structure) or isinstance(bt, Union):
                for entry in sorted(entity["description"]['value'], key=lambda key: str(key['field'])):
                    if not entity["root type"] and not entity["root value"]:
                        new_root_type = bt
                        new_root_value = entity["description"]["value"]
                    else:
                        new_root_type = entity["root type"]
                        new_root_value = entity["root value"]

                    field = extract_name(entry['field'])
                    # Ignore actually unions and structures without a name
                    if field:
                        e_bt = import_declaration(entry['field'], None)
                        e_bt.add_parent(bt)
                        new_sequence = list(entity["root sequence"])
                        new_sequence.append(field)

                        new_desc = {
                            "type": e_bt,
                            "description": entry,
                            "path": entity["path"],
                            "root type": new_root_type,
                            "root value": new_root_value,
                            "root sequence": new_sequence
                        }

                        bt.fields[field] = e_bt
                        entities.append(new_desc)
            else:
                raise NotImplementedError
        else:
            raise TypeError('Expect list or string')

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
