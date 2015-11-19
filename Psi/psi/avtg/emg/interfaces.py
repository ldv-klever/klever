import re

fi_regex = re.compile("(\w*)\.(\w*)")


def is_full_identifier(string):
    """Check that string is a correct full interface identifier."""
    if fi_regex(string) and len(fi_regex(string).groups()) == 2:
        return True
    else:
        False


def extract_full_identifier(string):
    """Extract full identifier from a given string."""
    if is_full_identifier(string):
        category, identifier = fi_regex.match(string).groups()
        return category, identifier
    else:
        raise ValueError("Given string {} is not a full identifier".format(string))


class CategorySpecification:
    categories = {}
    interfaces = {}
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




    def _import_interfaces(self, category_name, collection, interface_type):
        for intf_identifier in collection:
            full_identifier = "{}.{}".format(category_name, intf_identifier)
            self.logger.debug("Import {} interface {}".format(interface_type, full_identifier))
            if full_identifier in self.interfaces:
                self.logger.debug("Interface {} has been already described".format(full_identifier))
                intf = self.interfaces[full_identifier]
            else:
                self.logger.debug("Interface {} is new, going to create for it a new description".
                                  format(full_identifier))
                implmented_flag = False
                if "implemented in kernel" in collection[intf_identifier]:
                    implmented_flag = True

                if "header" in collection[intf_identifier]:
                    header = collection[intf_identifier]["header"]
                else:
                    header = None
                intf = Interface(collection[intf_identifier]["signature"],
                                 intf_identifier,
                                 header,
                                 implmented_flag)
                intf.category = category_name
                self.interfaces[intf.full_identifier] = intf

            if interface_type == "callback":
                if self.
                intf.callback = True
                self.categories[category_name]["callbacks"][intf_identifier] = intf
            elif interface_type == "resource":
                intf.resource = True
                self.categories[category_name]["resources"][intf_identifier] = intf
            elif interface_type == "container":
                intf.container = True
                self.categories[category_name]["containers"][intf_identifier] = intf
            else:
                raise ValueError("Unknown interface type {}".format(interface_type))

    def _import_category_interfaces(self, category_name, dictionary):
        if category_name in self.categories:
            raise TypeError("Category {} has been already defined in inteface category specification".
                            format(category_name))
        else:
            self.categories[category_name] = {
                "containers": {},
                "resources": {},
                "callbacks": {}
            }

        if "containers" in dictionary:
            self.logger.debug("Import containers of the interface category {}".format(category_name))
            self._import_interfaces(category_name, dictionary["containers"], "container")
        if "resources" in dictionary:
            self.logger.debug("Import resources of the interface category {}".format(category_name))
            self._import_interfaces(category_name, dictionary["resources"], "resource")
        if "callbacks" in dictionary:
            self.logger.debug("Import callbacks of the interface category {}".format(category_name))
            self._import_interfaces(category_name, dictionary["callbacks"], "callback")


class Interface:
    identifier = None
    category = None
    signature = None
    header = None
    implemented_in_kernel = None
    resource = False
    callback = False
    container = False
    _fields = {}

    def __init__(self, signature, identifier=None, header=None, implemented_in_kernel=False):
        self.signature = Signature(signature)

        if not header:
            if self.signature.type_class == "struct":
                raise TypeError("Require header with struct '{}' declaration in interface categories specification")
        else:
            self.header = header

        self.implemented_in_kernel = implemented_in_kernel
        self.identifier = identifier

    @property
    def fields(self, fields=None):
        """Containers have fields attribute with map from structure field names to another interfaces."""
        if not self.container:
            raise TypeError("Non-container interface does not have 'fields' attribute")

        if not fields:
            return self._fields
        else:
            self._fields = fields

    @property
    def role(self, role=None):
        """Callback interfaces have roles which are identifiers actually."""
        if not self.callback:
            raise TypeError("Non-callback interface does not have 'role' attribute")

        if not role:
            return self.identifier
        else:
            self.identifier = role

    @property
    def full_identifier(self, full_identifier=None):
        """Full identifier looks like 'category.identifier'."""
        if not self.category and not full_identifier:
            raise ValueError("Cannot determine full identifier without interface category")
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

    def _check_type(self, regex, type):
        if not self.type_class and regex.fullmatch(self.expression):
            self.type_class = type
            groups = regex.fullmatch(self.expression).groups()
            if groups[0] != "":
                self.pointer = True
            else:
                self.pointer = False

            if groups[1] != "":
                self.array = True
            else:
                self.array = False

            return True
        else:
            return False

    def _extract_function_interfaces(self):
        ret_and_name_re = re.compile("^(.*)\(\*%(\w*)%\s?\[\w*\]\)\s?\((.*)\)\Z")
        ret_signature, intf_name, args_signatures = ret_and_name_re.fullmatch(self.expression)
        self.return_value = Signature(ret_signature)

        arg_re = re.compile("^void]|[[.*\*?%s|%\w+%]\s?,?]]+]\Z")

        
    def __init__(self, expression):
        """
        Expect signature expression.
        :param expression:
        :return:
        """
        self.expression = expression

        struct_re = re.compile("^struct\s+\w*\s+(\*?)%s(\s?\[\w*\])\Z")
        value_re = re.compile("^(\w*\s+)+(\*?)%s(\s?\[\w*\])\Z")
        function_re = re.compile("^.*\((\*)%\w*%\s?(\[\w*\])\)\s?\(.*\)\Z")

        self._check_type(function_re, "function")
        self._check_type(struct_re, "struct")
        self._check_type(value_re, "value")

        if self.type_class == "function":
            self._extract_function_interfaces()

        if not self.type_class:
            raise ValueError("Cannot determine signature type (function, structure or value) {}".format(expression))

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
