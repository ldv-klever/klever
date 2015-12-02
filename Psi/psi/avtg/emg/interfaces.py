import re
import subprocess
import os
import json

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
    categories = {}
    interfaces = {}
    kernel_functions = {}
    kernel_macro_functions = {}
    kernel_macros = {}
    _logger = None

    def __init__(self, logger):
        self.logger = logger

    def import_specification(self, specification):
        self.logger.info("Import interface categories specification")
        for category in specification["categories"]:
            self.logger.debug("Import interface category {}".format(category))
            self._import_category_interfaces(category, specification["categories"][category])

        self.logger.info("Import resources from callbacks")
        for category in self.categories:
            for callback in self.categories[category]["callbacks"]:
                signature = self.categories[category]["callbacks"][callback].signature

                if signature.return_value:
                    if signature.return_value.interface and type(signature.return_value.interface) is str:
                        interface = signature.return_value.interface
                        if not is_full_identifier(interface):
                            interface = "{}.{}".format(category, interface)
                        if interface not in self.interfaces:
                            raise ValueError("Interface {} is referenced in the interface categories specification but "
                                             "it is not described there".format(interface))
                        else:
                            signature.return_value.interface = \
                                self.interfaces[interface]
                for arg in signature.parameters:
                    if arg and arg.interface and type(arg.interface) is str:
                        interface = arg.interface
                        if not is_full_identifier(interface):
                            interface = "{}.{}".format(category, interface)
                        if interface not in self.interfaces:
                            raise ValueError("Interface {} is referenced in the interface categories specification but "
                                             "it is not described there".format(interface))
                        else:
                            arg.interface = self.interfaces[interface]

            self.logger.info("Import interfaces from containers")
            for container in self.categories[category]["containers"]:
                for field in self.categories[category]["containers"][container].fields:
                    if type(self.categories[category]["containers"][container].fields[field]) is str:
                        identifier = self.categories[category]["containers"][container].fields[field]
                        if not is_full_identifier(identifier):
                            identifier = "{}.{}".format(category, identifier)
                        if identifier not in self.interfaces:
                            raise ValueError("Interface {} is referenced in the interface categories specification but "
                                             "it is not described there".format(identifier))
                        else:
                            self.categories[category]["containers"][container].fields[field] =\
                                self.interfaces[identifier]

        if "kernel functions" in specification:
            self.logger.info("Import kernel functions")
            for intf in self._import_kernel_interfaces("kernel functions", specification):
                self.kernel_functions[intf.identifier] = intf
        else:
            self.logger.warning("Kernel functions are not provided in interface categories specification, "
                                "expect 'kernel functions' attribute")

        if "kernel macro-functions" in specification:
            self.logger.info("Import kernel macro-functions")
            for intf in self._import_kernel_interfaces("kernel macro-functions", specification):
                self.kernel_functions[intf.identifier] = intf
        else:
            self.logger.warning("Kernel functions are not provided in interface categories specification, "
                                "expect 'kernel macro-functions' attribute")

        if "kernel macros" in specification:
            self.logger.info("Import kernel macro-functions")
            for intf in self._import_kernel_interfaces("kernel macro-functions", specification):
                self.kernel_functions[intf.identifier] = intf
        else:
            self.logger.warning("Kernel functions are not provided in interface categories specification, "
                                "expect 'kernel macro-functions' attribute")

    @staticmethod
    def _import_kernel_interfaces(category_name, collection):
        for identifier in collection[category_name]:
            if "signature" not in collection[category_name][identifier]:
                raise TypeError("Specify 'signature' for kernel interface {} at {}".format(name, category_name))
            elif "header" not in collection[category_name][identifier]:
                raise TypeError("Specify 'header' for kernel interface {} at {}".format(identifier, category_name))
            intf = Interface(collection[category_name][identifier]["signature"],
                             identifier,
                             collection[category_name][identifier]["header"],
                             True)
            intf.category = category_name
            if intf.signature.function_name and intf.signature.function_name != identifier:
                raise ValueError("Kernel function name {} does not correspond its signature {}".
                                 format(identifier, intf.signature.expression))
            elif not intf.signature.function_name:
                raise ValueError("Kernel function name {} is not a macro or a function".
                                 format(identifier, intf.signature.expression))
            yield intf

    @staticmethod
    def _import_interfaces(category_name, collection):
        for intf_identifier in collection:
            full_identifier = "{}.{}".format(category_name, intf_identifier)
            implmented_flag = False
            if "implemented in kernel" in collection[intf_identifier]:
                implmented_flag = True

            if "signature" not in collection[intf_identifier] and "header" not in collection[intf_identifier]:
                # Expect that it is just reference
                intf = Interface(None, intf_identifier)
                intf.category = category_name
                yield intf
            elif "signature" not in collection[intf_identifier]:
                raise TypeError("Provide 'signature' for interface {} at {}".format(intf_identifier, category_name))
            else:
                if "header" in collection[intf_identifier]:
                    header = collection[intf_identifier]["header"]
                else:
                    header = None

                intf = Interface(collection[intf_identifier]["signature"],
                                 intf_identifier,
                                 header,
                                 implmented_flag)
                intf.category = category_name

                if "fields" in collection[intf_identifier]:
                    intf.fields = collection[intf_identifier]["fields"]

                yield intf

    def _import_category_interfaces(self, category_name, dictionary):
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
            for intf in self._import_interfaces(category_name, dictionary["containers"]):
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
            for intf in self._import_interfaces(category_name, dictionary["resources"]):
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
            for intf in self._import_interfaces(category_name, dictionary["callbacks"]):
                if intf and intf.full_identifier not in self.interfaces:
                    self.logger.debug("Imported new identifier description {}".format(intf.full_identifier))
                    intf.callback = True
                    self.interfaces[intf.full_identifier] = intf
                    self.categories[intf.category]["callbacks"][intf.identifier] = intf
                elif intf and intf.full_identifier in self.interfaces:
                    self.logger.debug("Imported existing identifier description {}".format(intf.full_identifier))
                    intf.callback = True


class ModuleSpecification(CategorySpecification):
    implementations = {}
    analysis = {}

    def import_specification(self, specification={}, categories=None, analysis={}):
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
        self._import_source_analysis()

    def _import_source_analysis(self):
        self.logger.info("Start processing source code amnalysis data")
        self._parse_signatures_as_is()

        self.logger.debug("Mark all types as interfaces if there are already spercified")
        self._mark_existing_interfaces()

        self.logger.debug("Determine more interfaces from existng data in source analysis data")
        # TODO: Implementation
        self.logger.debug("Build more Interface objects and establish references between them")
        # TODO: Implementation

    def _parse_elements_signatures(self, elements):
        for element in elements:
            elements[element]["signature"] = \
                Signature(elements[element]["signature"])

            if elements[element]["type"] in ["array", "structure"]:
                self._parse_elements_signatures(elements[element]["value"])
            elif elements[element]["type"] == "function pointer":
                self._process_function_signature(elements[element])
                elements[element]["signature"].function_name = None

    @staticmethod
    def _process_function_signature(function):
        function["signature"].return_value = Signature(function["return value type"])
        del function["return value type"]

        function["signature"].parameters = []
        for parameter in function["parameters"]:
            function["signature"].parameters.append(Signature(parameter))
        del function["parameters"]

    def _parse_signatures_as_is(self):
        self.logger.debug("Pase signatures in source analysis")

        self.logger.debug("Parse kernel functions signatures")
        for function in self.analysis["kernel functions"]:
            self.logger.debug("Parse signature of function {}".format(function))
            self.analysis["kernel functions"][function]["signature"] = \
                Signature(self.analysis["kernel functions"][function]["signature"])
            self._process_function_signature(self.analysis["kernel functions"][function])
            self.analysis["kernel functions"][function]["signature"].function_name = function

        self.logger.debug("Parse modules functions signatures")
        for function in self.analysis["modules functions"]:
            for path in self.analysis["modules functions"][function]["files"]:
                self.logger.debug("Parse signature of function {} from file {}".format(function, path))
                self.logger.debug("Parse signature of function {}".format(function))
                self.analysis["modules functions"][function]["files"][path]["signature"] = \
                    Signature(self.analysis["modules functions"][function]["files"][path]["signature"])
                self._process_function_signature(self.analysis["modules functions"][function]["files"][path])
                self.analysis["modules functions"][function]["files"][path]["signature"].function_name = function

        self.logger.debug("Parse global variables signatures")
        for path in self.analysis["global variable initializations"]:
            for variable in self.analysis["global variable initializations"][path]:
                self.logger.debug("Parse signature of global variable {} from file {}".format(function, path))
                self.analysis["global variable initializations"][path][variable]["signature"] = \
                    Signature(self.analysis["global variable initializations"][path][variable]["signature"])

                self._parse_elements_signatures(
                    self.analysis["global variable initializations"][path][variable]["fields"])

    def _match_signature(self, signature):
        for interface in self.interfaces:
            if self.interfaces[interface].signature.expression == signature:
                return self.interfaces[interface]
        return None

    def _match_function_signature(self, function):
        intf = self._match_signature(function["return value type"])
        if intf:
            function["matched return value type"] = intf
            matched_retval = True
        else:
            matched_retval = False

        matched_params = 0
        function["matched parameters"] = []
        for param in function["parameters"]:
            intf = self._match_signature(param)
            if intf:
                function["matched parameters"].append(intf)
                matched_params += 1
            else:
                function["matched parameters"].append(None)

        if matched_retval and matched_params == len(function["parameters"]):
            return True

    def _mark_elements(self, fields):
        for name in fields:
            if fields[name]["type"] not in ["array", "structure"]:
                intf = self._match_signature(fields[name]["signature"])
                if intf:
                    fields[name]["matched"] = intf
            elif fields[name]["type"] == "array":
                self._mark_elements(fields[name]["elements"])
            elif fields[name]["type"] == "structure":
                self._mark_elements(fields[name]["elements"])
            else:
                raise NotImplementedError("Cannot process element of the type {}".format(fields[name]["type"]))

    def _mark_existing_interfaces(self):
        self.logger.debug("Mark already described kernel functions as existing interfaces")

        self.logger.debug("Mark function arguments of already described kernel functions as existing interfaces")
        for function in self.analysis["kernel functions"]:
            if function in self.kernel_functions:
                self.analysis["kernel functions"][function]["match"] = self.kernel_functions[function]
            else:
                self._match_function_signature(self.analysis["kernel functions"][function])

        self.logger.debug("Mark already described modules functions as existing interfaces")
        self.logger.debug("Mark function arguments of already described kernel functions as existing interfaces")
        for function in self.analysis["modules functions"]:
            for path in self.analysis["modules functions"][function]["files"]:
                self._match_function_signature(self.analysis["modules functions"][function]["files"][path])

        self.logger.debug("Mark already described containers as existing interfaces")
        for path in self.analysis["global variable initializations"]:
            for variable in self.analysis["global variable initializations"][path]:
                intf = self._match_signature(
                    self.analysis["global variable initializations"][path][variable]["signature"])
                if intf:
                    self.analysis["global variable initializations"][path][variable]["matched"] = intf

                self._mark_elements(self.analysis["global variable initializations"][path][variable]["fields"])

    def _extract_more_interfaces(self):
        # Determine potential callbacks as callbacks without calls in other module functions
        potential_callbacks = [callback for callback in self.analysis["modules functions"]
                               if not self.analysis["modules functions"][callback]["calls"]]

    def _establish_references(self):
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
                                    new = Interface(new_expr)
                                    new.callback = True
                                    new.category = self.interfaces[intf].category
                                    new.full_identifier = identifier
                                    new.identifier = field
                                    self.interfaces[new.full_identifier] = new


class Interface:
    identifier = None
    category = None
    signature = None
    header = None
    implemented_in_kernel = None
    resource = False
    callback = False
    container = False
    kernel_interface = False
    fields = {}
    implementations = {}

    def __init__(self, signature=None, identifier=None, header=None, implemented_in_kernel=False):

        if signature:
            self.signature = Signature(signature)
            if not header:
                if self.signature.type_class == "struct":
                    raise TypeError("Require header with struct '{}' declaration in interface categories specification".
                                    format(self.expression()))
        else:
            self.header = header

        self.implemented_in_kernel = implemented_in_kernel
        self.identifier = identifier

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
    expression = None
    type_class = None
    pointer = None
    array = None
    return_value = None
    interface = None
    function_name = None
    return_value = None
    parameters = None

    def __init__(self, expression):
        """
        Expect signature expression.
        :param expression:
        :return:
        """
        self.expression = expression

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

        struct_re = re.compile("^struct\s+\w*\s+(\*?)%s\s?((?:\[\w*\]))?\Z")
        self._check_type(struct_re, "struct")

        value_re = re.compile("^(\w*\s+)+(\*?)%s((?:\[\w*\]))?\Z")
        self._check_type(value_re, "value")

        interface_re = re.compile("^\*?%(.*)%\Z")
        if not self.type_class and interface_re.fullmatch(self.expression):
            self.type_class = "interface"

        if self.type_class in ["function", "macro"]:
            self._extract_function_interfaces()
        if self.type_class == "interface":
            self.interface = fi_extract.fullmatch(self.expression).group(1)

        if not self.type_class:
            raise ValueError("Cannot determine signature type (function, structure, value or interface) {}".
                             format(self.expression))

    def _check_type(self, regex, type_name):
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

    def _extract_function_interfaces(self):
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
