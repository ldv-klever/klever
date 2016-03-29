import copy

from core.avtg.emg.common.interface import Container, Resource, Callback, KernelFunction, Interface
from core.avtg.emg.common.signature import BaseType, InterfaceReference, UndefinedReference, Primitive, Array, Function,\
    Structure, Pointer, import_signature


class CategoriesSpecification:

    @property
    def categories(self):
        return sorted(set([interface.category for interface in self.interfaces.values()]))

    def import_specification(self, specification):
        self.logger.info("Analyze provided interface categories specification")
        for category in sorted(specification["categories"]):
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
                for field in sorted(container.field_interfaces):
                    if container.field_interfaces[field].declaration and \
                            (type(container.field_interfaces[field].declaration) is Array or
                             type(container.field_interfaces[field].declaration) is Structure):
                        if container.declaration.fields[field].pointer:
                            container.declaration.fields[field] = \
                                container.field_interfaces[field].declaration.take_pointer
                        if container.declaration not in container.declaration.fields[field].parents:
                            container.declaration.fields[field].parents.append(container.declaration)

        # todo: import "kernel macro-functions" (issue #6573)

        # Refine dirty declarations
        self._refine_interfaces()

    def containers(self, category=None):
        return [self.interfaces[name] for name in sorted(self.interfaces.keys())
                if type(self.interfaces[name]) is Container and
                (not category or self.interfaces[name].category == category)]

    def callbacks(self, category=None):
        return [self.interfaces[name] for name in sorted(self.interfaces.keys())
                if type(self.interfaces[name]) is Callback and
                (not category or self.interfaces[name].category == category)]

    def resources(self, category=None):
        return [self.interfaces[name] for name in sorted(self.interfaces.keys())
                if type(self.interfaces[name]) is Resource and
                (not category or self.interfaces[name].category == category)]

    def uncalled_callbacks(self, category=None):
        return [cb for cb in self.callbacks(category) if not cb.called]

    def select_containers(self, field, signature=None, category=None):
        return [container for container in self.containers(category)
                if type(container.declaration) is Structure and
                ((field in container.field_interfaces and
                  (not signature or container.field_interfaces[field].declaration.identifier == signature.identifier)) or
                 (field in container.declaration.fields and
                  (not signature or container.declaration.fields[field].identifier == signature.identifier))) and
                (not category or container.category == category)]

    def resolve_containers(self, target, category=None):
        return {container.identifier: container.contains(target) for container in self.containers(category)
                if (type(container.declaration) is Structure and len(container.contains(target)) > 0) or
                (type(container.declaration) is Array and container.contains(target))}

    def resolve_interface(self, signature, category=None):
        if type(signature) is InterfaceReference and signature.interface in self.interfaces:
            return [self.interfaces[signature.interface]]
        elif type(signature) is InterfaceReference and signature.interface not in self.interfaces:
            raise KeyError('Cannot find description of interface {}'.format(signature.interface))
        else:
            interfaces = [self.interfaces[name] for name in sorted(self.interfaces.keys())
                          if type(self.interfaces[name].declaration) is type(signature) and
                          (self.interfaces[name].declaration.identifier == signature.identifier) and
                          (not category or self.interfaces[name].category == category)]

            return interfaces

    def resolve_interface_weakly(self, signature, category=None):
        intf = self.resolve_interface(signature, category)
        if not intf and type(signature) is Pointer:
            intf = self.resolve_interface(signature.points, category)
        elif not intf and type(signature) is not Pointer and signature.clean_declaration:
            intf = self.resolve_interface(signature.take_pointer, category)
        return intf

    def implementations(self, interface, weakly=True):
        if weakly:
            candidates = interface.declaration.weak_implementations
        else:
            candidates = [interface.declaration.implementations[name] for name in
                          sorted(interface.declaration.implementations.keys())]

        if len(candidates) == 0:
            return candidates
        else:
            # Filter filter interfaces
            implementations = []
            for impl in candidates:
                if len(impl.sequence) > 0:
                    cnts = self.resolve_containers(interface)
                    for cnt in cnts:
                        cnt_intf = self.interfaces[cnt]
                        if impl.sequence[-1] in cnts[cnt] and \
                                (impl.sequence[-1] in cnt_intf.field_interfaces and
                                 cnt_intf.field_interfaces[impl.sequence[-1]] and
                                 cnt_intf.field_interfaces[impl.sequence[-1]].identifier == interface.identifier):
                            implementations.append(impl)
                            break
                else:
                    implementations.append(impl)

            return implementations

    def _refine_declaration(self, declaration):
        if declaration.clean_declaration:
            raise ValueError('Cannot clean already cleaned declaration')

        if type(declaration) is UndefinedReference:
            return None
        elif type(declaration) is InterfaceReference:
            if declaration.interface in self.interfaces and \
                    self.interfaces[declaration.interface].declaration.clean_declaration:
                if declaration.pointer:
                    return self.interfaces[declaration.interface].declaration.take_pointer
                else:
                    return self.interfaces[declaration.interface].declaration
            else:
                return None
        elif type(declaration) is Function:
            refinement = False
            ret = True
            cp_declaration = copy.copy(declaration)
            
            if cp_declaration.return_value and not cp_declaration.return_value.clean_declaration:
                rv = self._refine_declaration(cp_declaration.return_value)
                if rv:
                    cp_declaration.return_value = rv
                    refinement = True
                else:
                    ret = False

            for index in range(len(cp_declaration.parameters)):
                if type(cp_declaration.parameters[index]) is not str and \
                        not cp_declaration.parameters[index].clean_declaration:
                    pr = self._refine_declaration(cp_declaration.parameters[index])
                    if pr:
                        cp_declaration.parameters[index] = pr
                        refinement = True
                    else:
                        ret = False

            if refinement and cp_declaration.identifier in self.types:
                declaration = self.types[cp_declaration.identifier]
            elif refinement:
                declaration.return_value = cp_declaration.return_value
                declaration.parameters = cp_declaration.parameters
                # Identifier has been changed!
                self.types[declaration.identifier] = declaration

            if ret:
                return declaration
            else:
                return None
        elif type(declaration) is Pointer and type(declaration.points) is Function:
            func = self._refine_declaration(declaration.points)
            if func:
                return func.take_pointer
            else:
                return None
        else:
            raise ValueError('Cannot clean non-function or interface-reference')

    def _refine_interfaces(self):
        # Clean declarations if it is poissible
        self.logger.debug('Clean all interface declarations from InterfaceReferences')
        clean_flag = True
        while clean_flag:
            clean_flag = False

            for interface in [self.interfaces[name] for name in sorted(self.interfaces.keys())]:
                if not interface.declaration.clean_declaration:
                    new_declaration = self._refine_declaration(interface.declaration)

                    if new_declaration:
                        interface.declaration = new_declaration
                        clean_flag = True

        self.logger.debug("Restore field declarations in structure declarations")
        for structure in [intf for intf in self.containers() if intf.declaration and
                          type(intf.declaration) is Structure]:
            for field in [field for field in sorted(structure.declaration.fields.keys())
                          if not structure.declaration.fields[field].clean_declaration]:
                new_declaration = self._refine_declaration(structure.declaration.fields[field])
                if new_declaration:
                    structure.declaration.fields[field] = new_declaration

    def _fulfill_function_interfaces(self, interface, category=None):
        if type(interface.declaration) is Pointer and type(interface.declaration.points) is Function:
            declaration = interface.declaration.points
        elif type(interface.declaration) is Function:
            declaration = interface.declaration
        else:
            raise TypeError('Expect pointer to function or function declaration but got {}'.
                            format(str(type(interface.declaration))))

        if not interface.rv_interface:
            if declaration.return_value and type(declaration.return_value) is InterfaceReference and \
                    declaration.return_value.interface in self.interfaces:
                interface.rv_interface = self.interfaces[declaration.return_value.interface]
            elif declaration.return_value and type(declaration.return_value) is not Primitive and not \
                    (type(declaration.return_value) is Pointer and type(declaration.return_value.points) is Primitive):
                rv_interface = self.resolve_interface(declaration.return_value, category)
                if len(rv_interface) == 0:
                    rv_interface = self.resolve_interface_weakly(declaration.return_value, category)

                if len(rv_interface) == 1:
                    interface.rv_interface = rv_interface[-1]
                elif len(rv_interface) > 1:
                    raise ValueError('Cannot match two return values')

        for index in range(len(declaration.parameters)):
            if not (len(interface.param_interfaces) > index and interface.param_interfaces[index]):
                if type(declaration.parameters[index]) is InterfaceReference and \
                        declaration.parameters[index].interface in self.interfaces:
                    p_interface = self.interfaces[declaration.parameters[index].interface]
                elif type(declaration.parameters[index]) is not str and \
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

    def __import_kernel_interfaces(self, category_name, collection):
        for identifier in sorted(collection[category_name].keys()):
            self.logger.debug("Import a description of kernel interface {} from category {}".
                              format(identifier, category_name))
            if "signature" not in collection[category_name][identifier]:
                raise TypeError("Specify 'signature' for kernel interface {} at {}".format(identifier, category_name))
            elif "header" not in collection[category_name][identifier]:
                raise TypeError("Specify 'header' for kernel interface {} at {}".format(identifier, category_name))

            interface = KernelFunction(identifier, collection[category_name][identifier]["header"])
            interface.declaration = import_signature(collection[category_name][identifier]["signature"])
            if type(interface.declaration) is Function:
                self._fulfill_function_interfaces(interface)
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
            for identifier in sorted(dictionary['containers'].keys()):
                self.__import_interfaces(category_name, identifier, dictionary["containers"][identifier], Container)
        if "resources" in dictionary:
            self.logger.debug("Import resources from a description of an interface category {}".format(category_name))
            for identifier in sorted(dictionary['resources'].keys()):
                self.__import_interfaces(category_name, identifier, dictionary["resources"][identifier], Resource)
        if "callbacks" in dictionary:
            self.logger.debug("Import callbacks from a description of an interface category {}".format(category_name))
            for identifier in sorted(dictionary['callbacks'].keys()):
                self.__import_interfaces(category_name, identifier, dictionary["callbacks"][identifier], Callback)

        if "containers" in dictionary:
            self.logger.debug("Import containers from a description of an interface category {}".format(category_name))
            for identifier in sorted(dictionary['containers'].keys()):
                fi = "{}.{}".format(category_name, identifier)
                # Import field interfaces
                if "fields" in dictionary['containers'][identifier]:
                    for field in sorted(dictionary['containers'][identifier]["fields"].keys()):
                        f_signature = import_signature(dictionary['containers'][identifier]["fields"][field])
                        self.interfaces[fi].field_interfaces[field] = self.interfaces[f_signature.interface]
                        self.interfaces[fi].declaration.fields[field] = f_signature

        for callback in self.callbacks(category_name):
            self._fulfill_function_interfaces(callback)


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
