from core.avtg.emg.common.interface import Interface, extract_full_identifier


class CategoriesSpecification:

    def __init__(self, logger):
        self.logger = logger
        self.interfaces = {}
        self.kernel_functions = {}
        self.kernel_macro_functions = {}
        self.kernel_macros = {}

    @property
    def containers(self, category=None):
        return [interface for interface in self.interfaces.values() if interface.container and
                (not category or interface.category == category)]

    @property
    def callbacks(self, category=None):
        return [interface for interface in self.interfaces.values() if interface.callback and
                (not category or interface.category == category)]

    @property
    def resources(self, category=None):
        return [interface for interface in self.interfaces.values() if interface.resource and
                (not category or interface.category == category)]

    @property
    def categories(self):
        return set([interface.category for interface in self.interfaces.values()])

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

    def __import_kernel_interfaces(self, category_name, collection):
        for identifier in collection[category_name]:
            self.logger.debug("Import a description of kernel interface {} from category {}".
                              format(identifier, category_name))
            if "signature" not in collection[category_name][identifier]:
                raise TypeError("Specify 'signature' for kernel interface {} at {}".format(identifier, category_name))
            elif "header" not in collection[category_name][identifier]:
                raise TypeError("Specify 'header' for kernel interface {} at {}".format(identifier, category_name))

            interface = Interface(category_name, identifier)
            interface.import_signature(collection[category_name][identifier]["signature"])
            interface.header = collection[category_name][identifier]["header"]
            interface.implemented_in_kernel = True

            yield interface

    def __import_interfaces(self, category_name, collection):
        for intf_identifier in collection:
            if "{}.{}".format(category_name, intf_identifier) in self.interfaces:
                self.logger.debug("Found a description of an existing interface {} from category {}".
                                  format(intf_identifier, category_name))
                interface = self.interfaces["{}.{}".format(category_name, intf_identifier)]
            else:
                interface = Interface(category_name, intf_identifier)
                self.interfaces[interface.identifier] = interface

            if "implemented in kernel" in collection[intf_identifier]:
                interface.implemented_in_kernel = collection[intf_identifier]["implemented in kernel"]

            if "header" in collection[intf_identifier]:
                interface.header = collection[intf_identifier]["header"]

            if "signature" in collection[intf_identifier]:
                interface.import_signature(collection[intf_identifier]["signature"])

                # Import field interfaces
                if "fields" in collection[intf_identifier]:
                    for field in collection[intf_identifier]["fields"]:
                        if collection[intf_identifier]["fields"] in self.interfaces:
                            p_interface = self.interfaces[collection[intf_identifier]["fields"]]
                        else:
                            p_category, p_identifier = extract_full_identifier(collection[intf_identifier]["fields"])
                            p_interface = Interface(p_category, p_identifier)
                            self.interfaces[p_interface.identifier] = p_interface

                        interface.field_interfaces[field] = p_interface
            elif "signature" not in collection[intf_identifier] and \
                 "{}.{}".format(category_name, intf_identifier) not in self.interfaces:
                raise TypeError("Provide 'signature' for interface {} at {} or define it as a container".
                                format(intf_identifier, category_name))

            yield interface

    def __import_category_interfaces(self, category_name, dictionary):
        self.logger.debug("Initialize description for category {}".format(category_name))

        # Import interfaces
        if "containers" in dictionary:
            self.logger.debug("Import containers from a description of an interface category {}".format(category_name))
            for intf in self.__import_interfaces(category_name, dictionary["containers"]):
                intf.container = True
        if "resources" in dictionary:
            self.logger.debug("Import resources from a description of an interface category {}".format(category_name))
            for intf in self.__import_interfaces(category_name, dictionary["resources"]):
                intf.resource = True
        if "callbacks" in dictionary:
            self.logger.debug("Import callbacks from a description of an interface category {}".format(category_name))
            for intf in self.__import_interfaces(category_name, dictionary["callbacks"]):
                intf.callback = True


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
