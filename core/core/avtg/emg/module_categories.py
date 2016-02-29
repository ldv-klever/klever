import json

from core.avtg.emg.interface_categories import CategoriesSpecification
from core.avtg.emg.common.interface import Interface, Function, Primitive, Structure, yield_basetype


class ModuleCategoriesSpecification(CategoriesSpecification):

    def __init__(self):
        self.inits = None
        self.exits = None
        self.modules_functions = None

    def import_specification(self, specification=None, module_specification=None, analysis=None):
        # Import interface categories
        if specification:
            super().import_specification(specification)

        if module_specification:
            # todo: import specification (issue 6561)
            raise NotImplementedError

        # Import source analysis
        self.logger.info("Import results of source code analysis")
        self.__import_source_analysis(analysis)

    def save_to_file(self, file):
        raise NotImplementedError
        # todo: export specification (issue 6561)
        #self.logger.info("First convert specification to json and then save")
        #content = json.dumps(self, indent=4, sort_keys=True, cls=SpecEncoder)
        #
        #with open(file, "w", encoding="ascii") as fh:
        #    fh.write(content)

    @staticmethod
    def __add_type(signature, types):
        new_type = yield_basetype(signature)
        if new_type.identifier not in types:
            types[new_type.ideintifier] = new_type

            if type(new_type) is Function:
                if new_type.return_value and new_type.return_value.idenitfier in types:
                    new_type.return_value = types[new_type.return_value.idenitfier]
                elif new_type.return_value and \
                                new_type.return_value.idenitfier not in types:
                    types[new_type.return_value.idenitfier] = new_type.return_value

                for index in range(len(new_type.parameters)):
                    parameter = new_type.parameters[index]
                    if type(parameter) is not str and parameter.identifier in types:
                        new_type.parameters[index] = types[parameter.identifier]
                    elif type(parameter) is not str and parameter.identifier not in types:
                        types[parameter.identifier] = new_type.parameters[index]
        else:
            new_type = types[new_type.ideintifier]

        return new_type

    @staticmethod
    def __remove_pointer_aliases(category, main_type, secondary_type):
        for main in category[main_type]:
            for alias in list(category[secondary_type]):
                if main.pointer_alias(alias):
                    del category[secondary_type][category[secondary_type].index(alias)]
                    main.add_pointer_implementations(alias)
                    if main_type != secondary_type:
                        category[secondary_type].append(main)

    @staticmethod
    def __check_category_relevance(function):
        relevant = []

        if function.rv_interface:
            relevant.append(function.rv_interface)
        else:
            for parameter in function.param_interfaces:
                if parameter:
                    relevant.append(parameter)

        return relevant

    def __import_source_analysis(self, analysis):
        self.logger.info("Import modules init and exit functions")
        self.__import_inits_exits(analysis)

        self.logger.info("Extract complete types definitions")
        kernel_functions, module_functions, types = self.__extract_types(analysis)

        self.logger.info("Determine categories from extracted types")
        categories = self.__extract_categories(types)

        self.logger.info("Merge interface categories from both interface categories specification and modules "
                         "interface specification")
        self.__merge_categories(categories, kernel_functions,  module_functions)

        self.logger.info("Remove useless interfaces")
        self.__remove_interfaces()

    def __import_inits_exits(self, analysis):
        self.logger.debug("Move module initilizations functions to the modules interface specification")
        if "init" in analysis:
            self.inits = self.analysis["init"]

        self.logger.debug("Move module exit functions to the modules interface specification")
        if "exit" in self.analysis:
            self.exits = self.analysis["exit"]

    def __extract_types(self, analysis):
        types = {}
        entities = []
        if 'global variable initializations' in analysis:
            self.logger.info("Import types from global variables initializations")
            for path in analysis["global variable initializations"]:
                for variable in analysis["global variable initializations"][path]:
                    analysis["global variable initializations"][path][variable]["value"] = variable
                    bt = self.__add_type(analysis["global variable initializations"][path][variable]["signature"], types)
                    entity = {
                        "path": path,
                        "description": analysis["global variable initializations"][path][variable],
                        "root values": None,
                        "root types": None,
                        "root sequence": [],
                        "type": bt.identifier
                    }
                    types[bt.identifier] = bt
                    entities.append(entity)
            self.__import_entities(entities, types)

        if 'kernel functions' in analysis:
            self.logger.info("Import types from kernel functions")
            kernel_functions = {}
            for function in analysis['kernel functions']:
                self.logger.debug("Parse signature of function {}".format(function))
                kernel_functions[function] = self.__add_type(function, types)
        
        modules_functions = {}
        if 'modules functions' in analysis:
            self.logger.info("Import modules functions and implementations from kernel functions calls in it")
            for function in [name for name in analysis["modules functions"]
                             if 'files' in analysis["modules functions"][name]]:
                modules_functions[function] = {}
                module_function = analysis["modules functions"][function]
                for path in module_function["files"]:
                    self.logger.debug("Parse signature of function {} from file {}".format(function, path))
                    modules_functions[function][path] = \
                        self.__add_type(module_function["files"][path]["signature"], types)

                    if "calls" in module_function["files"][path]:
                        for kernel_function in [name for name in module_function["files"][path]["calls"]
                                                if name in kernel_functions]:
                            for call in module_function["files"][path]["calls"][kernel_function]:
                                for index in range(len(call)):
                                    if call[index] and call[index] != "0":
                                        kernel_functions[kernel_function].parameters[index].\
                                            add_implementation(call[index], path, None, None, [])

        return kernel_functions, modules_functions, types

    def __import_entities(self, entities, types):
        while len(entities) > 0:
            entity = entities.pop()
            bt = entity["type"]

            if "value" in entity["description"]:
                bt.add_implementation(
                    entity["description"]["value"],
                    entity["path"],
                    entity["root type"],
                    entity["root value"],
                    entity["root sequence"]
                )

            if entity["description"]['type'] == 'structure':
                if not entity["root type"] and not entity["root value"]:
                    new_root_type = bt
                    new_root_value = entity["description"]["value"]
                else:
                    new_root_type = entity["root type"]
                    new_root_value = entity["root value"]

                for field in entity["description"]['fields']:
                    f_bt = self.__add_type(entity["description"]['fields'][field]["signature"], types)
                    new_sequence = list(entity["root sequence"])
                    new_sequence.append(field)

                    new_desc = {
                        "type": f_bt,
                        "description": entity["description"]['fields'][field]["signature"],
                        "path": entity["path"],
                        "root type": new_root_type,
                        "root value": new_root_value,
                        "root sequence": new_sequence
                    }

                    entities.append(new_desc)
                    bt.fields[field] = f_bt
            elif entity["description"]['type'] == 'array':
                # todo: support arrays (issue #6559)
                # todo: add element number to sequence number instead of the field
                raise NotImplementedError("support arrays")

    def __extract_categories(self, types):
        callbacks = [cb for cb in types if type(cb) is Function and cb.suits_for_callback]
        categories = []

        while len(callbacks) > 0:
            cb = callbacks.pop()
            del types[cb.identifier]

            category = {
                "callbacks": [cb],
                "containers": [],
                "resources": []
            }

            number = len(category["callbacks"]) + len(category["containers"]) + len(category["resources"])
            new_number = 0
            while new_number != number:
                number = new_number

                for tp in list(types.values):
                    if type(tp) is Structure:
                        self.__container_check(tp, category)
                        self.__resource_check(tp, category)
                    elif type(tp) is Function:
                        self.__callback_check(tp, category)
                        self.__resource_check(tp, category)
                    elif type(tp) is Primitive:
                        self.__resource_check(tp, category)
                    else:
                        # todo: support arrays (issue #6559)
                        raise NotImplementedError("Unknown type category")

                new_number = len(category["callbacks"]) + len(category["containers"]) + len(category["resources"])

            self.__remove_pointer_aliases(category, "containers", "containers")
            self.__remove_pointer_aliases(category, "containers", "resources")
            self.__remove_pointer_aliases(category, "resources", "resources")

        return categories

    def __container_check(self, tp, category):
        raise NotImplementedError

    def __resource_check(self, tp, category):
        raise NotImplementedError

    def __callback_check(self, tp, category):
        raise NotImplementedError

    def __merge_categories(self, categories, kernel_functions,  module_functions):
        self.logger.info("Try to find suitable interface descriptions for found types")
        for category in categories:
            category_identifier = self.__yield_category(category)

            self.logger.info("Found interfaces for category {}".format(category_identifier))
            for interface_category in ["callbacks", "containers", "resources"]:
                for signature in category[interface_category]:
                    interface = self.resolve_interface(signature)
                    if not interface:
                        interface = Interface(category_identifier, signature.identifier)
                    interface.import_signature(signature)

                    if interface_category == "callbacks":
                        interface.callback = True
                    if interface_category == "resources":
                        interface.resource = True
                    if interface_category == "containers":
                        interface.container = True

            # Populate fields
            for container in self.containers(category_identifier):
                for field in container.declaration.fields:
                    interface = self.resolve_interface(container.declaration.fields[field])
                    if interface:
                        container.field_interfaces[field] = interface

            # Resolve callback parameters
            for callback in self.callbacks(category_identifier):
                self.__resolve_function_interfaces(callback)

            # Resolve kernel function parameters
            for function in self.kernel_functions.values():
                self.__resolve_function_interfaces(function)

            # Resolve module function parameters
            for function_name in self.modules_functions:
                for function in self.modules_functions[function_name].values():
                    self.__resolve_function_interfaces(function)

    def __resolve_function_interfaces(self, interface):
        if interface.declaration.return_value:
            rv_interface = self.resolve_interface(interface.declaration.return_value)
            if rv_interface:
                interface.rv_interface = rv_interface

        for index in range(len(interface.declaration.parameters)):
            if type(interface.declaration.parameters[index]) is not str:
                p_interface = self.resolve_interface(interface.declaration.parameters[index])
                if p_interface:
                    interface.param_interfaces[index] = p_interface
                else:
                    interface.param_interfaces[index] = None
            else:
                interface.param_interfaces[index] = None

    def __yield_category(self, category):
        category_identifier = None
        for interface_category in ["callbacks", "containers", "resources"]:
            if category_identifier:
                break
            for signature in category[interface_category]:
                interface = self.resolve_interface(signature)
                if interface:
                    category_identifier = interface.category
                    break

        if not category_identifier:
            if len(category["containers"]) > 0:
                category_identifier = list(category["containers"].values())[0].identifier
            elif len(category["resources"]) > 0:
                category_identifier = list(category["resources"].values())[0].identifier
            else:
                category_identifier = list(category["callbacks"].values())[0].identifier

        return category_identifier

    def __remove_interfaces(self):
        # Remove categories without implementations
        self.logger.info("Calculate relevant interfaces")
        relevant_interfaces = self.__calculate_relevant_interfaces()

        for interface in list(self.interfaces.values()):
            if interface not in relevant_interfaces:
                del self.interfaces[interface.identifier]

    def __calculate_relevant_interfaces(self):
        relevant_interfaces = []

        # If category interfaces are not used in kernel functions it means that this structure is not transferred to
        # the kernel or just source analysis cannot find all containers
        # Add kernel functionrelevant interfaces
        for name in self.kernel_functions:
            relevant_interfaces.extend(self.__check_category_relevance(self.kernel_functions[name]))

        # Add callbacks and their resources
        for callback in self.callbacks():
            if len(callback.declaration.implementations) > 0:
                relevant_interfaces.append(callback)
                relevant_interfaces.extend(self.__check_category_relevance(callback))

        # Add containers
        add_cnt = 1
        while add_cnt != 0:
            add_cnt = 0
            for container in self.containers():
                match = False

                for f_param in container.param_interfaces:
                    if f_param and f_param in relevant_interfaces:
                        match = True
                        break

                if match:
                    relevant_interfaces.append(container)
                    add_cnt += 1

        return relevant_interfaces


class SpecEncoder(json.JSONEncoder):

    def default(self, object):
        # todo: this does not work currently (issue #6561)
        fd = {}

        if type(object) is ModuleCategoriesSpecification:
            # Dump kernel functions
            fd["kernel functions"] = {}
            for function in object.kernel_functions:
                fd["kernel functions"][function] = {
                    "signature": object.kernel_functions[function]["signature"].get_string(),
                    "header": list(object.kernel_functions[function]["files"].keys())[0]
                }

            # todo: Dump macro-functions
            # todo: Dump macros

            # Dump categories
            fd["categories"] = {}
            for category in object.categories:
                fd["categories"][category] = {
                    "containers": {},
                    "callbacks": {},
                    "resources": {}
                }

                # Add containers
                for container in object.categories[category]["containers"]:
                    fd["categories"][category]["containers"][container] = {
                        "signature": None
                    }

                    if object.categories[category]["containers"][container].header:
                        fd["categories"][category]["containers"][container]["header"] = \
                            object.categories[category]["containers"][container].header

                    fd["categories"][category]["containers"][container]["signature"] = \
                        object.categories[category]["containers"][container].signature.get_string()

                    fd["categories"][category]["containers"][container]["fields"] = \
                        object.categories[category]["containers"][container].fields

                # Add function pointers
                for callback in object.categories[category]["callbacks"]:
                    fd["categories"][category]["callbacks"][callback] = {
                        "signature": object.categories[category]["callbacks"][callback].signature.get_string()
                    }

                # Add resources
                for resource in object.categories[category]["resources"]:
                    fd["categories"][category]["resources"][resource] = {}

                    if resource not in object.categories[category]["containers"]:
                        fd["categories"][category]["resources"][resource]["signature"] = \
                            object.categories[category]["resources"][resource].signature.get_string()

                # todo: Add implementations
                # todo: Add init, exit functions
        else:
            raise NotImplementedError("Cannot encode unknown object with type {}".format(str(type(object))))

        return fd

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
