import json

from core.avtg.emg.interface_categories import CategoriesSpecification
from core.avtg.emg.common.interface import Container, Resource, Callback, KernelFunction
from core.avtg.emg.common.signature import Function, Structure, Union, Array, Pointer, InterfaceReference, \
    setup_collection, import_signature, extract_name


class ModuleCategoriesSpecification(CategoriesSpecification):

    def __init__(self, logger):
        self.logger = logger
        self.interfaces = {}
        self.kernel_functions = {}
        self.kernel_macro_functions = {}
        self.kernel_macros = {}
        self.modules_functions = None
        self.inits = None
        self.exits = None
        self.types = {}
        setup_collection(self.types)

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
    def __check_category_relevance(function):
        relevant = []

        if function.rv_interface:
            relevant.append(function.rv_interface)
        else:
            for parameter in function.param_interfaces:
                if parameter:
                    relevant.append(parameter)

        return relevant

    def __set_declaration(self, interface, declaration):
        if type(interface.declaration) is Function:
            if interface.rv_interface:
                if type(interface.declaration.return_value) is InterfaceReference and \
                        interface.declaration.return_value.pointer:
                    self.__set_declaration(interface.rv_interface, declaration.return_value.points)
                else:
                    self.__set_declaration(interface.rv_interface, declaration.return_value)

            for index in range(len(interface.declaration.parameters)):
                p_declaration = declaration.parameters[index]

                if interface.param_interfaces[index]:
                    if type(interface.declaration.parameters[index]) is InterfaceReference and \
                            interface.declaration.parameters[index].pointer:
                        self.__set_declaration(interface.param_interfaces[index], p_declaration.points)
                    else:
                        self.__set_declaration(interface.param_interfaces[index], p_declaration)

        if not interface.declaration.clean_declaration:
            interface.declaration = declaration

    def __import_source_analysis(self, analysis):
        self.logger.info("Import modules init and exit functions")
        self.__import_inits_exits(analysis)

        self.logger.info("Extract complete types definitions")
        self.__extract_types(analysis)

        self.logger.info("Determine categories from extracted types")
        categories = self.__extract_categories()

        self.logger.info("Merge interface categories from both interface categories specification and modules "
                         "interface specification")
        self.__merge_categories(categories)

        self.logger.info("Remove useless interfaces")
        self.__remove_interfaces()

        self.logger.info("Both specifications are imported and categories are merged")

    def __import_inits_exits(self, analysis):
        self.logger.debug("Move module initilizations functions to the modules interface specification")
        if "init" in analysis:
            self.inits = analysis["init"]
        if len(self.inits) == 0:
            raise ValueError('No module initialization functions provided, abort model generation')

        self.logger.debug("Move module exit functions to the modules interface specification")
        if "exit" in analysis:
            self.exits = analysis["exit"]

    def __extract_types(self, analysis):
        entities = []
        # todo: this section below is slow enough
        if 'global variable initializations' in analysis:
            self.logger.info("Import types from global variables initializations")
            for variable in analysis["global variable initializations"]:
                variable_name = extract_name(variable['declaration'])
                signature = import_signature(variable['declaration'])
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
                        []
                    )
                    entities.append(entity)
            self.__import_entities(entities)

        if 'kernel functions' in analysis:
            self.logger.info("Import types from kernel functions")
            for function in analysis['kernel functions']:
                self.logger.debug("Parse signature of function {}".format(function))
                declaration = import_signature(analysis['kernel functions'][function]['signature'])

                if function in self.kernel_functions:
                    self.__set_declaration(self.kernel_functions[function], declaration)
                else:
                    new_intf = KernelFunction(function, analysis['kernel functions'][function]['header'])
                    new_intf.declaration = declaration

        # Remove dirty declarations
        self._refine_interfaces()

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
                        import_signature(module_function["files"][path]["signature"])

                    if "calls" in module_function["files"][path]:
                        for kernel_function in [name for name in module_function["files"][path]["calls"]
                                                if name in self.kernel_functions]:
                            for call in module_function["files"][path]["calls"][kernel_function]:
                                self.kernel_functions[kernel_function].add_call(function)

                                for index in [index for index in range(len(call))
                                              if call[index] and call[index] != "0"]:
                                    self.kernel_functions[kernel_function].declaration.parameters[index].\
                                        add_implementation(call[index], path, None, None, [])

        self.logger.info("Remove kernel functions which are not called at driver functions")
        for function in list(self.kernel_functions.keys()):
            if len(self.kernel_functions[function].called_at) == 0:
                del self.kernel_functions[function]

        self.modules_functions = modules_functions

    def __import_entities(self, entities):
        while len(entities) > 0:
            entity = entities.pop()
            bt = entity["type"]

            if "value" in entity["description"] and type(entity["description"]['value']) is str:
                bt.add_implementation(
                    entity["description"]["value"],
                    entity["path"],
                    entity["root type"],
                    entity["root value"],
                    entity["root sequence"]
                )
            elif "value" in entity["description"] and type(entity["description"]['value']) is list:
                for entry in entity["description"]['value']:
                    if type(entity['type']) is Array:
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
                    elif type(entity['type']) is Structure:
                        if not entity["root type"] and not entity["root value"]:
                            new_root_type = bt
                            new_root_value = entity["description"]["value"]
                        else:
                            new_root_type = entity["root type"]
                            new_root_value = entity["root value"]

                        field = extract_name(entry['field'])
                        e_bt = import_signature(entry['field'], None, bt)
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
                    else:
                        raise NotImplementedError

                    entities.append(new_desc)
            else:
                raise TypeError('Expect list or string')

    @staticmethod
    def __add_to_processing(element, process_list, category):
        if element not in process_list and element not in category['containers']:
            process_list.append(element)
        else:
            return

    @staticmethod
    def __add_interface_candidate(element, e_type, category):
        if element in category[e_type]:
            return
        else:
            category[e_type].append(element)

    def __add_callback(self, signature, category, identifier=None):
        if not identifier:
            identifier = signature.identifier

        if identifier not in category['callbacks']:
            category['callbacks'][identifier] = signature

            for parameter in [p for p in signature.points.parameters if type(p) is not str]:
                self.__add_interface_candidate(parameter, 'resources', category)

    def __extract_categories(self):
        structures = [struct for struct in self.types.values() if type(struct) is Structure and
                      len([field for field in struct.fields.values() if field.clean_declaration]) > 0]
        categories = []

        while len(structures) > 0:
            container = structures.pop()
            category = {
                "callbacks": {},
                "containers": [],
                "resources": []
            }

            to_process = [container]
            while len(to_process) > 0:
                tp = to_process.pop()

                # todo: unions?
                if type(tp) is Structure:
                    c_flag = False
                    for field in tp.fields:
                        if type(tp.fields[field]) is Pointer and \
                                (type(tp.fields[field].points) is Array or
                                 type(tp.fields[field].points) is Structure):
                            self.__add_to_processing(tp.fields[field].points, to_process, category)
                            c_flag = True
                        if type(tp.fields[field]) is Pointer and type(tp.fields[field].points) is Function:
                            self.__add_callback(tp.fields[field], category, field)
                            c_flag = True
                        elif type(tp.fields[field]) is Array or type(tp.fields[field]) is Structure:
                            self.__add_to_processing(tp.fields[field], to_process, category)
                            c_flag = True

                    if tp in structures:
                        del structures[structures.index(tp)]
                    if c_flag:
                        self.__add_interface_candidate(tp, 'containers', category)
                elif type(tp) is Array:
                    if type(tp.element) is Pointer and \
                            (type(tp.element.points) is Array or
                             type(tp.element.points) is Structure):
                        self.__add_to_processing(tp.element.points, to_process, category)
                        self.__add_interface_candidate(tp, 'containers', category)
                    elif type(tp.element) is Pointer and type(tp.element) is Function:
                        self.__add_callback(tp.element, category)
                        self.__add_interface_candidate(tp, 'containers', category)
                    elif type(tp.element) is Array or type(tp.element) is Structure:
                        self.__add_to_processing(tp.element, to_process, category)
                        self.__add_interface_candidate(tp, 'containers', category)
                if (type(tp) is Array or type(tp) is Structure) and len(tp.parents) > 0:
                    for parent in tp.parents:
                        if type(parent) is Structure or \
                           type(parent) is Array:
                            self.__add_to_processing(parent, to_process, category)
                        elif type(parent) is Pointer and len(parent.parents) > 0:
                            for ancestor in parent.parents:
                                if type(ancestor) is Structure or \
                                   type(ancestor) is Array:
                                    self.__add_to_processing(ancestor, to_process, category)

            if len(category['callbacks']) > 0:
                categories.append(category)

            # todo: default registration and deregistrations may need categories based on function pointers directly
            #       passed to kernel functions (feature #6568)
        return categories

    def __resolve_or_add_interface(self, signature, category, constructor):
        interface = self.resolve_interface(signature, category)
        if len(interface) == 0:
            interface = constructor(category, signature.identifier)
            interface.declaration = signature
            self.interfaces[interface.identifier] = interface
            interface = [interface]
        elif len(interface) > 1:
            for intf in interface:
                intf.declaration = signature
        else:
            interface[-1].declaration = signature
        return interface

    def __new_callback(self, declaration, category, identifier):
        if type(declaration) is Pointer and type(declaration.points) is Function:
            probe_identifier = "{}.{}".format(category, identifier)
            if probe_identifier in self.interfaces:
                identifier = declaration.identifier

            interface = Callback(category, identifier)
            interface.declaration = declaration
            self.interfaces[interface.identifier] = interface
            return interface
        else:
            raise TypeError('Expect function pointer to create callback object')

    def __merge_categories(self, categories):
        self.logger.info("Try to find suitable interface descriptions for found types")
        for category in categories:
            category_identifier = self.__yield_category(category)

            # Add containers and resources
            self.logger.info("Found interfaces for category {}".format(category_identifier))
            for signature in category['containers']:
                if type(signature) is not Array and type(signature) is not Structure:
                    raise TypeError('Expect structure or array to create container object')
                interface = self.__resolve_or_add_interface(signature, category_identifier, Container)
                if len(interface) > 1:
                    raise TypeError('Cannot match two containers with the same type')
                else:
                    interface = interface[-1]

                # Refine field interfaces
                for field in list(interface.field_interfaces.keys()):
                    if not interface.field_interfaces[field].declaration.clean_declaration and \
                            interface.declaration.fields[field].clean_declaration:
                        interface.field_interfaces[field].declaration = interface.declaration.fields[field]
                    elif not interface.field_interfaces[field].declaration.clean_declaration:
                        del interface.field_interfaces[field]
            for signature in category['resources']:
                intf = self.resolve_interface_weakly(signature, category_identifier)
                if len(intf) == 0:
                    interface = self.__resolve_or_add_interface(signature, category_identifier, Resource)
                    if len(interface) > 1:
                        raise TypeError('Cannot match two resources with the same type')

            # Add callbacks
            for identifier in category['callbacks']:
                candidates = self.resolve_interface(category['callbacks'][identifier], category_identifier)

                if len(candidates) > 0:
                    containers = self.select_containers(identifier, category['callbacks'][identifier],
                                                        category_identifier)
                    if len(containers) == 1 and identifier in containers[-1].field_interfaces and \
                            containers[-1].field_interfaces[identifier] in candidates:
                        containers[-1].field_interfaces[identifier].declaration = category['callbacks'][identifier]
                    elif len(containers) == 1 and identifier not in containers[-1].field_interfaces:
                        intf = self.__new_callback(category['callbacks'][identifier], category_identifier, identifier)
                        containers[-1].field_interfaces[identifier] = intf
                    else:
                        self.__new_callback(category['callbacks'][identifier], category_identifier, identifier)
                else:
                    self.__new_callback(category['callbacks'][identifier], category_identifier, identifier)

            # Resolve array elements
            for container in [cnt for cnt in self.containers(category_identifier) if cnt.declaration and
                              type(cnt.declaration) is Array and not cnt.element_interface]:
                intf = self.resolve_interface_weakly(container.declaration.element)
                if len(intf) == 1:
                    container.element_interface = intf
                else:
                    raise NotImplementedError

            # Resolve structure interfaces
            for container in [cnt for cnt in self.containers(category_identifier) if cnt.declaration and
                              type(cnt.declaration) is Structure]:
                for field in [field for field in container.declaration.fields
                              if field not in container.field_interfaces]:
                    intf = self.resolve_interface_weakly(container.declaration.fields[field])
                    if len(intf) == 1:
                        container.field_interfaces[field] = intf[-1]
                    elif len(intf) > 0 and field in [i.short_identifier for i in intf]:
                        container.field_interfaces[field] = [i for i in intf if i.short_identifier == field][-1]
                    elif len(intf) > 0:
                        raise NotImplementedError

            # Resolve callback parameters
            for callback in self.callbacks(category_identifier):
                self._fulfill_function_interfaces(callback, category_identifier)

            # Resolve kernel function parameters
            for function in self.kernel_functions.values():
                self._fulfill_function_interfaces(function)

        # Refine dirty declarations
        self._refine_interfaces()

    def __yield_category(self, category):
        category_identifier = None
        for interface_category in ["callbacks", "containers", "resources"]:
            if category_identifier:
                break
            for signature in category[interface_category]:
                interface = self.resolve_interface(signature)
                if len(interface) > 0:
                    category_identifier = interface[-1].category
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
            else:
                containers = self.resolve_containers(callback, callback.category)
                for container in containers:
                    if self.interfaces[container] in relevant_interfaces and \
                            len(self.interfaces[container].declaration.implementations) == 0:
                        relevant_interfaces.append(callback)
                        relevant_interfaces.extend(self.__check_category_relevance(callback))
                        break

        # Add containers
        add_cnt = 1
        while add_cnt != 0:
            add_cnt = 0
            for container in self.containers():
                if type(container.declaration) is Array:
                    match = False

                    for f_intf in container.field_interfaces:
                        if f_intf and f_intf in relevant_interfaces:
                            match = True
                            break

                    if match:
                        relevant_interfaces.append(container)
                        add_cnt += 1
                elif type(container.declaration) is Structure:
                    if container.element_interface in relevant_interfaces:
                        relevant_interfaces.append(container)
                        add_cnt += 1
                else:
                    raise TypeError('Expect structure or array container')

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
