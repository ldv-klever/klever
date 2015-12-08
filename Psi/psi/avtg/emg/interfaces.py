import re
import copy

fi_regex = re.compile("(\w*)\.(\w*)")
fi_extract = re.compile("\*?%((?:\w*\.)?\w*)%")


def is_full_identifier(string):
    """Check that string is a correct full interface identifier."""
    if fi_regex.fullmatch(string) and len(fi_regex.fullmatch(string).groups()) == 2:
        return True
    else:
        False


def extract_full_identifier(string):
    """Extract full identifier from a given string."""
    if is_full_identifier(string):
        category, identifier = fi_regex.fullmatch(string).groups()
        return category, identifier
    else:
        raise ValueError("Given string {} is not a full identifier".format(string))


class CategorySpecification:

    def __init__(self, logger):
        self.logger = logger
        self.categories = {}
        self.interfaces = {}
        self.kernel_functions = {}
        self.kernel_macro_functions = {}
        self.kernel_macros = {}

    def import_specification(self, specification):
        self.logger.info("Import interface categories specification")
        for category in specification["categories"]:
            self.logger.debug("Import interface category {}".format(category))
            self.__import_category_interfaces(category, specification["categories"][category])

        if "kernel functions" in specification:
            self.logger.info("Import kernel functions")
            for intf in self.__import_kernel_interfaces("kernel functions", specification):
                self.kernel_functions[intf.identifier] = intf
        else:
            self.logger.warning("Kernel functions are not provided in interface categories specification, "
                                "expect 'kernel functions' attribute")

        if "kernel macro-functions" in specification:
            self.logger.info("Import kernel macro-functions")
            for intf in self.__import_kernel_interfaces("kernel macro-functions", specification):
                self.kernel_macro_functions[intf.identifier] = intf
        else:
            self.logger.warning("Kernel functions are not provided in interface categories specification, "
                                "expect 'kernel macro-functions' attribute")

        # Populate signatures instead of Interface signatures and assign interface links
        self.logger.info("Remove Interface Signature objects and establish references to Interface objects instead")
        for intf in self.interfaces:
            self.interfaces[intf].signature = self._process_signature(self.interfaces, self.interfaces[intf].signature)

            # Check fields in case of container
            if not self.interfaces[intf].container and self.interfaces[intf].signature.type_class == "struct":
                # Fields matter for containers only, do not keep unnecessary date
                self.interfaces[intf].signature.fields = {}

        for function in self.kernel_functions:
            self.kernel_functions[function].signature = \
                self._process_signature(self.kernel_functions, self.kernel_functions[function].signature)

    def _process_signature(self, collection, signature):
        # Replace string interface definition by reference
        if signature.interface and type(signature.interface) is str:
            signature.interface = collection[signature.interface]
        # Replace Interface signature
        if signature.type_class == "interface":
            if signature.interface.signature.type_class == "interface":
                raise RuntimeError("Attempt to replace interface signature with an interface signature")
            signature = Signature.copy_signature(signature, signature.interface.signature)
        # Process return value and parameters in case of function
        if signature.type_class == "function":
            if signature.return_value:
                signature.return_value = self._process_signature(self.interfaces, signature.return_value)
            for index in range(len(signature.parameters)):
                if type(signature.parameters[index]) is Signature:
                    signature.parameters[index] = self._process_signature(self.interfaces, signature.parameters[index])
        # Check fields in case of structure
        elif signature.type_class == "struct":
            if len(signature.fields) > 0:
                for field in signature.fields:
                    signature.fields[field] = self._process_signature(self.interfaces, signature.fields[field])
        elif signature.type_class == "interface":
            raise RuntimeError("Cannot replace signature {} with an interface".format(signature.expression))
        return signature

    @staticmethod
    def __import_kernel_interfaces(category_name, collection):
        for identifier in collection[category_name]:
            if "signature" not in collection[category_name][identifier]:
                raise TypeError("Specify 'signature' for kernel interface {} at {}".format(identifier, category_name))
            elif "header" not in collection[category_name][identifier]:
                raise TypeError("Specify 'header' for kernel interface {} at {}".format(identifier, category_name))
            intf = Interface(collection[category_name][identifier]["signature"],
                             "kernel",
                             identifier,
                             collection[category_name][identifier]["header"],
                             True)
            intf.category = category_name
            intf.signature.interface = intf.identifier
            if intf.signature.function_name and intf.signature.function_name != identifier:
                raise ValueError("Kernel function name {} does not correspond its signature {}".
                                 format(identifier, intf.signature.expression))
            elif not intf.signature.function_name:
                raise ValueError("Kernel function name {} is not a macro or a function".
                                 format(identifier, intf.signature.expression))
            yield intf

    def __import_interfaces(self, category_name, collection):
        for intf_identifier in collection:
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
        if category_name in self.categories:
            self.logger.warning("Category {} has been already defined in inteface category specification".
                                format(category_name))
        else:
            self.categories[category_name] = {
                "containers": {},
                "resources": {},
                "callbacks": {}
            }

        if "containers" in dictionary:
            self.logger.debug("Import containers of the interface category {}".format(category_name))
            for intf in self.__import_interfaces(category_name, dictionary["containers"]):
                if intf and intf.full_identifier not in self.interfaces:
                    self.logger.debug("Imported new identifier description {}".format(intf.full_identifier))
                    self.interfaces[intf.full_identifier] = intf
                    intf.container = True
                    self.categories[intf.category]["containers"][intf.identifier] = intf
                elif intf and intf.full_identifier in self.interfaces:
                    self.logger.debug("Imported existing identifier description {}".format(intf.full_identifier))
                    intf.container = True
        if "resources" in dictionary:
            self.logger.debug("Import resources of the interface category {}".format(category_name))
            for intf in self.__import_interfaces(category_name, dictionary["resources"]):
                if intf and intf.full_identifier not in self.interfaces:
                    self.logger.debug("Imported new identifier description {}".format(intf.full_identifier))
                    intf.resource = True
                    self.interfaces[intf.full_identifier] = intf
                    self.categories[intf.category]["resources"][intf.identifier] = intf
                elif intf and intf.full_identifier in self.interfaces:
                    self.logger.debug("Imported existing identifier description {}".format(intf.full_identifier))
                    intf.resource = True
        if "callbacks" in dictionary:
            self.logger.debug("Import callbacks of the interface category {}".format(category_name))
            for intf in self.__import_interfaces(category_name, dictionary["callbacks"]):
                if intf and intf.full_identifier not in self.interfaces:
                    self.logger.debug("Imported new identifier description {}".format(intf.full_identifier))
                    intf.callback = True
                    self.interfaces[intf.full_identifier] = intf
                    self.categories[intf.category]["callbacks"][intf.identifier] = intf
                elif intf and intf.full_identifier in self.interfaces:
                    self.logger.debug("Imported existing identifier description {}".format(intf.full_identifier))
                    intf.callback = True


class ModuleSpecification(CategorySpecification):

    def import_specification(self, specification={}, categories=None, analysis={}):
        self.implementations = {}

        # Import categories
        self.categories = categories.categories
        self.interfaces = categories.interfaces
        self.kernel_functions = categories.kernel_functions
        self.kernel_macro_functions = categories.kernel_macro_functions
        self.kernel_macros = categories.kernel_macros
        self.analysis = analysis

        # Import categories from modules specification
        super().import_specification(specification)

        # TODO: import existing module specification

        # Import source analysis
        self.__import_source_analysis()

    def __import_source_analysis(self):
        self.logger.info("Start processing source code amnalysis data")
        self.__parse_signatures_as_is()

        self.logger.debug("Mark all types as interfaces if there are already specified")
        self.__mark_existing_interfaces()

        self.logger.debug("Determine more interfaces from existng data in source analysis data")
        self.__add_more_interfaces()

        self.logger.debug("Finally mark all types as interfaces if there are already specified")
        self.__mark_existing_interfaces()

        self.logger.debug("Add implementations to existing interfaces from source code analysis")
        self.__add_implementations_from_analysis()

        return

    def __add_implementations_from_analysis(self):
        # TODO: Implement import of implementations
        return

    def __add_more_interfaces(self):
        # Extract more containers from structures with callbacks
        self.logger.info("Extract more interfaces from matched containers")
        for path in self.analysis["global variable initializations"]:
            for variable in self.analysis["global variable initializations"][path]:
                var_desc = self.analysis["global variable initializations"][path][variable]
                if not var_desc.interface:
                    self.__process_unmatched_structure(var_desc)
                elif var_desc.interface and var_desc.interface.container:
                    self.__process_matched_structure(var_desc)

    def __process_matched_structure(self, structure):
        self.logger.debug("Extract interfaces from structure variable {}".format(structure.expression))
        self.logger.debug("Analize function pointers and structure in structure variable fields")
        for field in structure.fields:
            if not structure.fields[field].interface:
                if structure.fields[field].type_class == "function":
                    intf = self.__make_intf_from_signature(structure.fields[field], structure.interface.category, field)
                    intf.callback = True
                    self.categories[intf.category]["callbacks"][intf.identifier] = intf
                elif structure.fields[field].type_class == "struct":
                    self.__process_unmatched_structure(structure.fields[field])

        self.logger.debug("Analize resources of matched function pointers")
        for callback_id in self.categories[structure.interface.category]["callbacks"]:
            callback = self.categories[structure.interface.category]["callbacks"][callback_id]
            for parameter in callback.signature.parameters:
                if not parameter.interface:
                    self.logger.debug("Check suitable resource interface for parameter {} of callback {}".
                                      format(parameter, callback.full_identifier))
                    if parameter.type_class == "struct" \
                            and parameter.structure_name in self.categories[callback.category]["resources"]:
                        intf_name = parameter.structure_name
                        parameter.interface = self.categories[callback.category]["resources"][intf_name]
                    elif parameter.type_class == "function" and parameter.function_name and parameter.function_name \
                            in self.categories[callback.category]["resources"]:
                        intf_name = parameter.function_name
                        parameter.interface = self.categories[callback.category]["resources"][intf_name]
                    elif parameter.type_class == "function" and parameter.function_name and parameter.function_name \
                            not in self.categories[callback.category]["resources"] and \
                                    parameter.function_name in self.categories[callback.category]["callbacks"]:
                        intf_name = parameter.function_name
                        intf_name.resource = True
                        self.categories[intf_name.category]["resources"][intf_name] = \
                            self.categories[callback.category]["callbacks"][intf_name]
                        parameter.interface = self.categories[callback.category]["callbacks"][intf_name]
                    else:
                        self.logger.debug("Introduce new resource on base of parameter {} of callback {}".
                                          format(parameter, callback.full_identifier))
                        new_identifier = self._yield_new_identifier(callback.category, parameter)
                        interface = self.__make_intf_from_signature(callback.signature,
                                                                    callback.category, new_identifier)
                        interface.resource = True
                        self.categories[interface.category]["resources"][interface.identifier] = interface

    def __make_intf_from_signature(self, signature, category, identifier):
        intf = Interface(signature.expression, category, identifier, None)
        intf.signature = signature
        signature.interface = intf
        if intf.full_identifier not in self.interfaces:
            self.interfaces[intf.full_identifier] = intf
        else:
            raise KeyError("Cannot add interface {}".format(intf.full_identifier))
        return intf

    def __process_unmatched_structure(self, structure):
        fp = []
        intfs = []
        matched = False
        self.logger.debug("Process unmatched straucture {}".format(structure.expression))
        for field in structure.fields:
            self.logger.debug("Process unmatched structure variable {} field {}".format(structure.expression, field))
            if not structure.fields[field].interface:
                if structure.fields[field].type_class == "function":
                    fp.append(structure.fields[field])
                elif structure.fields[field].type_class == "struct":
                    if self.__process_unmatched_structure(structure.fields[field]):
                        intfs.append(structure.fields[field].interface)
            else:
                intfs.append(structure.fields[field].interface)

        if len(intfs) != 0:
            self.logger.debug("Found {} interfaces in structure variable {} fields".
                              format(len(intfs), structure.expression))
            probe_intf = intfs[0]
            same = [intf for intf in intfs if intf.category == probe_intf.category]
            if len(same) != len(intfs):
                raise RuntimeError("Cannot determine signle category for structure variable {}".format(structure.expression))
            category = same.category
            identifier = structure.structure_name
            interface = self.__make_intf_from_signature(structure.expression, category, identifier)
            interface.container = True
            self.categories[interface.category]["containers"][interface.identifier] = interface
            matched = True
        elif len(fp) != 0:
            self.logger.debug("Found {} function pointerrs in structure variable {} fields".
                              format(len(fp), structure.expression))
            category = self._yield_new_category()
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

    def _yield_new_identifier(self, category, signature):
        name = None
        if signature.type_class == "struct":
            name = signature.structure_name
        elif signature.type_class == "function" and signature.function_name:
            name = signature.function_name
        elif signature.type_class == "primitive":
            name = "primitive"

        if not name:
            name = "klever_intf"

        final_name = name
        cnt = 0
        while "{}.{}".format(category, final_name) in self.interfaces:
            cnt += 1
            final_name = "{}_{}".format(name, cnt)
        return final_name

    def _yield_new_category(self):
        cnt = 0
        name = "yielded_category_{}".format(cnt)
        while name in self.categories:
            cnt += 1
            name = "yielded_category_{}".format(cnt)
        self.categories[name] = {
            "containers": {},
            "callbacks": {},
            "resources": {},
        }
        return name

    def __parse_elements_signatures(self, elements):
        for element in elements:
            elements[element]["signature"] = \
                Signature(elements[element]["signature"])

            if elements[element]["type"] in ["array", "struct"]:
                self.__parse_elements_signatures(elements[element]["fields"])
                for field in elements[element]["fields"]:
                    elements[element]["signature"].fields[field] = elements[element]["fields"][field]["signature"]
                del elements[element]["fields"]
            elif elements[element]["type"] == "function pointer":
                self.__process_function_signature(elements[element])
                elements[element]["signature"].function_name = None

    @staticmethod
    def __process_function_signature(function):
        function["signature"].return_value = Signature(function["return value type"])
        del function["return value type"]

        function["signature"].parameters = []
        for parameter in function["parameters"]:
            function["signature"].parameters.append(Signature(parameter))
        del function["parameters"]

    def __parse_signatures_as_is(self):
        self.logger.debug("Pase signatures in source analysis")

        self.logger.debug("Parse kernel functions signatures")
        for function in self.analysis["kernel functions"]:
            self.logger.debug("Parse signature of function {}".format(function))
            self.analysis["kernel functions"][function]["signature"] = \
                Signature(self.analysis["kernel functions"][function]["signature"])
            self.__process_function_signature(self.analysis["kernel functions"][function])
            self.analysis["kernel functions"][function]["signature"].function_name = function

        self.logger.debug("Parse modules functions signatures")
        for function in self.analysis["modules functions"]:
            for path in self.analysis["modules functions"][function]["files"]:
                self.logger.debug("Parse signature of function {} from file {}".format(function, path))
                self.logger.debug("Parse signature of function {}".format(function))
                self.analysis["modules functions"][function]["files"][path]["signature"] = \
                    Signature(self.analysis["modules functions"][function]["files"][path]["signature"])
                self.__process_function_signature(self.analysis["modules functions"][function]["files"][path])
                self.analysis["modules functions"][function]["files"][path]["signature"].function_name = function

        self.logger.debug("Parse global variables signatures")
        for path in self.analysis["global variable initializations"]:
            for variable in self.analysis["global variable initializations"][path]:
                self.logger.debug("Parse signature of global variable {} from file {}".format(function, path))
                # Create new signature
                self.analysis["global variable initializations"][path][variable]["signature"] = \
                    Signature(self.analysis["global variable initializations"][path][variable]["signature"])

                # Parse arrays and structures
                # todo: implement array parsing
                self.__parse_elements_signatures(
                    self.analysis["global variable initializations"][path][variable]["fields"])
                for field in self.analysis["global variable initializations"][path][variable]["fields"]:
                    self.analysis["global variable initializations"][path][variable]["signature"].fields[field] = \
                        self.analysis["global variable initializations"][path][variable]["fields"][field]["signature"]
                del self.analysis["global variable initializations"][path][variable]["fields"]

                # Keep only signature
                self.analysis["global variable initializations"][path][variable] = \
                    self.analysis["global variable initializations"][path][variable]["signature"]

    def __match_rest_elements(self, root_element):
        for element in root_element.fields:
            interfaces = [self.interfaces[intf] for intf in self.interfaces
                          if self.interfaces[intf].category == root_element.interface.category and
                          self.interfaces[intf].signature.type_class == root_element.fields[element].type_class]
            for intf in interfaces:
                if root_element.fields[element].compare_signature(intf.signature):
                    root_element.fields[element].interface = intf
                    if root_element.fields[element].type_class == "struct":
                        self.__match_rest_elements(root_element.fields[element])

    def __mark_existing_interfaces(self):
        self.logger.debug("Mark already described kernel functions as existing interfaces")

        self.logger.debug("Mark function arguments of already described kernel functions as existing interfaces")
        for function in self.analysis["kernel functions"]:
            if function in self.kernel_functions:
                self.analysis["kernel functions"][function]["signature"].interface = self.kernel_functions[function]
                if self.analysis["kernel functions"][function]["signature"].return_value and \
                   not self.analysis["kernel functions"][function]["signature"].return_value.interface and \
                   self.kernel_functions[function].signature.return_value and \
                   self.kernel_functions[function].signature.return_value.interface:
                    self.analysis["kernel functions"][function]["signature"].return_value.interface = \
                        self.kernel_functions[function].signature.return_value.interface

                for index in range(len(self.analysis["kernel functions"][function]["signature"].parameters)):
                    if not self.analysis["kernel functions"][function]["signature"].parameters[index].interface and \
                       self.kernel_functions[function].signature.parameters[index].interface:
                        self.analysis["kernel functions"][function]["signature"].parameters[index].interface = \
                            self.kernel_functions[function].signature.parameters[index].interface
        self.logger.debug("Mark already described containers as existing interfaces")
        for path in self.analysis["global variable initializations"]:
            for variable in self.analysis["global variable initializations"][path]:
                # Compare with containers
                for category in self.categories:
                    for container in self.categories[category]["containers"]:
                        if self.categories[category]["containers"][container].signature.\
                            compare_signature(
                                self.analysis["global variable initializations"][path][variable]):
                            self.analysis["global variable initializations"][path][variable].interface = \
                                self.categories[category]["containers"][container]
                            break
                    if self.analysis["global variable initializations"][path][variable].interface:
                        break
                if self.analysis["global variable initializations"][path][variable].interface:
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
                            break

    def __establish_references(self):
        # Import confirmed container implementations
        name_re = re.compile("%name%")
        for file in self.analysis["global variable initializations"]:
            for var_name in self.analysis["global variable initializations"][file]:
                variable = self.analysis["global variable initializations"][file][var_name]
                for intf in self.interfaces:
                    if variable["signature"] == self.interfaces[intf].signature.expression:
                        if file not in self.interfaces[intf].implementations:
                            self.interfaces[intf].implementations[file] = {}
                        if var_name not in self.interfaces[intf].implementations[file]:
                            # Extend field types
                            # Submit implementation
                            for field in [field for field in variable["fields"] if
                                          variable["fields"][field]["type"] == "function pointer"]:
                                identifier = "{}.{}".format(self.interfaces[intf].category, field)
                                # Replace function name
                                new_expr = name_re.sub("%{}%".format(identifier),
                                                       variable["fields"][field]["signature"])
                                if identifier not in self.interfaces:
                                    new = Interface(new_expr,
                                                    self.interfaces[intf].category,
                                                    field,
                                                    None)
                                    new.callback = True
                                    new.category = self.interfaces[intf].category
                                    new.full_identifier = identifier
                                    new.identifier = field
                                    self.interfaces[new.full_identifier] = new


class Interface:

    def __init__(self, signature, category, identifier, header, implemented_in_kernel=False):
        self.signature = Signature(signature)
        self.header = header
        self.category = category
        self.identifier = identifier
        self.implemented_in_kernel = implemented_in_kernel
        self.resource = False
        self.callback = False
        self.container = False
        self.kernel_interface = False
        self.fields = {}
        self.implementations = {}

    @property
    def role(self, role=None):
        """Callback interfaces have roles which are identifiers actually."""
        if not self.callback:
            raise TypeError("Non-callback interface {} does not have 'role' attribute".format(self.identifier))

        if not role:
            return self.identifier
        else:
            self.identifier = role

    @property
    def full_identifier(self, full_identifier=None):
        """Full identifier looks like 'category.identifier'."""
        if not self.category and not full_identifier:
            raise ValueError("Cannot determine full identifier {} without interface category")
        elif full_identifier:
            category, identifier = extract_full_identifier(full_identifier)
            self.category = category
            self.identifier = identifier
        else:
            return "{}.{}".format(self.category, self.identifier)


class Signature:

    @staticmethod
    def copy_signature(old, new):
        """
        This method copy signature and removes extra information if flag is not given.

        :param old: Signature obkect to replace.
        :param new: Signature to assign.
        """
        cp = copy.deepcopy(new)
        cp.array = old.array
        cp.pointer = old.pointer
        cp.interface = old.interface
        return cp

    def compare_signature(self, signature):
        # Need this to compare with undefined arguments
        if not signature:
            return False

        # Be sure that the signature is not an interface
        if signature.type_class == "interface" or self.type_class == "interface":
            raise TypeError("Interface signatures cannot be compared")

        if self.type_class != signature.type_class:
            return False
        if self.interface and signature.interface and self.interface != signature.interface:
            return False

        if self.expression != signature.expression:
            if self.type_class == "function":
                if self.return_value.compare_signature(signature.return_value):
                    if len(self.parameters) == len(signature.parameters):
                        for param in range(len(self.parameters)):
                            if not self.parameters[param].compare_signature(signature.parameters[param]):
                                return False
                        return True
                    else:
                        return False
                else:
                    return False
            elif self.type_class == "struct":
                if len(self.fields.keys()) > 0 and len(signature.fields.keys()) > 0 \
                        and len(set(signature.fields.keys()).intersection(self.fields.keys())) > 0:
                    for param in self.fields:
                        if param in signature.fields:
                            if not self.fields[param].compare_signature(signature.fields[param]):
                                return False
                    for param in signature.fields:
                        if param in self.fields:
                            if not signature.fields[param].compare_signature(self.fields[param]):
                                return False
                    return True
                return False
        else:
            return True

    def __init__(self, expression):
        """
        Expect signature expression.
        :param expression:
        :return:
        """
        self.expression = expression
        self.type_class = None
        self.pointer = False
        self.array = False
        self.return_value = None
        self.interface = None
        self.function_name = None
        self.return_value = None
        self.parameters = None
        self.fields = None

        ret_val_re = "(?:\$|(?:void)|(?:[\w\s]*\*?%s)|(?:\*?%[\w.]*%)|(?:[^%]*))"
        identifier_re = "(?:(?:(\*?)%s)|(?:(\*?)%[\w.]*%)|(?:(\*?)\w*))(\s?\[\w*\])?"
        args_re = "(?:[^()]*)"
        function_re = re.compile("^{}\s\(?{}\)?\s?\({}\)\Z".format(ret_val_re, identifier_re, args_re))
        if function_re.fullmatch(self.expression):
            self.type_class = "function"
            groups = function_re.fullmatch(self.expression).groups()
            if (groups[0] and groups[0] != "") or (groups[1] and groups[1] != ""):
                self.pointer = True
            else:
                self.pointer = False
            if groups[2] and groups[2] != "":
                self.array = True
            else:
                self.array = False

        macro_re = re.compile("^\w*\s?\({}\)\Z".format(args_re))
        if macro_re.fullmatch(self.expression):
            self.type_class = "macro"
            self.pointer = False
            self.array = False

        struct_re = re.compile("^struct\s+(?:[\w|*]*\s)+(\**)%s\s?((?:\[\w*\]))?\Z")
        struct_name_re = re.compile("^struct\s+(\w+)")
        self.__check_type(struct_re, "struct")

        value_re = re.compile("^(\w*\s+)+(\**)%s((?:\[\w*\]))?\Z")
        self.__check_type(value_re, "primitive")

        interface_re = re.compile("^(\*?)%.*%\Z")
        if not self.type_class and interface_re.fullmatch(self.expression):
            self.type_class = "interface"

        if self.type_class in ["function", "macro"]:
            self.__extract_function_interfaces()
        if self.type_class == "interface":
            ptr = interface_re.fullmatch(self.expression).group(1)
            if ptr and ptr != "":
                self.pointer = True
            self.interface = fi_extract.fullmatch(self.expression).group(1)
        if self.type_class == "struct":
            self.fields = {}
            self.structure_name = struct_name_re.match(self.expression).group(1)

        if not self.type_class:
            raise ValueError("Cannot determine signature type (function, structure, primitive or interface) {}".
                             format(self.expression))

    def __check_type(self, regex, type_name):
        if not self.type_class and regex.fullmatch(self.expression):
            self.type_class = type_name
            groups = regex.fullmatch(self.expression).groups()
            if groups[0] and groups[0] != "":
                self.pointer = True
            else:
                self.pointer = False

            if groups[1] and groups[1] != "":
                self.array = True
            else:
                self.array = False

            return True
        else:
            return False

    def __extract_function_interfaces(self):
        identifier_re = "((?:\*?%s)|(?:\*?%[\w.]*%)|(?:\*?\w*))(?:\s?\[\w*\])?"
        args_re = "([^()]*)"

        if self.type_class == "function":
            ret_val_re = "(\$|(?:void)|(?:[\w\s]*\*?%s)|(?:\*?%[\w.]*%)|(?:[^%]*))"
            function_re = re.compile("^{}\s\(?{}\)?\s?\({}\)\Z".format(ret_val_re, identifier_re, args_re))

            if function_re.fullmatch(self.expression):
                ret_val, name, args = function_re.fullmatch(self.expression).groups()
            else:
                raise ValueError("Cannot parse function signature {}".format(self.expression))

            if ret_val in ["$", "void"] or "%" not in ret_val:
                self.return_value = None
            else:
                self.return_value = Signature(ret_val)
        else:
            identifier_re = "(\w*)"
            macro_re = re.compile("^{}\s?\({}\)\Z".format(identifier_re, args_re))

            if macro_re.fullmatch(self.expression):
                name, args = macro_re.fullmatch(self.expression).groups()
            else:
                raise ValueError("Cannot parse macro signature {}".format(self.expression))
        self.function_name = name

        self.parameters = []
        if args != "void":
            for arg in args.split(", "):
                if arg in ["$", "..."] or "%" not in arg:
                    self.parameters.append("None")
                else:
                    self.parameters.append(Signature(arg))

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
