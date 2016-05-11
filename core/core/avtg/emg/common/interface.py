class Interface:
    def _common_declaration(self, category, identifier):
        self.category = category
        self.short_identifier = identifier
        self.identifier = "{}.{}".format(category, identifier)
        self.declaration = None
        self.header = None
        self.implemented_in_kernel = False


class Container(Interface):
    def __init__(self, category, identifier):
        self._common_declaration(category, identifier)
        self.element_interface = None
        self.field_interfaces = {}

    def contains(self, target):
        if issubclass(type(target), Interface):
            target = target.declaration

        return self.declaration.contains(target)

    def weak_contains(self, target):
        if issubclass(type(target), Interface):
            target = target.declaration

        return self.declaration.weak_contains(target)


class Callback(Interface):
    def __init__(self, category, identifier):
        self._common_declaration(category, identifier)
        self.param_interfaces = []
        self.rv_interface = False
        self.called = False
        self.interrupt_context = False


class Resource(Interface):
    def __init__(self, category, identifier):
        self._common_declaration(category, identifier)


class KernelFunction(Interface):
    def __init__(self, identifier, header):
        self.identifier = identifier
        self.header = header
        self.declaration = None
        self.param_interfaces = []
        self.rv_interface = False
        self.called_at = {}

    def add_call(self, caller):
        if caller not in self.called_at:
            self.called_at[caller] = 1
        else:
            self.called_at[caller] += 1

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
