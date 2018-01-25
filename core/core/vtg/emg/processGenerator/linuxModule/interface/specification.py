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
from core.vtg.emg.processGenerator.linuxModule.interface import StructureContainer, ArrayContainer, Resource, Callback,\
    FunctionInterface
from core.vtg.emg.common.c.types import Function, Structure, Array, Pointer, Primitive, import_declaration


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

    if "functions models" in specification:
        collection.logger.info("Import kernel functions description")
        for intf in __import_kernel_interfaces(collection, "kernel functions", specification):
            collection.set_source_function(intf, None)
            collection.logger.debug("New kernel function {} has been imported".format(intf.identifier))
    else:
        collection.logger.warning(
            "Kernel functions are not provided within an interface categories specification, expect 'kernel functions' "
            "attribute")

    # Add fields to container declaration types
    for container in collection.containers():
        if isinstance(container.declaration, Structure):
            for field in sorted(container.field_interfaces):
                if container.field_interfaces[field].declaration and \
                        (isinstance(container.field_interfaces[field].declaration, Array) or
                         isinstance(container.field_interfaces[field].declaration, Structure)):
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
        if isinstance(decl, Primitive) or \
            (isinstance(decl, Pointer) and
             (isinstance(decl.points, Primitive) or decl.identifier in {'void *', 'void **'})):
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

    # Check declaration type
    if isinstance(interface.declaration, Pointer) and isinstance(interface.declaration.points, Function):
        declaration = interface.declaration.points
    elif isinstance(interface.declaration, Function):
        declaration = interface.declaration
    else:
        raise TypeError('Expect pointer to function or function declaration but got {}'.
                        format(str(type(interface.declaration))))

    # First check explicitly stated interfaces
    if not interface.rv_interface and declaration.return_value and \
            isinstance(declaration.return_value, InterfaceReference) and \
            declaration.return_value.interface in collection.interfaces:
        interface.rv_interface = collection.get_intf(declaration.return_value.interface)
    elif interface.rv_interface and not category:
        category = interface.rv_interface.category

    # Check explicit parameter interface references
    for index in range(len(declaration.parameters)):
        if not (len(interface.param_interfaces) > index and interface.param_interfaces[index]):
            if isinstance(declaration.parameters[index], InterfaceReference) and \
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
                not isinstance(declaration.parameters[index], str) and \
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
    def get_clean_declaration(desc, i):
        if "declaration" in desc:
            decl = import_declaration(desc["declaration"])
        else:
            raise ValueError("Provide declaration for interface specification of '{}.{}'".format(category_name, i))
        return decl

    # Import interfaces
    if "containers" in description:
        for identifier in description['containers'].keys():
            declaration = get_clean_declaration(description['containers'][identifier], identifier)
            if isinstance(declaration, Structure):
                intf = StructureContainer(category_name, identifier)
            elif isinstance(declaration, Array):
                intf = ArrayContainer(category_name, identifier)
            else:
                raise ValueError("Container '{}.{}' should be either a structure or array"
                                 .format(category_name, identifier))
            intf.declaration(declaration)
            __import_interfaces(collection, intf, description["containers"][identifier])
    if "resources" in description:
        for identifier in description['resources'].keys():
            declaration = get_clean_declaration(description['resources'][identifier], identifier)
            intf = Resource(category_name, identifier)
            intf.declaration(declaration)
            __import_interfaces(collection, intf, description["resources"][identifier])
    if "callbacks" in description:
        for identifier in description['callbacks'].keys():
            __import_interfaces(collection, category_name, identifier, description["callbacks"][identifier], Callback)

    if "containers" in description:
        for identifier in description['containers'].keys():
            fi = "{}.{}".format(category_name, identifier)
            # Import field interfaces
            if "fields" in description['containers'][identifier]:
                for field in description['containers'][identifier]["fields"].keys():
                    f_signature = import_declaration(description['containers'][identifier]["fields"][field])
                    collection.get_intf(fi).field_interfaces[field] = collection.get_intf(f_signature.interface)
                    collection.get_intf(fi).declaration.fields[field] = f_signature
            if 'element' in description['containers'][identifier]:
                raise NotImplementedError('There is no support for Array Containers still')

    for callback in collection.callbacks(category_name):
        fulfill_function_interfaces(collection, callback)


def __import_interfaces(collection, intf, description):
    if "{}.{}".format(category_name, identifier) not in collection.interfaces:
        interface = constructor(category_name, identifier, manually_specified=True)
        collection.set_intf(interface)
    else:
        raise ValueError('Interface {} is described twice'.format(identifier))

    if "headers" in description:
        interface.header = description["headers"]
    elif "header" in description:
        interface.header = [description["header"]]

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

        interface = SourceFunction(identifier, specification[category_name][identifier]["signature"])
        if isinstance(interface.declaration, Function):
            fulfill_function_interfaces(collection, interface)
        else:
            raise TypeError('Expect function declaration in description of kernel function {}'.format(identifier))

        yield interface
