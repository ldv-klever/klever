import re

__fi_regex = None
__fi_extract = None


# todo: merge with the next one
def __is_full_identifier(string):
    global __fi_regex
    global __fi_extract

    if not __fi_regex or not __fi_extract:
        __fi_regex = re.compile("(\w*)\.(\w*)")
        __fi_extract = re.compile("\*?%((?:\w*\.)?\w*)%")

    if __fi_regex.fullmatch(string) and len(__fi_regex.fullmatch(string).groups()) == 2:
        return True
    else:
        return False


def extract_full_identifier(string):
    global __fi_regex

    if __is_full_identifier(string):
        category, short_identifier = __fi_regex.fullmatch(string).groups()

        return category, "{}.{}".format(category, short_identifier)
    else:
        raise ValueError("Given string {} is not an identifier".format(string))


def yield_basetype(signature):
    pass


class __BaseType:

    def __init__(self, signature):
        self._signature = signature
        self.implementations = []
        self.path = None

    def pointer_alias(self, value):
        pass

    def add_pointer_implementations(self):
        pass

    def add_implementation(self):
        pass


class Primitive(__BaseType):

    def __init__(self, ast):
        self.__ast = ast


class Function(__BaseType):

    def __init__(self, ast):
        self.parameters = []
        self.return_value = None
        self.call = []

    @property
    def suits_for_callback(self):
        pass


class Structure(__BaseType):

    def __init__(self, ast):
        self.structure_name = None


class Array(__BaseType):

    def __init__(self, ast):
        self.element = None


class Implementation:

    def __init__(self, value, file, base_container_id=None, base_container_value=None):
        self.base_container = base_container_id
        self.base_value = base_container_value
        self.value = value
        self.file = file


class Interface:

    def __init__(self, category, identifier):
        self.category = category
        self.identifier = identifier
        self.declaration = None
        self.header = None
        self.implemented_in_kernel = False
        self.resource = False
        self.callback = False
        self.container = False
        self.field_interfaces = {}
        self.param_interfaces = []
        self.rv_interface = False

    def import_signature(self, signature):
        pass

#    @property
#    def full_identifier(self, full_identifier=None):
#        if not self.category and not full_identifier:
#            raise ValueError("Cannot determine full identifier {} without interface category")
#        elif full_identifier:
#            category, identifier = extract_full_identifier(full_identifier)
#            self.category = category
#            self.identifier = identifier
#        else:
#            return "{}.{}".format(self.category, self.identifier)

#class Signature:
#
#    def __init__(self, basetype):
#        if type(basetype) is str:
#            self.basetype = BaseType(basetype)
#        elif type(basetype) is BaseType:
#            self.basetype = basetype
#        else:
#            raise NotImplementedError("Signature require type declaration or BaseType object")


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
