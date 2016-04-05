import json

from core.avtg.emg.interface_categories import CategoriesSpecification
from core.avtg.emg.common.interface import Container, Resource, Callback, KernelFunction
from core.avtg.emg.common.signature import Function, Structure, Union, Array, Pointer, Primitive, InterfaceReference, \
    setup_collection, import_signature, import_typedefs, extract_name, check_null


class ModuleCategoriesSpecification(CategoriesSpecification):

    def __init__(self, logger):
        self.logger = logger
        self.interfaces = {}
        self.kernel_functions = {}
        self.kernel_macro_functions = {}
        self.kernel_macros = {}
        self.modules_functions = None
        self.inits = []
        self.exits = []
        self.types = {}
        self.typedefs = {}
        self._locked_categories = set()
        self._implementations_cache = {}
        self._containers_cache = {}
        self._interface_cache = {}

        setup_collection(self.types, self.typedefs)

    def import_specification(self, specification=None, module_specification=None, analysis=None):
        # Import typedefs if there are provided
        if analysis and 'typedefs' in analysis:
            import_typedefs(analysis['typedefs'])

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

    def collect_relevant_models(self, function):
        self.logger.debug("Collect relevant kernel functions called in a call stack of function ''".format(function))
        process_names = [function]
        processed_names = []
        relevant = []
        while len(process_names) > 0:
            name = process_names.pop()

            if name in self.modules_functions:
                for file in sorted(self.modules_functions[name].keys()):
                    for called in self.modules_functions[name][file]['calls']:
                        if called in self.modules_functions and called not in processed_names and \
                                called not in process_names:
                            process_names.append(called)
                        elif called in self.kernel_functions:
                            relevant.append(called)

            processed_names.append(name)
        return relevant

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
            raise ValueError('There is no module initialization function provided')

        self.logger.debug("Move module exit functions to the modules interface specification")
        if "exit" in analysis:
            self.exits = analysis["exit"]
        if len(self.exits) == 0:
            self.logger.warning('There is no module exit function provided')

    def __extract_types(self, analysis):
        entities = []
        # todo: this section below is slow enough
        if 'global variable initializations' in analysis:
            self.logger.info("Import types from global variables initializations")
            for variable in sorted(analysis["global variable initializations"],
                                   key=lambda var: str(var['declaration'])):
                variable_name = extract_name(variable['declaration'])
                if not variable_name:
                    raise ValueError('Global variable without a name')

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
            for function in sorted(analysis['kernel functions'].keys()):
                self.logger.debug("Parse signature of function {}".format(function))
                declaration = import_signature(analysis['kernel functions'][function]['signature'])

                if function in self.kernel_functions:
                    self.__set_declaration(self.kernel_functions[function], declaration)
                else:
                    new_intf = KernelFunction(function, analysis['kernel functions'][function]['header'])
                    new_intf.declaration = declaration

        # Remove dirty declarations
        self._refine_interfaces()

        # Import modules functions
        modules_functions = {}
        if 'modules functions' in analysis:
            self.logger.info("Import modules functions and implementations from kernel functions calls in it")
            for function in [name for name in sorted(analysis["modules functions"].keys())
                             if 'files' in analysis["modules functions"][name]]:
                modules_functions[function] = {}
                module_function = analysis["modules functions"][function]
                for path in sorted(module_function["files"].keys()):
                    self.logger.debug("Parse signature of function {} from file {}".format(function, path))
                    modules_functions[function][path] = \
                        {'declaration': import_signature(module_function["files"][path]["signature"])}

                    if "calls" in module_function["files"][path]:
                        modules_functions[function][path]['calls'] = module_function["files"][path]['calls']
                        for kernel_function in [name for name in sorted(module_function["files"][path]["calls"].keys())
                                                if name in self.kernel_functions]:
                            kf = self.kernel_functions[kernel_function]
                            for call in module_function["files"][path]["calls"][kernel_function]:
                                kf.add_call(function)

                                for index in [index for index in range(len(call))
                                              if call[index] and
                                              check_null(kf.declaration, call[index])]:
                                    kf.declaration.parameters[index].\
                                        add_implementation(call[index], path, None, None, [])

        self.logger.info("Remove kernel functions which are not called at driver functions")
        for function in sorted(self.kernel_functions.keys()):
            if len(self.kernel_functions[function].called_at) == 0:
                del self.kernel_functions[function]

        self.modules_functions = modules_functions

    def __import_entities(self, entities):
        while len(entities) > 0:
            entity = entities.pop()
            bt = entity["type"]

            if "value" in entity["description"] and type(entity["description"]['value']) is str:
                if check_null(bt, entity["description"]["value"]):
                    bt.add_implementation(
                        entity["description"]["value"],
                        entity["path"],
                        entity["root type"],
                        entity["root value"],
                        entity["root sequence"]
                    )
                else:
                    self.logger.debug('Skip null pointer value for function pointer {}'.format(bt.to_string('%s')))
            elif "value" in entity["description"] and type(entity["description"]['value']) is list:
                if type(bt) is Array:
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
                elif type(bt) is Structure or type(bt) is Union:
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
                            entities.append(new_desc)
                else:
                    raise NotImplementedError
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
        structures = [self.types[name] for name in sorted(self.types.keys()) if type(self.types[name]) is Structure and
                      len([self.types[name].fields[nm] for nm in sorted(self.types[name].fields.keys())
                           if self.types[name].fields[nm].clean_declaration]) > 0]
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

                if type(tp) is Structure or type(tp) is Union:
                    c_flag = False
                    for field in sorted(tp.fields.keys()):
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
        interface = self.resolve_interface(signature, category, False)
        if len(interface) == 0:
            interface = constructor(category, signature.pretty_name)
            self.logger.debug("Create new interface '{}' with signature '{}'".
                              format(interface.identifier, signature.identifier))
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
                identifier = declaration.pretty_name

            interface = Callback(category, identifier)
            self.logger.debug("Create new interface '{}' with signature '{}'".
                              format(interface.identifier, declaration.identifier))
            interface.declaration = declaration
            self.interfaces[interface.identifier] = interface
            return interface
        else:
            raise TypeError('Expect function pointer to create callback object')

    def __get_field_candidates(self, container):
        changes = True
        while changes:
            changes = False
            for field in [field for field in container.declaration.fields if field not in container.field_interfaces]:
                intf = self.__match_interface_for_container(container.declaration.fields[field], container.category,
                                                            field)
                if intf:
                    container.field_interfaces[field] = intf
                    changes = True

    def __match_interface_for_container(self, signature, category, id_match):
        candidates = self.resolve_interface_weakly(signature, category, False)

        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) == 0:
            return None
        else:
            strict_candidates = self.resolve_interface(signature, category, False)
            if len(strict_candidates) == 1:
                return strict_candidates[0]
            elif len(strict_candidates) > 1 and id_match:
                id_candidates = [intf for intf in strict_candidates if intf.short_identifier == id_match]
                if len(id_candidates) == 1:
                    return id_candidates[0]
                else:
                    return None

            if len(strict_candidates) > 1:
                raise RuntimeError('There are several interfaces with the same declaration {}'.
                                   format(signature.to_string('a')))

            # Filter of resources
            candidates = [intf for intf in candidates if type(intf) is not Resource]
            if len(candidates) == 1:
                return candidates[0]
            else:
                return None

    def __merge_categories(self, categories):
        self.logger.info("Try to find suitable interface descriptions for found types")
        for category in categories:
            category_identifier = self.__yield_existing_category(category)
            if not category_identifier:
                category_identifier = self.__yield_new_category(category)

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
                for field in sorted(interface.field_interfaces.keys()):
                    if not interface.field_interfaces[field].declaration.clean_declaration and \
                            interface.declaration.fields[field].clean_declaration:
                        interface.field_interfaces[field].declaration = interface.declaration.fields[field]
                    elif not interface.field_interfaces[field].declaration.clean_declaration:
                        del interface.field_interfaces[field]
            for signature in category['resources']:
                intf = self.resolve_interface_weakly(signature, category_identifier, False)
                if len(intf) == 0:
                    interface = self.__resolve_or_add_interface(signature, category_identifier, Resource)
                    if len(interface) > 1:
                        raise TypeError('Cannot match two resources with the same type')

            # Add callbacks
            for identifier in sorted(category['callbacks'].keys()):
                candidates = self.resolve_interface(category['callbacks'][identifier], category_identifier, False)

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
                intf = self.__match_interface_for_container(container.declaration.element, container.category, None)
                if intf:
                    container.element_interface = intf

            # Resolve structure interfaces
            for container in [cnt for cnt in self.containers(category_identifier) if cnt.declaration and
                              type(cnt.declaration) is Structure]:
                self.__get_field_candidates(container)

            # Resolve callback parameters
            for callback in self.callbacks(category_identifier):
                self._fulfill_function_interfaces(callback, category_identifier)

            # Resolve kernel function parameters
            for function in [self.kernel_functions[name] for name in sorted(self.kernel_functions.keys())]:
                self._fulfill_function_interfaces(function)

        # Refine dirty declarations
        self._refine_interfaces()

    def __yield_existing_category(self, category):
        category_identifier = None
        for interface_category in ["containers"]:
            if category_identifier:
                break
            for signature in category[interface_category]:
                interface = self.resolve_interface(signature, False)
                if len(interface) > 0 and interface[-1].category not in self._locked_categories:
                    category_identifier = interface[-1].category
                    break
        for interface_category in ["callbacks"]:
            if category_identifier:
                break
            for signature in sorted(list(category[interface_category].values()), key=lambda y: y.identifier):
                interface = self.resolve_interface(signature, False)
                if len(interface) > 0 and interface[-1].category not in self._locked_categories:
                    category_identifier = interface[-1].category
                    break

        return category_identifier

    def __yield_new_category(self, category):
        category_identifier = None
        for interface_category in ["containers", "resources"]:
            if category_identifier:
                break
            for signature in category[interface_category]:
                if signature.pretty_name not in self.categories:
                    category_identifier = signature.pretty_name
                    break

        if category_identifier:
            return category_identifier
        else:
            raise ValueError('Cannot find a suitable category identifier')

    def __remove_interfaces(self):
        # Remove categories without implementations
        self.logger.info("Calculate relevant interfaces")
        relevant_interfaces = self.__calculate_relevant_interfaces()

        for interface in [self.interfaces[name] for name in sorted(self.interfaces.keys())]:
            if interface not in relevant_interfaces:
                self.logger.debug("Delete interface description {} as unrelevant".format(interface.identifier))
                del self.interfaces[interface.identifier]

    def __calculate_relevant_interfaces(self):
        relevant_interfaces = set()

        # If category interfaces are not used in kernel functions it means that this structure is not transferred to
        # the kernel or just source analysis cannot find all containers
        # Add kernel functionrelevant interfaces
        for name in sorted(self.kernel_functions):
            relevant_interfaces.update(self.__check_category_relevance(self.kernel_functions[name]))

        # Add all interfaces for non-container categories
        for interface in set(relevant_interfaces):
            containers = self.containers(interface.category)
            if len(containers) == 0:
                relevant_interfaces.update([self.interfaces[name] for name in sorted(self.interfaces)
                                            if self.interfaces[name].category == interface.category])

        # Add callbacks and their resources
        for callback in self.callbacks():
            if len(self.implementations(callback)) > 0:
                relevant_interfaces.add(callback)
                relevant_interfaces.update(self.__check_category_relevance(callback))
            else:
                containers = self.resolve_containers(callback, callback.category)
                for container in containers:
                    if self.interfaces[container] in relevant_interfaces and \
                            len(self.interfaces[container].declaration.implementations) == 0:
                        relevant_interfaces.add(callback)
                        relevant_interfaces.update(self.__check_category_relevance(callback))
                        break

        # Add containers
        add_cnt = 1
        while add_cnt != 0:
            add_cnt = 0
            for container in [cnt for cnt in self.containers() if cnt not in relevant_interfaces]:
                if type(container.declaration) is Structure:
                    match = False

                    for f_intf in [container.field_interfaces[name] for name
                                   in sorted(container.field_interfaces.keys())]:
                        if f_intf and f_intf in relevant_interfaces:
                            match = True
                            break

                    if match:
                        relevant_interfaces.add(container)
                        add_cnt += 1
                elif type(container.declaration) is Array:
                    if container.element_interface in relevant_interfaces:
                        relevant_interfaces.add(container)
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
