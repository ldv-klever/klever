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

import sortedcontainers

from klever.core.vtg.emg.common.c.types import Structure, Union, Array, Pointer, Function, import_declaration, extract_name, \
    is_not_null_function
from klever.core.vtg.emg.generators.linuxModule.interface import Callback, StructureContainer, ArrayContainer
from klever.core.vtg.emg.generators.linuxModule.interface.specification import import_interface_specification
from klever.core.vtg.emg.generators.linuxModule.interface.categories import yield_categories


def import_specification(logger, conf, collection, sa, specification):
    """
    Import specifications and populate provided interface collection.

    :param logger: Logger object.
    :param conf: Configuration dict.
    :param collection: InterfaceCollection object.
    :param sa: Source object.
    :param specification: Dict with imported specification.
    """

    logger.info("Analyze provided interface categories specification")
    import_interface_specification(logger, collection, sa, specification)

    logger.info("Import results of source code analysis")
    __extract_implementations(logger, collection, sa)

    logger.info("Match interfaces with existing categories and introduce new categories")
    yield_categories(logger, conf, collection, sa)

    logger.info("Interface specifications are imported and categories are merged")


def __extract_implementations(logger, collection, sa):
    entities = []
    logger.info("Import values from global variables initializations")
    for varname, var in ((varname, var) for varname in sa.source_variables for var in sa.get_source_variables(varname)):
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
                logger.info("There are several containers with declaration {!r}".format(var.declaration.to_string('a')))
            for i in intfs:
                i.add_implementation(
                    varname,
                    var.declaration,
                    var.initialization_file,
                    None,
                    None,
                    []
                )
                # Actually we does not expect several declarations specific for containers
                entity['category'] = i.category
            entities.append(entity)
    __import_entities(collection, sa, entities)

    logger.info("Search for callbacks provided as parameters")
    for name, obj, in ((name, obj) for name in sa.source_functions for obj in sa.get_source_functions(name)):
        for cf_name in obj.calls:
            called_function = collection.get_intf("functions models.%s" % cf_name)
            if called_function:
                for indx, parameter in enumerate(called_function.param_interfaces):
                    if parameter:
                        for call in (c[indx] for c in obj.calls[cf_name] if c[indx] and c[indx] != '0'):
                            call_obj = sa.get_source_function(call, obj.definition_file)
                            if not call_obj:
                                call_obj = sa.get_source_function(
                                    call, declaration=called_function.declaration.parameters[indx].points)
                            if not call_obj:
                                raise ValueError("Cannot find function definition for function pointer {!r}".
                                                 format(call))
                            parameter.add_implementation(call, called_function.declaration.parameters[indx],
                                                         call_obj.definition_file, None, None, [])


def check_relevant_interface(collection, declaration, category, connector):
    def strict_compare(d1, d2):
        if d1 == d2:
            if (d2 == 'void *' or d1 == 'void *') and not category:
                return False
            else:
                return True
        else:
            return False

    children = sortedcontainers.SortedSet()
    suits = collection.resolve_containers(declaration, category)
    for suit in suits:
        container = collection.get_intf(suit)
        if isinstance(container, StructureContainer) and connector in container.field_interfaces and \
                container.field_interfaces[connector] is not None and \
                strict_compare(container.field_interfaces[connector].declaration, declaration):
            children.add(str(container.field_interfaces[connector]))
        elif isinstance(container, ArrayContainer) and container.element_interface is not None and \
                strict_compare(container.element_interface.declaration, declaration):
            children.add(str(container.element_interface))

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

    while entities:
        entity = entities.pop()
        bt = entity["type"]

        if "value" in entity["description"] and isinstance(entity["description"]['value'], str):
            if is_not_null_function(bt, entity["description"]["value"]):
                category = entity["category"] if "category" in entity else None
                intfs = list(check_relevant_interface(collection, entity["type"], category, entity["root sequence"][-1]))
                if not intfs and isinstance(entity["type"], Pointer) and isinstance(entity["type"].points, Function):
                    containers = collection.resolve_interface_weakly(entity['parent type'], category)
                    for container in (c for c in containers if isinstance(c, StructureContainer)):
                        if "{}.{}".format(container.category, entity["root sequence"][-1]) not in collection.interfaces:
                            identifier = entity["root sequence"][-1]
                        elif "{}.{}".format(container.category, entity["type"].pretty_name) not in collection.interfaces:
                            identifier = entity["type"].pretty_name
                        else:
                            raise RuntimeError("Cannot yield identifier for callback {!r} of category {!r}".
                                               format(str(entity["type"]), container.category))
                        interface = Callback(container.category, identifier)
                        interface.declaration = entity["type"]
                        collection.set_intf(interface)
                        container.field_interfaces[entity["root sequence"][-1]] = interface
                        intfs.append(interface)
                        break

                for intf in intfs:
                    intf.add_implementation(
                        entity["description"]["value"],
                        entity['type'],
                        entity['path'],
                        entity["root type"],
                        entity["root value"],
                        entity["root sequence"])

        elif "value" in entity["description"] and isinstance(entity["description"]['value'], list):
            if isinstance(bt, Array):
                bt.size = len(entity["description"]['value'])
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
