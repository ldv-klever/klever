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
from core.vtg.emg.common.c.types import Structure, Union, Array, Pointer, Function, import_declaration, extract_name, \
    check_null
from core.vtg.emg.processGenerator.linuxModule.interface import StructureContainer, ArrayContainer, Callback


def extract_implementations(collection, sa):
    entities = []
    # todo: this section below is slow enough
    collection.logger.info("Import values from global variables initializations")
    for varname in sa.source_variables:
        for var in sa.get_source_variables(varname):
            if var and (isinstance(var.declaration, Structure) or isinstance(var.declaration, Array) or
                        isinstance(var.declaration, Union)) and not isinstance(var.value, str):
                # Here we rely on fact that any file should suit
                entity = {
                    "path": var.initialization_file,
                    "description": {'value': var.value},
                    "root value": varname,
                    "root type": None,
                    "root sequence": [],
                    "type": var.declaration
                }
                intfs = collection.resolve_interface_weakly(var.declaration)
                if len(intfs) > 1:
                    collection.logger.info("There are several containers with declation {!r}".
                                           format(var.declaration.to_string('a')))
                for i in intfs:
                    implementation = i.add_implementation(
                        varname,
                        var.declaration,
                        var.initialization_file,
                        None,
                        None,
                        []
                    )
                    implementation.static = var.static
                    # Actually we does not expect several declarations specific for containers
                    entity['category'] = i.category
                entities.append(entity)
    __import_entities(collection, sa, entities)

    collection.logger.info("Search for callbacks provided as parameters")
    for funcname in sa.source_functions:
        for func_obj in sa.get_source_functions(funcname):
            for cf_name in func_obj.calls:
                called_function = collection.get_intf("functions models.{}".format(cf_name))
                if called_function:
                    for indx, parameter in enumerate(called_function.param_interfaces):
                        if parameter:
                            for call in (c[indx] for c in func_obj.calls[cf_name] if c[indx] and c[indx] != '0'):
                                call_obj = sa.get_source_function(call, func_obj.definition_file)
                                if not call_obj:
                                    call_obj = sa.get_source_function(
                                        call, declaration=called_function.declaration.parameters[indx].points)
                                if not call_obj:
                                    raise ValueError("Cannot find function definition for function pointer {!r}".
                                                     format(call))
                                impl = parameter.add_implementation(call, called_function.declaration.parameters[indx],
                                                                    call_obj.definition_file, None, None, [])
                                impl.static = call_obj.static


def __check_static(name, file, sa):
    static = True
    # Check that is a function
    func = sa.get_source_function(name, file)
    if func:
        static = func.static
    else:
        # Check that it is a variable
        var = sa.get_source_variable(name, file)
        if var:
            static = var.static

    return static


def check_relevant_interface(collection, declaration, category, connector):
    def strict_compare(d1, d2):
        if d1.compare(d2):
            if (d2.identifier == 'void *' or d1.identifier == 'void *') and not category:
                return False
            else:
                return True
        else:
            return False

    suits = collection.resolve_containers(declaration, category)
    children = set()
    if len(suits) > 0:
        for suit in suits:
            container = collection.get_intf(suit)
            if isinstance(container, StructureContainer) and connector in container.field_interfaces and \
                    container.field_interfaces[connector] is not None and \
                    strict_compare(container.field_interfaces[connector].declaration, declaration):
                children.add(container.field_interfaces[connector].identifier)
            elif isinstance(container, ArrayContainer) and container.element_interface is not None and \
                    strict_compare(container.element_interface.declaration, declaration):
                children.add(container.element_interface.identifier)

    return (collection.get_intf(i) for i in children)


def __import_entities(collection, sa, entities):
    def determine_category(e, decl):
        c = None
        if 'category' in e:
            c = e['category']
        else:
            resolved = collection.resolve_interface_weakly(decl)
            if len(resolved) == 1:
                c = resolved[0].category
        return c

    while len(entities) > 0:
        entity = entities.pop()
        bt = entity["type"]

        if "value" in entity["description"] and isinstance(entity["description"]['value'], str):
            if check_null(bt, entity["description"]["value"]):
                category = entity["category"] if "category" in entity else None
                intfs = list(check_relevant_interface(collection, entity["type"], category,
                                                      entity["root sequence"][-1]))
                if len(intfs) == 0 and isinstance(entity["type"], Pointer) and \
                        isinstance(entity["type"].points, Function):
                    containers = collection.resolve_interface_weakly(entity['parent type'], category)
                    for container in (c for c in containers if isinstance(c, StructureContainer)):
                        if "{}.{}".format(container.category, entity["root sequence"][-1]) not in collection.interfaces:
                            identifier = entity["root sequence"][-1]
                        elif "{}.{}".format(container.category, entity["type"].pretty_name) \
                                not in collection.interfaces:
                            identifier = entity["type"].pretty_name
                        else:
                            raise RuntimeError("Cannot yield identifier for callback {!r} of category {!r}".
                                               format(entity["type"].identifier, container.category))
                        interface = Callback(container.category, identifier)
                        interface.declaration = entity["type"]
                        collection.set_intf(interface)
                        container.field_interfaces[entity["root sequence"][-1]] = interface
                        intfs.append(interface)
                        break

                for intf in intfs:
                    impl = intf.add_implementation(
                        entity["description"]["value"],
                        entity['type'],
                        entity['path'],
                        entity["root type"],
                        entity["root value"],
                        entity["root sequence"])
                    impl.static = __check_static(entity["description"]["value"], entity['path'], sa)

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
                        "parent type": bt,
                        "root type": new_root_type,
                        "root value": entity["root value"],
                        "root sequence": new_sequence
                    }

                    category = determine_category(entity, e_bt)
                    if category:
                        new_desc["category"] = category

                    entities.append(new_desc)
            elif isinstance(bt, Structure) or isinstance(bt, Union):
                for entry in entity["description"]['value']:
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
                            "parent type": bt,
                            "root type": new_root_type,
                            "root value": new_root_value,
                            "root sequence": new_sequence
                        }
                        category = determine_category(entity, e_bt)
                        if category:
                            new_desc["category"] = category

                        bt.fields[field] = e_bt
                        entities.append(new_desc)
            else:
                raise NotImplementedError
        else:
            raise TypeError('Expect list or string')
