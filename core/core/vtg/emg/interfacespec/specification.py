#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from core.vtg.emg.common.interface import Container, Resource, Callback, SourceFunction
from core.vtg.emg.common.signature import Function, Structure, Array, Pointer, InterfaceReference, Primitive, \
    import_declaration


def import_interface_specification(collection, specification):
    """
    Starts specification import.

    First it creates Interface objects for each container, resource and callback in specification and then imports
    kernel functions matching their parameters with already imported interfaces.

    :param collection: InterfaceCategoriesSpecification object.
    :param specification: Dictionary with content of a JSON specification prepared manually.
    :return: None
    """
    for category in sorted(specification["categories"]):
        collection.logger.debug("Found interface category {}".format(category))
        __import_category_interfaces(collection, category, specification["categories"][category])

        # todo: check specifications and remove this
        if 'extensible' in specification["categories"][category]:
            raise KeyError("Extensible attribute is depricated. Found one in {!r}".format(category))

    if "kernel functions" in specification:
        collection.logger.info("Import kernel functions description")
        for intf in __import_kernel_interfaces(collection, "kernel functions", specification):
            collection.set_kernel_function(intf)
            collection.logger.debug("New kernel function {} has been imported".format(intf.identifier))
    else:
        collection.logger.warning(
            "Kernel functions are not provided within an interface categories specification, expect 'kernel functions' "
            "attribute")

    # Add fields to container declaration types
    for container in collection.containers():
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

    # Refine "dirty" declarations
    collection.refine_interfaces()


def fulfill_function_interfaces(collection, interface, category=None):
    """
    Check an interface declaration (function or function pointer) and try to match its return value type and
    parameters arguments types with existing interfaces. The algorythm should be the following:

    * Match explicitly stated interface References (only if they meet given category).
    * Match rest parameters:
        - Avoid matching primitives and arrays and pointers of primitives;
        - Match interfaces from given category or from the category of already matched interfaces by interface
          references;
        - If there are more that one category is matched - do not do match to avoid mistakes in match.

    :param collection: InterfaceCategoriesSpecification object.
    :param interface: Interface object: KernelFunction or Callback.
    :param category: Category filter.
    :return: None.
    """

    def is_primitive_or_void(decl):
        """
        Return True if given declaration object has type of Primitive or pointer(* and **) to Primitive.

        :param decl: Declaration object
        :return: True - it is primitive, False - otherwise
        """
        # todo: Implement check agains arrays of primitives
        if type(decl) is Primitive or \
            (type(decl) is Pointer and
             (type(decl.points) is Primitive or decl.identifier in {'void *', 'void **'})):
            return True
        else:
            return False

    def assign_parameter_interface(function_intf, matched_intf, position):
        """
        Add matched parameter interface to the list of matched parameters. This takes care of unfilled list of
        parameters in the interface list.

        :param function_intf: KernelFunction or Callback object.
        :param matched_intf: Interface object.
        :param position: int.
        :return: None
        """
        if len(function_intf.param_interfaces) > position and not function_intf.param_interfaces[position]:
            function_intf.param_interfaces[position] = matched_intf
        else:
            function_intf.param_interfaces.append(matched_intf)

    collection.logger.debug("Try to match collateral interfaces for function '{}'".format(interface.identifier))
    # Check declaration type
    if type(interface.declaration) is Pointer and type(interface.declaration.points) is Function:
        declaration = interface.declaration.points
    elif type(interface.declaration) is Function:
        declaration = interface.declaration
    else:
        raise TypeError('Expect pointer to function or function declaration but got {}'.
                        format(str(type(interface.declaration))))

    # First check explicitly stated interfaces
    if not interface.rv_interface and declaration.return_value and \
            type(declaration.return_value) is InterfaceReference and \
            declaration.return_value.interface in collection.interfaces:
        interface.rv_interface = collection.get_intf(declaration.return_value.interface)
    elif interface.rv_interface and not category:
        category = interface.rv_interface.category

    # Check explicit parameter interface references
    for index in range(len(declaration.parameters)):
        if not (len(interface.param_interfaces) > index and interface.param_interfaces[index]):
            if type(declaration.parameters[index]) is InterfaceReference and \
                    declaration.parameters[index].interface in collection.interfaces:
                p_interface = collection.get_intf(declaration.parameters[index].interface)
            else:
                p_interface = None

            assign_parameter_interface(interface, p_interface, index)

            if p_interface and not category:
                category = p_interface.category
        elif len(interface.param_interfaces) > index and interface.param_interfaces[index] and \
                isinstance(interface.param_interfaces[index], Callback):
            interface.param_interfaces[index].declaration = interface.declaration.parameters[index]

    # Second match rest types
    if not interface.rv_interface and declaration.return_value and not is_primitive_or_void(declaration.return_value):
        rv_interface = collection.resolve_interface(declaration.return_value, category, False)
        if len(rv_interface) == 0:
            rv_interface = collection.resolve_interface_weakly(declaration.return_value, category, False)
        if len(rv_interface) == 1:
            interface.rv_interface = rv_interface[-1]
        elif len(rv_interface) > 1:
            collection.logger.warning(
                'Interface {!r} return value signature {!r} can be match with several following interfaces: {}'.
                format(interface.identifier, declaration.return_value.identifier,
                       ', '.join((i.identifier for i in rv_interface))))

    for index in range(len(declaration.parameters)):
        if not (len(interface.param_interfaces) > index and interface.param_interfaces[index]) and \
                type(declaration.parameters[index]) is not str and \
                not is_primitive_or_void(declaration.parameters[index]):
            p_interface = collection.resolve_interface(declaration.parameters[index], category, False)
            if len(p_interface) == 0:
                p_interface = collection.resolve_interface_weakly(declaration.parameters[index], category, False)
            if len(p_interface) == 1:
                p_interface = p_interface[0]
            elif len(p_interface) == 0:
                p_interface = None
            else:
                collection.logger.warning(
                    'Interface {!r} parameter in the position {} with signature {!r} can be match with several '
                    'following interfaces: {}'.format(interface.identifier,
                                                      index, declaration.parameters[index].identifier,
                                                      ', '.join((i.identifier for i in p_interface))))
                p_interface = None

            assign_parameter_interface(interface, p_interface, index)

            if p_interface and not category:
                category = p_interface.category


def __import_category_interfaces(collection, category_name, description):
    collection.logger.debug("Initialize description for category {}".format(category_name))

    # Import interfaces
    if "containers" in description:
        collection.logger.debug("Import containers from an interface category description {!r}".format(category_name))
        for identifier in sorted(description['containers'].keys()):
            __import_interfaces(collection, category_name, identifier, description["containers"][identifier], Container)
    if "resources" in description:
        collection.logger.debug("Import resources from an interface category description {!r}".format(category_name))
        for identifier in sorted(description['resources'].keys()):
            __import_interfaces(collection, category_name, identifier, description["resources"][identifier], Resource)
    if "callbacks" in description:
        collection.logger.debug("Import callbacks from an interface category description {!r}".format(category_name))
        for identifier in sorted(description['callbacks'].keys()):
            __import_interfaces(collection, category_name, identifier, description["callbacks"][identifier], Callback)

    if "containers" in description:
        collection.logger.debug("Import containers from an interface category description {!r}".format(category_name))
        for identifier in sorted(description['containers'].keys()):
            fi = "{}.{}".format(category_name, identifier)
            # Import field interfaces
            if "fields" in description['containers'][identifier]:
                for field in sorted(description['containers'][identifier]["fields"].keys()):
                    f_signature = import_declaration(description['containers'][identifier]["fields"][field])
                    collection.get_intf(fi).field_interfaces[field] = collection.get_intf(f_signature.interface)
                    collection.get_intf(fi).declaration.fields[field] = f_signature

    for callback in collection.callbacks(category_name):
        fulfill_function_interfaces(collection, callback)


def __import_interfaces(collection, category_name, identifier, description, constructor):
    if "{}.{}".format(category_name, identifier) not in collection.interfaces:
        collection.logger.debug("Import described interface description '{}.{}'".format(category_name, identifier))
        interface = constructor(category_name, identifier, manually_specified=True)
        collection.set_intf(interface)
    else:
        raise ValueError('Interface {} is described twice'.format(identifier))

    if "implemented in kernel" in description:
        interface.implemented_in_kernel = description["implemented in kernel"]

    if "headers" in description:
        interface.header = description["headers"]
    elif "header" in description:
        interface.header = [description["header"]]

    if "signature" in description:
        interface.declaration = import_declaration(description["signature"])

    if "interrupt context" in description and description["interrupt context"]:
        interface.interrupt_context = True

    return interface


def __import_kernel_interfaces(collection, category_name, specification):
    for identifier in sorted(specification[category_name].keys()):
        if "signature" not in specification[category_name][identifier]:
            raise TypeError("Specify 'signature' for kernel interface {} at {}".format(identifier, category_name))
        elif "header" not in specification[category_name][identifier] and \
                "headers" not in specification[category_name][identifier]:
            raise TypeError("Specify 'header' for kernel interface {} at {}".format(identifier, category_name))

        collection.logger.debug("Import kernel function description '{}'".format(identifier))
        if "header" in specification[category_name][identifier]:
            interface = SourceFunction(identifier, specification[category_name][identifier]["signature"],
                                       specification[category_name][identifier]["header"])
        else:
            interface = SourceFunction(identifier, specification[category_name][identifier]["signature"],
                                       specification[category_name][identifier]["headers"])

        interface.declaration = import_declaration(specification[category_name][identifier]["signature"])
        if type(interface.declaration) is Function:
            fulfill_function_interfaces(collection, interface)
        else:
            raise TypeError('Expect function declaration in description of kernel function {}'.format(identifier))

        yield interface


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
