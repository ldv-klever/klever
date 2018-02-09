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
from core.vtg.emg.common.c.types import Structure, Union, Array, import_declaration, extract_name, check_null


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
                    "description": var.value,
                    "root value": varname,
                    "root type": None,
                    "root sequence": [],
                    "type": var.declaration
                }
                intfs = collection.resolve_interface_weakly(var.declaration)
                if len(intfs) > 1:
                    raise ValueError("Does not expect description of several containers with declation {!r}".
                                     format(var.declaration))
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
    __import_entities(collection, entities)

    collection.logger.info("Search for callbacks provided as parameters")
    for funcname in sa.source_functions:
        for func_obj in sa.get_source_functions(funcname):
            for cf_name in func_obj.calls:
                called_function = collection.get_intf(cf_name)
                if called_function:
                    for indx, parameter in enumerate(called_function.param_interfaces):
                        if parameter:
                            for call in (c[indx] for c in func_obj.calls[cf_name] if c[indx]):
                                parameter.add_implementation(call, called_function.declaration.parameters[indx],
                                                             func_obj.definition_file, None, None, [])


def __import_entities(collection, entities):
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
                intfs = collection.resolve_interface_weakly(entity["type"], category=category)
                for intf in intfs:
                    intf.add_implementation(
                        entity["description"]["value"],
                        entity["type"],
                        entity['path'],
                        entity["root type"],
                        entity["root value"],
                        entity["root sequence"]
                    )
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

