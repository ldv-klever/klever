import abc
import os
import re

from psi.avtg.emg.interfaces import Signature


class AbstractTranslator(metaclass=abc.ABCMeta):

    def __init__(self, logger, conf, avt, analysis, model):
        self.logger = logger
        self.conf = conf
        self.task = avt
        self.analysis = analysis
        self.model = model
        self.files = {}
        self.aspects = {}
        self.model_map = ModelMap()
        self.entry_file = None
        self.model_aspects = []

        # Determine entry point name and file
        self.__determine_entry()

        self._generate_entry_point()
        self._generate_aspects()
        self._add_aspects()
        self._add_entry_points()
        return

    @abc.abstractmethod
    def _generate_entry_point(self):
        raise NotImplementedError("Use corresponding translator instead of this abstract one")

    def __determine_entry(self):
        if len(self.analysis.inits) == 1:
            file = list(self.analysis.inits.keys())[0]
            self.logger.info("Choose file {} for entry point function".format(file))
            self.entry_file = file
        elif len(self.analysis.inits) < 1:
            raise RuntimeError("Cannot generate entry point without module initialization function")

        if "entry point" in self.conf:
            self.entry_point_name = self.conf["entry point"]
        else:
            self.entry_point_name = "main"
        self.logger.info("Genrate entry point function {}".format(self.entry_point_name))

    def _import_mapping(self):
        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                if 'plugin aspects' not in cc_extra_full_desc_file:
                    pass

    def _generate_aspects(self):
        self.logger.info("Create aspects diretory in EMG working directory")
        os.makedirs("aspects", exist_ok=True)

        for grp in self.task['grps']:
            # Generate function declarations
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                lines = []
                lines.append('before: file ("$this")\n')
                lines.append('{\n')
                lines.append("#include <verifier/rcv.h>\n\n")
                lines.append("/* EMG Function declarations */\n")
                for file in self.files:
                    if "functions" in self.files[file]:
                        for function in [self.files[file]["functions"][name] for name in self.files[file]["functions"]]:
                            if function.export and cc_extra_full_desc_file["in file"] != file:
                                lines.extend(function.get_declaration(extern=True))
                            else:
                                lines.extend(function.get_declaration(extern=False))
                lines.append("\n")

                lines.append("/* EMG variable declarations */\n")
                for file in self.files:
                    if "variables" in self.files[file]:
                        for variable in [self.files[file]["variables"][name] for name in self.files[file]["variables"]]:
                            if variable.export and cc_extra_full_desc_file["in file"] != file:
                                lines.extend(variable.get_declaration(extern=True))
                            else:
                                lines.extend(variable.get_declaration(extern=False))
                lines.append("}\n")

                lines.append('after: file ("$this")\n')
                lines.append('{\n')
                lines.append("/* EMG function definitions */\n")
                for file in self.files:
                    if "functions" in self.files[file]:
                        for function in [self.files[file]["functions"][name] for name in self.files[file]["functions"]]:
                            if cc_extra_full_desc_file["in file"] == file:
                                lines.extend(function.get_definition())
                                lines.append("\n")
                lines.append("}\n")

                lines.append("/* EMG kernel function models */\n")
                for aspect in self.model_aspects:
                    lines.extend(aspect.get_aspect())

                name = "aspects/emg_{}.aspect".format(os.path.splitext(
                    os.path.basename(cc_extra_full_desc_file["in file"]))[0])
                with open(name, "w") as fh:
                    fh.writelines(lines)

                path = os.path.relpath(os.path.abspath(name), os.path.realpath(self.conf['source tree root']))
                self.logger.info("Add aspect file {}".format(path))
                self.aspects[cc_extra_full_desc_file["in file"]] = path

    def _add_aspects(self):
        for grp in self.task['grps']:
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                if cc_extra_full_desc_file["in file"] in self.aspects:
                    if 'plugin aspects' not in cc_extra_full_desc_file:
                        cc_extra_full_desc_file['plugin aspects'] = []
                    cc_extra_full_desc_file['plugin aspects'].append(
                        {
                            "plugin": "EMG",
                            "aspects": [self.aspects[cc_extra_full_desc_file["in file"]]]
                        }
                    )

    def _add_entry_points(self):
        self.task["entry points"] = [self.entry_point_name]


class Variable:
    name_re = re.compile("\(?\*?%s\)?")

    def __init__(self, name, file, signature=Signature("void *%s"), export=False):
        self.name = name
        self.file = file
        if not signature:
            raise ValueError("Attempt to create variable {} without signature".format(name))
        self.signature = signature
        self.value = None
        self.export = export

    def declare_with_init(self):
        declaration = self.signature.expression
        if self.signature.pointer and self.signature.type_class == "struct":
            alloc = ModelMap.init_pointer(self.signature)
            self.value = alloc
        return self.declare()

    def declare(self, set_value=True):
        declaration = self.signature.expression
        if self.signature.type_class == "function":
            declaration = self.name_re.sub("(* {})".format(self.name), declaration)
        else:
            if self.signature.pointer:
                declaration = declaration.replace("*%s", "*{}".format(self.name))
                declaration = declaration.replace("%s", "*{}".format(self.name))
            else:
                declaration = declaration.replace("%s", self.name)

        if self.value and set_value:
            declaration += " = {}".format(self.value)
        declaration += ";"
        return declaration

    def get_declaration(self, extern=False):
        if extern:
            declaration = self.declare(set_value=False)
            declaration = "extern " + declaration
        else:
            declaration = self.declare()
        return [declaration + "\n"]


class Function:

    def __init__(self, name, file, signature=Signature("void %s(void)"), export=False):
        self.name = name
        self.file = file
        self.signature = signature
        self.export = export
        self.__body = None

    @property
    def body(self, body=[]):
        if not self.__body:
            self.__body = FunctionBody(body)
        else:
            self.__body.concatenate(body)
        return self.__body

    def get_declaration(self, extern=False):
        declaration = self.signature.expression
        declaration = self.signature.expression.replace("%s", self.name)
        declaration += ';'

        if extern:
            declaration = "extern " + declaration
        return [declaration + "\n"]

    def get_definition(self):
        if self.signature.type_class == "function" and not self.signature.pointer:
            lines = []
            lines.append(self.signature.expression.replace("%s", self.name) + "{\n")
            lines.extend(self.body.get_lines(1))
            lines.append("}\n")
            return lines
        else:
            raise TypeError("Signature '{}' with class '{}' is not a function or it is a function pointer".
                            format(self.expression, self.type_class))


class Aspect(Function):

    def __init__(self, name, signature, aspect_type="after"):
        self.name = name
        self.signature = signature
        self.aspect_type = aspect_type
        self.__body = None

    @property
    def body(self, body=[]):
        if not self.__body:
            self.__body = FunctionBody(body)
        else:
            self.__body.concatenate(body)
        return self.__body

    def get_aspect(self):
        lines = []
        lines.append("{}: call({}) ".format(self.aspect_type, self.signature.expression.replace("%s", self.name))
                     + " {\n")
        lines.extend(self.body.get_lines(1))
        lines.append("}\n")
        return lines

class FunctionBody:
    indent_re = re.compile("^(\t*)([^\s]*.*)")

    def __init__(self, body=[]):
        self.__body = []

        if len(body) > 0:
            self.concatenate(body)

    def _split_indent(self, string):
        split = self.indent_re.match(string)
        return {
            "indent": len(split.group(1)),
            "statement": split.group(2)
        }

    def concatenate(self, statements):
        if type(statements) is list:
            for line in statements:
                splitted = self._split_indent(line)
                self.__body.append(splitted)
        elif type(statements) is str:
            splitted = self._split_indent(statements)
            self.__body.append(splitted)
        else:
            raise TypeError("Can add only string or list of strings to function body but given: {}".
                            format(str(type(statements))))

    def get_lines(self, start_indent=1):
        lines = []
        for splitted in self.__body:
            line = (start_indent + splitted["indent"]) * "\t" + splitted["statement"] + "\n"
            lines.append(line)
        return lines


class Entry:

    def __init__(self, logger, modules):
        self.logger = logger
        self.modules = modules

    def __load_order(self, modules):
        sorted_list = []

        unmarked = list(modules)
        self.marked = {}
        while len(unmarked) > 0:
            selected = unmarked.pop(0)
            if selected not in self.marked:
                self.__visit(selected, sorted_list, modules)

        return sorted_list

    def __visit(self, selected, sorted_list):
        if selected in self.marked and self.marked[selected] == 0:
            self.logger.debug('Given graph is not a DAG')

        elif selected not in self.marked:
            self.marked[selected] = 0

            if selected in self.modules:
                for module in self.modules[selected]:
                    self.__visit(module, sorted_list)

            self.marked[selected] = 1
            sorted_list.append(selected)


class ModelMap:

    # todo: implement all models
    mem_function_map = {
        "ALLOC": "ldv_successful_malloc",
        "ALLOC_RECURSIVELY": "ldv_successful_malloc",
        "FREE": "free",
        "FREE_RECURSIVELY": None,
        "ZINIT": "ldv_init_zalloc",
        "ZINIT_STRUCT": None,
        "INIT_STRUCT": None,
        "INIT_RECURSIVELY": None,
        "ZINIT_RECURSIVELY": None,
    }
    irq_function_map = {
        "GET_CONTEXT": None,
        "IRQ_CONTEXT": None,
        "PROCESS_CONTEXT": None
    }

    mem_function_re = "\$({})\(%(\w+)%(?:,\s?(\w+))?\)"
    irq_function_re = "\$({})"

    @staticmethod
    def init_pointer(signature):
        if signature.type_class in ["struct", "primitive"] and signature.pointer:
            return "{}(sizeof(struct {}))".format(ModelMap.mem_function_map["ZINIT"], signature.structure_name)
        else:
            raise NotImplementedError("Cannot initialize label {} which is not pointer to structure or primitive".
                                      format(signature.name, signature.type_class))

    def __replace_mem_call(self, match):
        function, label_name, flag = match.groups()
        if function not in self.mem_function_map:
            raise NotImplementedError("Model of {} is not supported".format(function))
        elif not self.mem_function_map[function]:
            raise NotImplementedError("Set implementation for the function {}".format(function))

        # Create function call
        if label_name not in self.process.labels:
            raise ValueError("Process {} has no label {}".format(self.process.name, label_name))
        signature = self.process.labels[label_name].signature
        if signature.type_class in ["struct", "primitive"] and signature.pointer:
            return "{}(sizeof(struct {}))".format(self.mem_function_map[function], signature.structure_name)
        else:
            raise NotImplementedError("Cannot initialize signature {} which is not pointer to structure or primitive".
                                      format(signature.expression, signature.type_class))

    def __replace_irq_call(self, match):
        function = match.groups()
        if function not in self.mem_function_map:
            raise NotImplementedError("Model of {} is not supported".format(function))
        elif not self.mem_function_map[function]:
            raise NotImplementedError("Set implementation for the function {}".format(function))

        # Replace
        return self.mem_function_map[function]

    def replace_models(self, process, string):
        self.process = process
        ret = string
        # Memory functions
        for function in self.mem_function_map:
            regex = re.compile(self.mem_function_re.format(function))
            ret = regex.sub(self.__replace_mem_call, ret)

        # IRQ functions
        for function in self.irq_function_map:
            regex = re.compile(self.irq_function_re.format(function))
            ret = regex.sub(self.__replace_irq_call, ret)
        return ret

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'


