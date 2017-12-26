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

    if 'functions' in analysis:
        collection.logger.info("Import source functions")
        for func in analysis['functions']:
            for path in analysis['functions'][func]:
                description = analysis['functions'][func][path]
                declaration = import_declaration(description['signature'])
                func_intf = collection.get_source_function(func)
                if func_intf and func_intf.declaration.compare(declaration) and not description['static']:
                    func_intf.declaration_files.add(path)
                    func_intf.update_declaration(declaration)
                else:
                    func_intf = SourceFunction(func, description['signature'])
                    func_intf.declaration_files.add(path)

                    if 'definition' in description and description['definition']:
                        func_intf.definition_file = path

                if 'static' in description:
                    func_intf.static = description['static']

                func_intf.raw_declaration = description['signature']
                collection.set_source_function(func_intf, path)

        # Remove dirty declarations
        collection.refine_interfaces()

        # Then add calls
        for func in analysis['functions']:
            for path in analysis['functions'][func]:
                intf = collection.get_source_function(func, path)
                description = analysis['functions'][func][path]
                if "called at" in description:
                    for name in description["called at"]:
                        intf.add_call(name, path)
                if "calls" in description:
                    for name in description["calls"]:
                        intf.call_function(name, path)
                        called_function = collection.get_source_function(name, path)
                        for call in description["calls"][name]:
                            for index in [index for index in range(len(call))
                                          if call[index] and check_null(intf.declaration, call[index])]:

                                rn = collection.refined_name(call[index])
                                candidate = collection.get_source_function(rn, path)
                                if candidate:
                                    static = candidate.static
                                else:
                                    raise ValueError("Cannot find function {!r} in both kernel and module functiosn".
                                                     format(rn))
                                new = called_function.declaration.parameters[index].\
                                    add_implementation(call[index], path, None, None, [], static)
                                if len(intf.param_interfaces) > index and intf.param_interfaces[index]:
                                    new.fixed_interface = intf.param_interfaces[index].identifier
    else:
        collection.logger.warning("There is no any functions in source analysis")

    collection.logger.info("Remove functions which are not called at driver")
    for func in list(collection._source_functions.keys()):
        if None in collection._source_functions[func]:
            del collection._source_functions[func][None]

        if func not in analysis['functions'] or len(collection._source_functions[func].keys()) == 0:
            collection.remove_source_function(func)


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
                            entity["path"] = variable["path"]
                            static = is_static(variable['declaration'])
                            match = True
                            break

                    if not match:
                        if val in analysis["functions"]:
                            # Try to get path with definition
                            paths = [p for p in analysis["functions"][val]
                                     if 'definition' in analysis["functions"][val][p] and
                                     analysis["functions"][val][p]['definition']]
                            if len(paths) == 1:
                                p = paths[0]
                                entity["path"] = p
                                static = analysis["functions"][val][p]['static']
                            elif len(analysis["functions"][val]) > 0:
                                p = list(analysis["functions"][val].keys())[0]
                                entity["path"] = p
                                static = analysis["functions"][val][p]['static']

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

