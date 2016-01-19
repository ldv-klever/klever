import abc
import os


from core.avtg.emg.representations import Function, FunctionBody


class AbstractTranslator(metaclass=abc.ABCMeta):

    def __init__(self, logger, conf, avt, analysis, model, header_lines=None, aspect_lines=None):
        self.logger = logger
        self.conf = conf
        self.task = avt
        self.analysis = analysis
        self.model = model
        self.files = {}
        self.aspects = {}
        self.entry_file = None
        self.model_aspects = []

        if not header_lines:
            self.additional_headers = []
        else:
            self.additional_headers = header_lines
        if not aspect_lines:
            self.additional_aspects = []
        else:
            self.additional_aspects = aspect_lines

        # Determine entry point name and file
        self.logger.info("Determine entry point name and file")
        self.__determine_entry()
        self.logger.info("Going to generate entry point function {} in file {}".
                         format(self.entry_point_name, self.entry_file))

        # Prepare entry point function
        self.logger.info("Generate C code from an intermediate model")
        self._generate_entry_point()

        # Print aspect text
        self.logger.info("Add individual aspect files to the abstract verification task")
        self._generate_aspects()

        # Add aspects to abstract task
        self.logger.info("Add individual aspect files to the abstract verification task")
        self._add_aspects()

        # Set entry point function in abstract task
        self.logger.info("Add entry point function to abstract verification task")
        self._add_entry_points()

        self.logger.info("Model translation is finished")

    @abc.abstractmethod
    def _generate_entry_point(self):
        raise NotImplementedError("Use corresponding translator instead of this abstract one")

    def __determine_entry(self):
        if len(self.analysis.inits) == 1:
            file = list(self.analysis.inits.keys())[0]
            self.logger.info("Choose file {} to add an entry point function".format(file))
            self.entry_file = file
        elif len(self.analysis.inits) < 1:
            raise RuntimeError("Cannot generate entry point without module initialization function")

        if "entry point" in self.conf:
            self.entry_point_name = self.conf["entry point"]
        else:
            self.entry_point_name = "main"

    def _generate_aspects(self):
        aspect_dir = "aspects"
        self.logger.info("Create directory for aspect files {}".format("aspects"))
        os.makedirs(aspect_dir, exist_ok=True)

        for grp in self.task['grps']:
            # Generate function declarations
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                # Aspect text
                lines = list()

                # Before file
                lines.append('before: file ("$this")\n')
                lines.append('{\n')

                if len(self.additional_headers) > 0:
                    lines.append("/* EMG additional headers */\n")
                    lines.extend(self.additional_headers)
                    lines.append("\n")
                lines.append('}\n')

                # After file
                lines.append('after: file ("$this")\n')
                lines.append('{\n')
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
                        for variable in [self.files[file]["variables"][name] for name in self.files[file]["variables"]
                                         if self.files[file]["variables"][name].use > 0]:
                            if variable.export and cc_extra_full_desc_file["in file"] != file:
                                lines.extend([variable.declare(extern=True) + ";\n"])
                            else:
                                lines.extend([variable.declare(extern=False) + ";\n"])

                lines.append("/* EMG variable initialization */\n")
                for file in self.files:
                    if "variables" in self.files[file]:
                        for variable in [self.files[file]["variables"][name] for name in self.files[file]["variables"]
                                         if self.files[file]["variables"][name].use > 0]:
                            if cc_extra_full_desc_file["in file"] == file and variable.value:
                                lines.extend([variable.declare_with_init(init=False) + ";\n"])
                lines.append("\n")

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
                    lines.append("\n")

                if len(self.additional_aspects) > 0:
                    lines.append("/* EMG additional non-generated aspects */\n")
                    lines.extend(self.additional_aspects)
                    lines.append("\n")

                name = "aspects/emg_{}.aspect".format(os.path.splitext(
                    os.path.basename(cc_extra_full_desc_file["in file"]))[0])
                with open(name, "w", encoding="ascii") as fh:
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


class Aspect(Function):

    def __init__(self, name, signature, aspect_type="after"):
        self.name = name
        self.signature = signature
        self.aspect_type = aspect_type
        self.__body = None

    @property
    def body(self, body=None):
        if not body:
            body = []

        if not self.__body:
            self.__body = FunctionBody(body)
        else:
            self.__body.concatenate(body)
        return self.__body

    def get_aspect(self):
        lines = list()
        lines.append("{}: call({}) ".format(self.aspect_type, self.signature.expression.replace("%s", self.name)) +
                     " {\n")
        lines.extend(self.body.get_lines(1))
        lines.append("}\n")
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
                self.__visit(selected, sorted_list)

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


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'


