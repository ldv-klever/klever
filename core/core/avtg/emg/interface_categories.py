from core.avtg.emg.common.interface import Container, Resource, Callback, KernelFunction
from core.avtg.emg.common.signature import InterfaceReference, Primitive, Array, Function, Structure, Pointer, \
    import_signature


class CategoriesSpecification:
    def containers(self, category=None):
        return [interface for interface in self.interfaces.values() if type(interface) is Container and
                (not category or interface.category == category)]

    def callbacks(self, category=None):
        return [interface for interface in self.interfaces.values() if type(interface) is Callback and
                (not category or interface.category == category)]

    def resources(self, category=None):
        return [interface for interface in self.interfaces.values() if type(interface) is Resource and
                (not category or interface.category == category)]

    @property
    def categories(self):
        return set([interface.category for interface in self.interfaces.values()])

    def select_containers(self, field, signature=None, category=None):
        return [container for container in self.containers(category)
                if type(container.declaration) is Structure and
                ((field in container.field_interfaces and
                 (not signature or container.field_interfaces[field].declaration.identifier == signature.identifier)) or
                (field in container.declaration.fields and
                 (not signature or container.declaration.fields[field].identifier == signature.identifier))) and
                (not category or container.category == category)]

    def resolve_interface(self, signature, category=None):
        if type(signature) is InterfaceReference and signature.interface in self.interfaces:
            return [self.interfaces[signature.interface]]
        elif type(signature) is InterfaceReference and signature.interface not in self.interfaces:
            raise KeyError('Cannot find description of interface {}'.format(signature.interface))
        else:
            interfaces = [intf for intf in self.interfaces.values()
                          if type(intf.declaration) is type(signature) and
                          (intf.declaration.identifier == signature.identifier) and
                          (not category or intf.category == category)]

            return interfaces

    def resolve_interface_weakly(self, signature, category=None):
        intf = self.resolve_interface(signature, category)
        if not intf and type(signature) is Pointer:
            intf = self.resolve_interface(signature.points, category)
        elif not intf and type(signature) is not Pointer and signature.clean_declaration:
            intf = self.resolve_interface(signature.take_pointer, category)
        return intf

    def _resolve_function_interfaces(self, interface, category=None):
        if type(interface.declaration) is Pointer and type(interface.declaration.points) is Function:
            declaration = interface.declaration.points
        elif type(interface.declaration) is Function:
            declaration = interface.declaration
        else:
            raise TypeError('Expect pointer to function or function declaration but got {}'.
                            format(str(type(interface.declaration))))

        if declaration.return_value and type(declaration.return_value) is not Primitive and not \
                (type(declaration.return_value) is Pointer and type(declaration.return_value.points) is Primitive):
            rv_interface = self.resolve_interface(declaration.return_value, category)
            if len(rv_interface) == 0:
                rv_interface = self.resolve_interface_weakly(declaration.return_value, category)

            if len(rv_interface) == 1:
                interface.rv_interface = rv_interface[-1]
            elif len(rv_interface) > 1:
                raise ValueError('Cannot match two return values')

        for index in range(len(declaration.parameters)):
            if type(declaration.parameters[index]) is not str and \
                    type(declaration.parameters[index]) is not Primitive and not \
                    (type(declaration.parameters[index]) is Pointer and
                     type(declaration.parameters[index].points) is Primitive):
                p_interface = self.resolve_interface(declaration.parameters[index], category)
                if len(p_interface) == 0:
                    p_interface = self.resolve_interface_weakly(declaration.parameters[index], category)

                if len(p_interface) == 1:
                    p_interface = p_interface[-1]
                elif len(p_interface) == 0:
                    p_interface = None
                else:
                    raise ValueError('Cannot match parameter with two or more interfaces')
            else:
                p_interface = None

            if len(interface.param_interfaces) > index:
                interface.param_interfaces[index] = p_interface
            else:
                interface.param_interfaces.append(p_interface)

    def import_specification(self, specification):
        self.logger.info("Analyze provided interface categories specification")
        for category in specification["categories"]:
            self.logger.debug("Found interface category {}".format(category))
            self.__import_category_interfaces(category, specification["categories"][category])

        if "kernel functions" in specification:
            self.logger.info("Import kernel functions description")
            for intf in self.__import_kernel_interfaces("kernel functions", specification):
                self.kernel_functions[intf.identifier] = intf
                self.logger.debug("New kernel function {} has been imported".format(intf.identifier))
        else:
            self.logger.warning("Kernel functions are not provided within an interface categories specification, "
                                "expect 'kernel functions' attribute")

        # Add fields to container declaration types
        for container in self.containers():
            if type(container.declaration) is Structure:
                for field in container.field_interfaces:
                    if container.field_interfaces[field].declaration and \
                            (type(container.field_interfaces[field].declaration) is Array or
                             type(container.field_interfaces[field].declaration) is Structure):
                        if container.declaration.fields[field].pointer:
                            container.declaration.fields[field] = \
                                container.field_interfaces[field].declaration.take_pointer
                        if container.declaration not in container.declaration.fields[field].parents:
                            container.declaration.fields[field].parents.append(container.declaration)

                            # todo: import "kernel macro-functions" (issue #6573)

    def __import_kernel_interfaces(self, category_name, collection):
        for identifier in collection[category_name]:
            self.logger.debug("Import a description of kernel interface {} from category {}".
                              format(identifier, category_name))
            if "signature" not in collection[category_name][identifier]:
                raise TypeError("Specify 'signature' for kernel interface {} at {}".format(identifier, category_name))
            elif "header" not in collection[category_name][identifier]:
                raise TypeError("Specify 'header' for kernel interface {} at {}".format(identifier, category_name))

            interface = KernelFunction(identifier, collection[category_name][identifier]["header"])
            interface.declaration = import_signature(collection[category_name][identifier]["signature"])
            if type(interface.declaration) is Function:
                self._resolve_function_interfaces(interface)
            else:
                raise TypeError('Expect function declaration in description of kernel function {}'.format(identifier))

            yield interface

    def __import_interfaces(self, category_name, identifier, desc, constructor):
        if "{}.{}".format(category_name, identifier) not in self.interfaces:
            interface = constructor(category_name, identifier)
            self.interfaces[interface.identifier] = interface
        else:
            raise ValueError('Interface {} is described twice'.format(identifier.identifier))

        if "implemented in kernel" in desc:
            interface.implemented_in_kernel = desc["implemented in kernel"]

        if "header" in desc:
            interface.header = desc["header"]

        if "signature" in desc:
            interface.declaration = import_signature(desc["signature"])

        return interface

    def __import_category_interfaces(self, category_name, dictionary):
        self.logger.debug("Initialize description for category {}".format(category_name))

        # Import interfaces
        if "containers" in dictionary:
            self.logger.debug("Import containers from a description of an interface category {}".format(category_name))
            for identifier in dictionary['containers']:
                self.__import_interfaces(category_name, identifier, dictionary["containers"][identifier], Container)
        if "resources" in dictionary:
            self.logger.debug("Import resources from a description of an interface category {}".format(category_name))
            for identifier in dictionary['resources']:
                self.__import_interfaces(category_name, identifier, dictionary["resources"][identifier], Resource)
        if "callbacks" in dictionary:
            self.logger.debug("Import callbacks from a description of an interface category {}".format(category_name))
            for identifier in dictionary['callbacks']:
                self.__import_interfaces(category_name, identifier, dictionary["callbacks"][identifier], Callback)

        if "containers" in dictionary:
            self.logger.debug("Import containers from a description of an interface category {}".format(category_name))
            for identifier in dictionary['containers']:
                fi = "{}.{}".format(category_name, identifier)
                # Import field interfaces
                if "fields" in dictionary['containers'][identifier]:
                    for field in dictionary['containers'][identifier]["fields"]:
                        f_signature = import_signature(dictionary['containers'][identifier]["fields"][field])
                        self.interfaces[fi].field_interfaces[field] = self.interfaces[f_signature.interface]
                        self.interfaces[fi].declaration.fields[field] = f_signature

        for callback in self.callbacks(category_name):
            self._resolve_function_interfaces(callback)


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
