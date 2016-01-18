import json


from core.avtg.emg.representations import Signature, Interface, Implementation


class CategorySpecification:

    def __init__(self, logger):
        self.logger = logger
        self.categories = {}
        self.interfaces = {}
        self.kernel_functions = {}
        self.kernel_macro_functions = {}
        self.kernel_macros = {}
        self.logger.info("Interface categories specification has been initialized")

    def import_specification(self, specification):
        self.logger.info("Analyze provided interface categories specification")
        for category in specification["categories"]:
            self.logger.debug("Found interface category {}".format(category))
            self.__import_category_interfaces(category, specification["categories"][category])

        if "kernel functions" in specification:
            self.logger.info("Import kernel functions description")
            for intf in self.__import_kernel_interfaces("kernel functions", specification):
                self.kernel_functions[intf.identifier] = intf
                self.logger.debug("New interface {} has been imported".format(intf.full_identifier))
        else:
            self.logger.warning("Kernel functions are not provided within an interface categories specification, "
                                "expect 'kernel functions' attribute")

        if "kernel macro-functions" in specification:
            self.logger.info("Import kernel macro-functions description")
            for intf in self.__import_kernel_interfaces("kernel macro-functions", specification):
                self.kernel_macro_functions[intf.identifier] = intf
                self.logger.debug("New interface {} has been imported".format(intf.full_identifier))
        else:
            self.logger.warning("Kernel functions are not provided within an interface categories specification, "
                                "expect 'kernel macro-functions' attribute")

        # Populate signatures instead of Interface signatures and assign interface links
        self.logger.info("Add references to an Interface objects of categories instead of just interface names")
        signatures_to_process = []
        for intf in self.interfaces:
            signatures_to_process.append([self.interfaces, self.interfaces[intf].signature])

            # Check fields in case of container
            if not self.interfaces[intf].container and self.interfaces[intf].signature.type_class == "struct":
                # Fields matter for containers only, do not keep unnecessary date
                self.logger.debug("Remove fields description for interface {} which is not a container".format(intf))
                self.interfaces[intf].signature.fields = {}

        self.logger.info("Add references to an Interface objects of kernel interfaces instead of just interface names")
        for function in self.kernel_functions:
            signatures_to_process.append([self.kernel_functions, self.kernel_functions[function].signature])

        # Process signatures
        self._process_signatures(signatures_to_process)

    def _process_signatures(self, signatures):
        processed_or_processing = [sign for coll, sign in signatures]
        while signatures:
            collection, signature = signatures.pop()
            self.logger.debug("Replace all entries of interface names with an object references in signature {}".
                              format(signature.expression))

            # Replace string interface definition by reference
            if signature.interface and type(signature.interface) is str:
                signature.interface = collection[signature.interface]

            # Replace Interface signature
            if signature.type_class == "interface":
                if signature.interface.signature.type_class == "interface":
                    raise RuntimeError("Attempt to replace interface signature with an interface signature")
                signature.replace(signature.interface.signature)

            # Process return value and parameters in case of function
            if signature.type_class == "function":
                if signature.return_value and signature.return_value not in processed_or_processing:
                    signatures.append([self.interfaces, signature.return_value])
                for index in range(len(signature.parameters)):
                    if type(signature.parameters[index]) is Signature and signature.parameters[index] \
                            not in processed_or_processing:
                        signatures.append([self.interfaces, signature.parameters[index]])

            # Check fields in case of structure
            elif signature.type_class == "struct":
                if len(signature.fields) > 0:
                    for field in [field for field in signature.fields if signature.fields[field] not in
                                  processed_or_processing]:
                        signatures.append([self.interfaces, signature.fields[field]])
            elif signature.type_class == "interface":
                raise RuntimeError("Cannot replace signature {} with an interface object reference".
                                   format(signature.expression))

            if signature not in processed_or_processing:
                    processed_or_processing.append(signature)

    def __import_kernel_interfaces(self, category_name, collection):
        for identifier in collection[category_name]:
            self.logger.debug("Import a description of kernel interface {} from category {}".
                              format(identifier, category_name))
            if "signature" not in collection[category_name][identifier]:
                raise TypeError("Specify 'signature' for kernel interface {} at {}".format(identifier, category_name))
            elif "header" not in collection[category_name][identifier]:
                raise TypeError("Specify 'header' for kernel interface {} at {}".format(identifier, category_name))

            # Create interface description
            intf = Interface(collection[category_name][identifier]["signature"],
                             "kernel",
                             identifier,
                             collection[category_name][identifier]["header"],
                             True)

            # Assign additional values
            intf.category = category_name
            intf.signature.interface = intf.identifier

            # Check whether interface corresponds its signature
            self.logger.debug("Check whether interface corresponds its signature")
            if intf.signature.function_name and intf.signature.function_name != identifier:
                raise ValueError("Kernel function name {} does not correspond its signature {}".
                                 format(identifier, intf.signature.expression))
            elif not intf.signature.function_name:
                raise ValueError("Kernel function name {} is not a macro or a function".
                                 format(identifier, intf.signature.expression))
            yield intf

    def __import_interfaces(self, category_name, collection):
        for intf_identifier in collection:
            if "{}.{}".format(category_name, intf_identifier) in self.interfaces:
                self.logger.debug("Found a description of an existing interface {} from category {}".
                                  format(intf_identifier, category_name))
                yield self.interfaces["{}.{}".format(category_name, intf_identifier)]
            else:
                self.logger.debug("Initialize description of an interface {} from category {}".
                                  format(intf_identifier, category_name))

                implmented_flag = False
                if "implemented in kernel" in collection[intf_identifier]:
                    implmented_flag = True
                if "header" in collection[intf_identifier]:
                    header = collection[intf_identifier]["header"]
                else:
                    header = None

                if "signature" in collection[intf_identifier]:
                    intf = Interface(collection[intf_identifier]["signature"],
                                     category_name,
                                     intf_identifier,
                                     header,
                                     implmented_flag)
                    if "fields" in collection[intf_identifier]:
                        intf.fields = collection[intf_identifier]["fields"]

                    yield intf
                elif "signature" not in collection[intf_identifier] and \
                     "{}.{}".format(category_name, intf_identifier) in self.interfaces:
                    yield self.interfaces["{}.{}".format(category_name, intf_identifier)]
                else:
                    raise TypeError("Provide 'signature' for interface {} at {} or define it as a container".
                                    format(intf_identifier, category_name))

    def __import_category_interfaces(self, category_name, dictionary):
        self.logger.debug("Initialize description for category {}".format(category_name))
        if category_name in self.categories:
            self.logger.warning("Category {} has been already defined in the inteface category specification".
                                format(category_name))
        else:
            self.categories[category_name] = {
                "containers": {},
                "resources": {},
                "callbacks": {}
            }

        if "containers" in dictionary:
            self.logger.debug("Import containers from a description of an interface category {}".format(category_name))
            for intf in self.__import_interfaces(category_name, dictionary["containers"]):
                if intf and intf.full_identifier not in self.interfaces:
                    self.logger.debug("Imported new interface description {}".format(intf.full_identifier))
                    self.interfaces[intf.full_identifier] = intf
                    intf.container = True
                    self.categories[intf.category]["containers"][intf.identifier] = intf
                elif intf and intf.full_identifier in self.interfaces:
                    self.logger.debug("Imported existing interface description {}".format(intf.full_identifier))
                    self.categories[intf.category]["containers"][intf.identifier] = intf
                    intf.container = True
        if "resources" in dictionary:
            self.logger.debug("Import resources from a description of an interface category {}".format(category_name))
            for intf in self.__import_interfaces(category_name, dictionary["resources"]):
                if intf and intf.full_identifier not in self.interfaces:
                    self.logger.debug("Imported new interface description {}".format(intf.full_identifier))
                    intf.resource = True
                    self.interfaces[intf.full_identifier] = intf
                    self.categories[intf.category]["resources"][intf.identifier] = intf
                elif intf and intf.full_identifier in self.interfaces:
                    self.logger.debug("Imported existing interface description {}".format(intf.full_identifier))
                    self.categories[intf.category]["resources"][intf.identifier] = intf
                    intf.resource = True
        if "callbacks" in dictionary:
            self.logger.debug("Import callbacks from a description of an interface category {}".format(category_name))
            for intf in self.__import_interfaces(category_name, dictionary["callbacks"]):
                if intf and intf.full_identifier not in self.interfaces:
                    self.logger.debug("Imported new interface description {}".format(intf.full_identifier))
                    intf.callback = True
                    self.interfaces[intf.full_identifier] = intf
                    self.categories[intf.category]["callbacks"][intf.identifier] = intf
                elif intf and intf.full_identifier in self.interfaces:
                    self.logger.debug("Imported existing interface description {}".format(intf.full_identifier))
                    self.categories[intf.category]["callbacks"][intf.identifier] = intf
                    intf.callback = True


class ModuleSpecification(CategorySpecification):

    def import_specification(self, specification, analysis=None, categories=None):

        # Check specification and analysis
        if not analysis:
            analysis = {}

        # Import categories
        self.categories = categories.categories
        self.interfaces = categories.interfaces
        self.kernel_functions = categories.kernel_functions
        self.kernel_macro_functions = categories.kernel_macro_functions
        self.kernel_macros = categories.kernel_macros
        self.analysis = analysis
        self.inits = None
        self.exits = None
        self.modules_functions = None
        self.implementations = {}

        # Import categories from modules specification
        if specification:
            super().import_specification(specification)

        # todo: import existing module specification

        # Import source analysis
        self.logger.info("Import results of source code analysis first")
        self.__import_source_analysis()
        self.logger.info("Results of source code analysis are imported")

        # Remove categories without callbacks or relevant interfaces
        self.__remove_categories()

    def save_to_file(self, file):
        self.logger.info("First convert specification to json and then save")
        content = json.dumps(self, indent=4, sort_keys=True, cls=SpecEncoder)

        with open(file, "w") as fh:
            fh.write(content)

    def __import_source_analysis(self):
        self.logger.info("Start processing source code amnalysis raw data")
        self.__parse_signatures_as_is()

        self.logger.info("Mark all found types as interfaces if there are already specified")
        self.__mark_existing_interfaces()

        self.logger.info("Yield more new interfaces from existng data in source analysis data")
        self.__add_new_interfaces()

        self.logger.info("Mark all found types as interfaces if there are already specified")
        self.__mark_existing_interfaces()

        self.logger.info("Add information about interface implementations")
        self.__add_implementations_from_analysis()

    def __add_implementations_from_analysis(self):
        self.logger.info("Add global variables as interface implementations")
        # Import variable implementations
        for path in self.analysis["global variable initializations"]:
            for variable in self.analysis["global variable initializations"][path]:
                signature = self.analysis["global variable initializations"][path][variable]
                if signature.interface:
                    self.logger.debug("Add global variable {} from {} as implementation of {}".
                                      format(variable, path, signature.interface.full_identifier))
                    implementation = Implementation("& " + variable,
                                                    path,
                                                    signature.interface.full_identifier,
                                                    variable)
                    self.interfaces[signature.interface.full_identifier].implementations.append(implementation)

                    # Import fields implementations
                    for field in [name for name in signature.fields if name in self.implementations[path][variable] and
                                  name in signature.interface.fields]:
                        identifier = "{}.{}".\
                            format(signature.interface.category, signature.interface.fields[field])
                        interface = self.interfaces[identifier]
                        implementation = Implementation(self.implementations[path][variable][field],
                                                        path,
                                                        signature.interface.full_identifier,
                                                        variable)
                        interface.implementations.append(implementation)

        # Import implementations from function parameters
        for mf in [self.analysis["modules functions"][name] for name in self.analysis["modules functions"]
                   if "files" in self.analysis["modules functions"][name]]:
            for path in [name for name in mf["files"] if "calls" in mf["files"][name]]:
                for kf in [name for name in mf["files"][path]["calls"] if name in self.kernel_functions]:
                    for call in mf["files"][path]["calls"][kf]:
                        for index in range(len(call)):
                            if call[index] and call[index] != "0" and \
                                    self.kernel_functions[kf].signature.parameters[index] and \
                                    self.kernel_functions[kf].signature.parameters[index].interface:
                                identifier = \
                                    self.kernel_functions[kf].signature.parameters[index].interface.full_identifier

                                if len((impl for impl in self.interfaces[identifier].implementations
                                        if impl.value == call[index])) == 0:
                                    implementation = Implementation(call[index], path, None, None)
                                    self.interfaces[identifier].implementations.append(implementation)

        self.logger.debug("Remove global variables initialization description")
        del self.analysis["global variable initializations"]

        self.logger.debug("Move kernel functions descriptions to the modules interface specification")
        self.kernel_functions = self.analysis["kernel functions"]
        del self.analysis["kernel functions"]

        self.logger.debug("Move modules functions descriptions to the modules interface specification")
        self.modules_functions = self.analysis["modules functions"]
        del self.analysis["modules functions"]

        # TODO: modules can omit init functions, e.g. drivers/media/common/saa7146/saa7146.ko, drivers/media/common/tveeprom.ko and many others.
        self.logger.debug("Move module initilizations functions to the modules interface specification")
        self.inits = self.analysis["init"]
        del self.analysis["init"]

        # TODO: modules can omit exit functions, e.g. drivers/block/xen-blkback/xen-blkback.ko.
        self.logger.debug("Move module exit functions to the modules interface specification")
        self.exits = self.analysis["exit"]
        del self.analysis["exit"]

        self.logger.debug("Delete finally source code analysis, since all data is added to the modules interface "
                          "specification")
        del self.analysis

    def __add_new_interfaces(self):
        # Extract more containers from containters with callbacks
        self.logger.info("Extract more interfaces from global variables")
        for path in self.analysis["global variable initializations"]:
            for variable in self.analysis["global variable initializations"][path]:
                self.logger.debug("Analyze global variable {} from {} to extract more interfaces".
                                  format(variable, path))
                var_desc = self.analysis["global variable initializations"][path][variable]

                if not var_desc.interface:
                    self.logger.debug("Cannot match global variable {} from {} with any interface".
                                      format(variable, path))
                    self.__process_unmatched_structure(var_desc)
                elif var_desc.interface and var_desc.interface.container:
                    self.logger.debug("Matched global variable {} from {} with an interface {}".
                                      format(variable, path, var_desc.interface))
                    self.__process_matched_structure(var_desc)
        # todo: use also other data to extract more interfaces

    def __process_matched_structure(self, structure):
        self.logger.debug("Analyze fields of matched structure {}".format(structure.expression))
        for field in structure.fields:
            if not structure.fields[field].interface:
                self.logger.debug("Field {} is not recognized as an interface")

                if field in structure.interface.fields:
                    structure.fields[field].interface = \
                        self.categories[structure.interface.category]["callbacks"][structure.interface.fields[field]]
                else:
                    if structure.fields[field].type_class == "function":
                        intf = self.__make_intf_from_signature(structure.fields[field],
                                                               structure.interface.category, field)
                        intf.callback = True
                        self.categories[intf.category]["callbacks"][intf.identifier] = intf
                    elif structure.fields[field].type_class == "struct":
                        self.__process_unmatched_structure(structure.fields[field])

                    if structure.fields[field].interface and field not in structure.interface.fields:
                        structure.interface.fields[field] = structure.fields[field].interface.identifier
                    # todo: Check that no conflicts can occur there
            else:
                self.logger.debug("Field {} is recognized as an interface {}".
                                  format(field, structure.fields[field].interface.full_identifier))

        self.logger.debug("Analize resources of matched function pointers")
        for callback_id in self.categories[structure.interface.category]["callbacks"]:
            callback = self.categories[structure.interface.category]["callbacks"][callback_id]
            self.logger.debug("Check types of parameters of callback {} from category {}".
                              format(callback_id, structure.interface.category))
            self.__match_function_parameters(callback.signature)

            for parameter in [p for p in callback.signature.parameters if p and not p.interface and
                              p.type_class == "struct"]:
                cnds = []
                # Check relevance of creating new resource
                for function in [self.kernel_functions[name].signature for name in self.kernel_functions] +\
                                [structure.fields[name] for name in structure.fields if
                                 structure.fields[name].type_class == "function"]:
                    cnds.extend([p for p in function.parameters if p and p.type_class == parameter.type_class and
                                 p.structure_name == parameter.structure_name])

                if len(cnds) > 0:
                    self.logger.debug("Introduce new resource on base of a parameter {} of callback {}".
                                      format(parameter, callback.full_identifier))
                    interface = self.__make_intf_from_signature(parameter, callback.category)
                    interface.resource = True
                    self.categories[interface.category]["resources"][interface.identifier] = interface

    def __make_intf_from_signature(self, signature, category, identifier=None):
        if not identifier:
            if signature.type_class == "struct":
                name = signature.structure_name
            elif signature.type_class == "function" and signature.function_name:
                name = signature.function_name
            else:
                name = "primitive"

            if "{}.{}".format(category, name) not in self.interfaces:
                identifier = name
            else:
                name = "emg_{}".format(name)
                cnt = 0
                while "{}.{}_{}".format(category, name, cnt) in self.interfaces:
                    cnt += 1
                identifier = "{}_{}".format(name, cnt)

        intf = Interface(signature.expression, category, identifier, None)
        intf.signature = signature
        signature.interface = intf
        if intf.full_identifier not in self.interfaces:
            self.interfaces[intf.full_identifier] = intf
        else:
            raise KeyError("Cannot add interface {}".format(intf.full_identifier))

        self.logger.debug("Introduce new interface {} on base of signature {}".
                          format(intf.full_identifier, signature.expression))

        self.__mark_existing_interfaces()
        return intf

    def _yield_new_category(self, name):
        if name in self.categories:
            name = "emg_{}".format(name)
            if name in self.categories:
                cnt = 0
                while "{}_{}".format(name, cnt) in self.categories:
                    cnt += 1
                name = "{}_{}".format(name, cnt)

        self.categories[name] = {
            "containers": {},
            "callbacks": {},
            "resources": {},
        }

        self.logger.debug("Introduce new interface category {}".format(name))
        return name

    def __process_unmatched_structure(self, structure):
        fp = []
        intfs = []
        matched = False
        self.logger.debug("Process structure fields of structure {} which is not matched with any interface".
                          format(structure.expression))
        for field in structure.fields:
            if not structure.fields[field].interface:
                if structure.fields[field].type_class == "function":
                    fp.append(structure.fields[field])
                elif structure.fields[field].type_class == "struct":
                    if self.__process_unmatched_structure(structure.fields[field]):
                        intfs.append(structure.fields[field].interface)
            else:
                intfs.append(structure.fields[field].interface)

        if len(intfs) != 0:
            self.logger.debug("{} fields are matched with interfaces".
                              format(len(intfs), structure.expression))
            probe_intf = intfs[0]
            same = [intf for intf in intfs if intf.category == probe_intf.category]
            if len(same) != len(intfs):
                raise RuntimeError("Expect single suitable category for structure variable {}".
                                   format(structure.expression))

            category = same[0].category
            identifier = structure.structure_name
            interface = self.__make_intf_from_signature(structure.expression, category, identifier)
            interface.container = True
            self.categories[interface.category]["containers"][interface.identifier] = interface
            matched = True
        elif len(fp) != 0:
            self.logger.debug("Found {} function pointers in structure variable {} fields".
                              format(len(fp), structure.expression))
            category = self._yield_new_category(structure.structure_name)

            identifier = structure.structure_name
            interface = self.__make_intf_from_signature(structure, category, identifier)
            interface.container = True
            self.categories[interface.category]["containers"][interface.identifier] = interface
            matched = True

        if matched:
            self.logger.debug("Match structure variable {} with an interface {}".
                              format(structure.expression, structure.interface.full_identifier))
            # Process content of the structure
            self.__process_matched_structure(structure)
        return matched

    def __parse_elements_signatures(self, elements):
        for element in list(elements.keys()):
            if elements[element]["type"] in ["struct", "function pointer"]:
                elements[element]["signature"] = Signature(elements[element]["signature"])

                if elements[element]["type"] in ["array", "struct"]:
                    self.__parse_elements_signatures(elements[element]["fields"])
                    for field in elements[element]["fields"]:
                        elements[element]["signature"].fields[field] = elements[element]["fields"][field]["signature"]
                    del elements[element]["fields"]
                elif elements[element]["type"] == "function pointer":
                    self.__convert_collateral_signatures(elements[element])
                    elements[element]["signature"].function_name = None
            else:
                # todo: need to support arrays, pointer to pointer, etc.
                # todo: array elements doesn't have attribute fields, they have attribute elements, e.g.
                # todo: for drivers/usb/gadget/g_audio.ko, drivers/usb/gadget/g_webcam.ko.
                del elements[element]

    def __convert_collateral_signatures(self, function):
        self.logger.debug("Convert collateral signatures of function description {}".
                          format(function["signature"].expression))

        self.logger.debug("Convert return value {} to signature".format(function["return value type"]))
        function["signature"].return_value = Signature(function["return value type"])
        del function["return value type"]

        function["signature"].parameters = []
        for parameter in function["parameters"]:
            self.logger.debug("Convert parameter {} to signature".format(parameter))
            function["signature"].parameters.append(Signature(parameter))

        self.logger.debug("Delete all collateral data in function description except function signature {}".
                          format(function["signature"].expression))
        del function["parameters"]

    def __parse_signatures_as_is(self):
        self.logger.debug("Parse signatures in source analysis")

        self.logger.debug("Parse signatures of kernel functions")
        for function in self.analysis["kernel functions"]:
            self.logger.debug("Parse signature of function {}".format(function))
            self.analysis["kernel functions"][function]["signature"] = \
                Signature(self.analysis["kernel functions"][function]["signature"])
            self.__convert_collateral_signatures(self.analysis["kernel functions"][function])
            self.analysis["kernel functions"][function]["signature"].function_name = function

        self.logger.debug("Parse modules functions signatures")
        for function in self.analysis["modules functions"]:
            for path in self.analysis["modules functions"][function]["files"]:
                self.logger.debug("Parse signature of function {} from file {}".format(function, path))
                self.analysis["modules functions"][function]["files"][path]["signature"] = \
                    Signature(self.analysis["modules functions"][function]["files"][path]["signature"])
                self.__convert_collateral_signatures(self.analysis["modules functions"][function]["files"][path])
                self.analysis["modules functions"][function]["files"][path]["signature"].function_name = function

        self.logger.debug("Parse global variables signatures")
        for path in self.analysis["global variable initializations"]:
            for variable in list(self.analysis["global variable initializations"][path].keys()):
                self.logger.debug("Parse signature of global variable {} from file {}".format(function, path))

                if "type" not in self.analysis["global variable initializations"][path][variable]:
                    var_description = self.analysis["global variable initializations"][path][variable]

                    # Create new signature
                    var_description["signature"] = \
                        Signature(var_description["signature"])

                    # Parse arrays and structures
                    # todo: implement array parsing

                    # Add implementations
                    if path not in self.implementations:
                        self.implementations[path] = {}
                    self.implementations[path][variable] = {}

                    self.logger.debug("Parse fields of global variable {} from file {}".format(function, path))
                    self.__parse_elements_signatures(var_description["fields"])
                    for field in var_description["fields"]:
                        if "value" in var_description["fields"][field]:
                            self.implementations[path][variable][field] = var_description["fields"][field]["value"]
                        else:
                            self.logger.warning("Field {} from description of variable {} from {} has no value".
                                                format(field, variable, path))

                        if "signature" in var_description["fields"][field]:
                            var_description["signature"].fields[field] = var_description["fields"][field]["signature"]
                        else:
                            raise KeyError("Signature of field {} in description of variable {} from {} os not given".
                                           format(field, variable, path))

                    self.logger.debug("Remove legacy data about initialization of variable {} from file {}".
                                      format(function, path))
                    del var_description["fields"]

                    # Keep only signature
                    # todo: Save values
                    self.analysis["global variable initializations"][path][variable] = var_description["signature"]
                else:
                    self.logger.warning(
                            "Cannot process global variable with type {}".
                            format(self.analysis["global variable initializations"][path][variable]["type"]))
                    del self.analysis["global variable initializations"][path][variable]

    def __match_rest_elements(self, root_element):
        for element in root_element.fields:
            if not root_element.fields[element].interface and not root_element.fields[element].type_class == "function":
                interfaces = [self.interfaces[intf] for intf in self.interfaces
                              if self.interfaces[intf].category == root_element.interface.category and
                              self.interfaces[intf].signature.type_class == root_element.fields[element].type_class]
                for intf in interfaces:
                    if root_element.fields[element].compare_signature(intf.signature):
                        root_element.fields[element].interface = intf
                        if root_element.fields[element].type_class == "struct":
                            self.__match_rest_elements(root_element.fields[element])

    def __match_function_parameters(self, function):
        structs_and_funcs = [self.interfaces[name] for name in self.interfaces
                             if self.interfaces[name].signature.type_class == "struct" or
                             self.interfaces[name].signature.type_class == "function"]

        if function.return_value and not function.return_value.interface:
            for intf in structs_and_funcs:
                if intf.signature.compare_signature(function.return_value):
                    self.logger.debug("Match return value type {} with an interface {}".
                                      format(function.return_value.expression, intf.full_identifier))
                    function.return_value.interface = intf
                    break

        for parameter in function.parameters:
            if parameter and not parameter.interface:
                for intf in structs_and_funcs:
                    if intf.signature.compare_signature(parameter):
                        self.logger.debug("Match parameter type {} with an interface {}".
                                          format(parameter.expression, intf.full_identifier))
                        parameter.interface = intf
                        break

    def __mark_existing_interfaces(self):
        self.logger.debug("Mark function arguments of already described kernel functions as existing interfaces")
        for function in self.analysis["kernel functions"]:
            self.logger.debug("Analyze collateral signatures of kernel function {}".format(function))
            function_signature = self.analysis["kernel functions"][function]["signature"]
            if function in self.kernel_functions:
                self.logger.debug("Found description of function {} in existing specification".format(function))
                existing_signature = self.kernel_functions[function].signature
                function_signature.interface = self.kernel_functions[function]
                if function_signature.return_value and not function_signature.return_value.interface and \
                   existing_signature.return_value and existing_signature.return_value.interface:
                    function_signature.return_value.interface = existing_signature.return_value.interface

                for index in range(len(function_signature.parameters)):
                    if not function_signature.parameters[index].interface and existing_signature.parameters[index] and\
                       existing_signature.parameters[index].interface:
                        function_signature.parameters[index].interface = existing_signature.parameters[index].interface
            else:
                self.__match_function_parameters(function_signature)

        self.logger.debug("Mark already described containers as existing interfaces")
        for path in self.analysis["global variable initializations"]:
            for variable in self.analysis["global variable initializations"][path]:
                # Compare with containers
                for category in self.categories:
                    self.logger.debug("Try match variable {} with category {}".format(variable, category))
                    for container in self.categories[category]["containers"]:
                        if self.categories[category]["containers"][container].signature.\
                                compare_signature(self.analysis["global variable initializations"][path][variable]):
                            self.analysis["global variable initializations"][path][variable].interface = \
                                self.categories[category]["containers"][container]
                            break
                    if self.analysis["global variable initializations"][path][variable].interface:
                        break

                if self.analysis["global variable initializations"][path][variable].interface:
                    identifier = self.analysis["global variable initializations"][path][variable].interface.\
                        full_identifier
                    expression = self.analysis["global variable initializations"][path][variable].expression
                    self.logger.debug("Match variable {} from {} with type {} with container {}".
                                      format(variable, path, expression, identifier))
                    self.__match_rest_elements(
                        self.analysis["global variable initializations"][path][variable])
                else:
                    # Compare with resources
                    for category in self.categories:
                        for resource in self.categories[category]["resources"]:
                            if self.categories[category]["resources"][resource].signature.\
                                compare_signature(
                                    self.analysis["global variable initializations"][path][variable]):
                                self.analysis["global variable initializations"][path][variable].interface = \
                                    self.categories[category]["resources"][resource]
                                break

                        if self.analysis["global variable initializations"][path][variable].interface:
                            identifier = self.analysis["global variable initializations"][path][variable].interface.\
                                full_identifier
                            expression = self.analysis["global variable initializations"][path][variable].expression
                            self.logger.debug("Match variable {} from {} with type {} with resource {}".
                                              format(variable, path, expression, identifier))
                            break

    def __remove_categories(self):
        # Remove categories without implementations
        self.logger.info("Remove interface categories which has no interface implementations or relevant interfaces")
        categories = list(self.categories.keys())
        for category in categories:
            relevant_functions = []
            relevant_interfaces = []
            ref_categories = []

            # If category interfaces are not used in kernel functions it means that this structure is not transferred to
            # the kernel or just source analysis cannot find all containers
            for name in self.kernel_functions:
                if self.kernel_functions[name]["signature"].return_value.interface and \
                        self.kernel_functions[name]["signature"].return_value.interface.category == category:
                    relevant_functions.append(name)
                    relevant_interfaces.append(self.kernel_functions[name]["signature"].return_value.interface)
                else:
                    for parameter in self.kernel_functions[name]["signature"].parameters:
                        if parameter.interface and \
                                parameter.interface.category == category:
                            relevant_functions.append(name)
                            relevant_interfaces.append(parameter.interface)
                            break

            # Check interfaces from the other categories
            for cat in [self.categories[name] for name in self.categories if name != category]:
                # Check that callbacks from other categories refer interfaces from the category
                for callback in cat["callbacks"].values():
                    if callback.signature.return_value and callback.signature.return_value.interface and \
                            callback.signature.return_value.interface.category == category:
                        relevant_interfaces.append(callback.signature.return_value.interface)
                        ref_categories.append(callback.category)

                    for parameter in [p for p in callback.signature.parameters if p and p.interface and
                                      p.interface.category == category]:
                        relevant_interfaces.append(parameter.interface)
                        ref_categories.append(callback.category)

                # todo: Check that containers from other categories refer interfaces from this category

            if len(relevant_functions) == 0 and len(relevant_interfaces) == 0:
                self.logger.debug("Remove interface category {}".format(category))
                intfs = [intf for intf in (list(self.categories[category]["containers"].keys()) +
                                           list(self.categories[category]["resources"].keys()) +
                                           list(self.categories[category]["callbacks"].keys()))]
                for intf in intfs:
                    if "{}.{}".format(category, intf) in self.interfaces:
                        del self.interfaces["{}.{}".format(category, intf)]
                del self.categories[category]
            else:
                self.logger.debug("Keep interface category {}".format(category))


class SpecEncoder(json.JSONEncoder):

    def default(self, object):
        fd = {}

        if type(object) is ModuleSpecification:
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
