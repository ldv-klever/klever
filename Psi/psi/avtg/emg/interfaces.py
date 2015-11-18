import re


class CategorySpecification:
    categories = {}

    def __init__(self, specification):
        for category in specification["categories"]:
            cat = InterfaceCategory()
            cat.import_dictionary(specification["categories"][category])
            self.categories[category] = cat


class InterfaceCategory:
    name = None
    callbacks = {}
    resources = {}
    containers = {}

    def import_dictionary(self, name, dict):
        self.name = name

        if "resources" in dict:
            for resource in dict["resources"]:
                implmented_flag = False
                if "implemented in kernel" in dict["resources"][resource]:
                    implmented_flag = True

                self.resources[resource] = Resource(dict["resources"][resource]["signature"],
                                                    dict["resources"][resource]["header"],
                                                    resource,
                                                    implmented_flag)
                
        if "callbacks" in dict:
            for callback in dict["callbacks"]:
                implmented_flag = False
                if "implemented in kernel" in dict["callbacks"][callback]:
                    implmented_flag = True

                self.callbacks[callback] = Callback(dict["callbacks"][callback]["signature"],
                                                    dict["callbacks"][callback]["header"],
                                                    callback,
                                                    implmented_flag)


class Interface:
    signature = None
    header = None
    implemented_in_kernel = None
    identifier = None

    def __init__(self, signature, header, identifier=None, implemented_in_kernel=False):
        self.signature = Signature(signature)
        self.header = header
        self.implemented_in_kernel = implemented_in_kernel
        self.identifier = identifier


class Container(Interface):
    fields = None

    def __init__(self, signature, header, identifier=None, implemented_in_kernel=False, fields={}):
        super().__init__(self, signature, header, identifier, implemented_in_kernel)

        self.fields = fields
        if not self.identifier:
            self.identifier = self.signature.type

        if not self.identifier:
            raise ValueError("Cannot determine container identifier")


class Callback(Interface):
    context = "process"

    def __init__(self, signature, header, identifier, implemented_in_kernel=False):
        super().__init__(self, signature, header, identifier, implemented_in_kernel)

        if not self.identifier:
            raise ValueError("Callback constructor requires role as an identifier to be provided")


class Resource(Interface):

    def __init__(self, signature, header, identifier, implemented_in_kernel=False):
        super().__init__(self, signature, header, identifier, implemented_in_kernel)

        if not self.identifier:
            raise ValueError("Resource constructor requires identifier to be provided")


class Signature:
    expression = None
    type = None

    def __init__(self, expression):
        """
        Expect signature expression.
        :param expression:
        :return:
        """
        self.expression = expression

        # TODO: Determine type
        self.type = ""



__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
