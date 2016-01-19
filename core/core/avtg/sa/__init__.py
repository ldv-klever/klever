import glob
import jinja2
import re
import os
import json
import collections

import core.components
import core.utils


def nested_dict():
    return collections.defaultdict(nested_dict)


class SA(core.components.Component):
    # TODO: Use template processor instead of predefined aspect file and target output files
    collection = None
    files = []
    modules_functions = []
    kernel_functions = []

    def analyze_sources(self):
        self.logger.info("Start source analyzer {}".format(self.id))

        self.logger.info("Going to extract abstract verification task from queue")
        avt = self.mqs['abstract task description'].get()
        self.logger.info("Abstract verification task {} has been successfully received".format(avt["id"]))

        # Init an empty collection
        self.logger.info("Initialize an empty collection before analyzing source code")
        self.collection = collections.defaultdict(nested_dict)
        self.logger.info("An empty collection before analyzing source code has been successfully generated")

        # Generate aspect file
        self.logger.info("Prepare aspect files for CIF to use them during source code analysis")
        self._generate_aspect_file()
        self.logger.info("Aspect file has been successfully generated")

        # Perform requests
        self.logger.info("Run source code analysis")
        self._perform_info_requests(avt)
        self.logger.info("Source analysis has been finished successfully")

        # Extract data
        self.logger.info("Process and save collected data to the collection")
        self._fulfill_collection()
        self.logger.info("Collection fulfillment has been successfully finished")

        # Model postprocessing
        self.logger.info("Delete useless data from the collection and organize it better way if necessary")
        self._process_collection()
        self.logger.info("Collection processing has been successfully finished")

        # Save data to file
        collection_file = "model.json"
        self.logger.info("Save collection to {}".format(collection_file))
        self._save_collection(collection_file)
        self.logger.info("Collection has been saved succussfully")

        # Save data to abstract task
        self.logger.info("Add the collection to an abstract verification task {}".format(avt["id"]))
        # todo: better do this way: avt["source analysis"] = self.collection
        avt["source analysis"] = os.path.relpath("model.json", os.path.realpath(self.conf["main working directory"]))

        # Put edited task and terminate
        self.mqs['abstract task description'].put(avt)
        self.logger.info("Source analyzer {} successfully finished".format(self.id))

    def _generate_aspect_file(self):
        # Prepare aspect file
        if "template aspect" not in self.conf:
            raise TypeError("Source analyzer plugin need a configuration property 'template aspect' to be set")
        template_aspect_file = core.utils.find_file_or_dir(self.logger, self.conf["main working directory"],
                                                           self.conf["template aspect"])
        self.logger.info("Found file with aspect file template {}".format(template_aspect_file))

        # TODO: extract to common library (the same code as in core/avtg/tr/__init__.py).
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(os.path.dirname(template_aspect_file)),
            line_statement_prefix='//',
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=jinja2.StrictUndefined
        )

        self.logger.info('Render template {}'.format(template_aspect_file))
        with open("requests.aspect", "w", encoding="ascii") as fh:
            fh.write(env.get_template(os.path.basename(template_aspect_file)).render({
                "max_args_num": self.conf["max arguments number"],
                "arg_patterns": {i: ", ".join(["$"] * (i + 1)) for i in range(self.conf["max arguments number"])},
                "arg_printf_patterns": {i: ' '.join(["arg{}='%s'".format(j + 1) for j in range(i + 1)]) for i in range(self.conf["max arguments number"])},
                "arg_types": {i: ",".join(["$arg_type_str{}".format(j + 1) for j in range(i + 1)]) for i in range(self.conf["max arguments number"])},
                "arg_vals": {i: ",".join(["$arg_value{}".format(j + 1) for j in range(i + 1)]) for i in range(self.conf["max arguments number"])}
            }))
        self.logger.debug('Rendered template was stored into file {}'.format("requests.aspect"))

        self.aspect = os.path.realpath(os.path.join(os.getcwd(), "requests.aspect"))

    def _perform_info_requests(self, abstract_task):
        self.logger.info("Import source build commands")
        for group in abstract_task["grps"]:
            # TODO: do not extend abstract verification task description in such the way! This information isn't required for other AVTG plugins.
            group["build commands"] = []
            for section in group["cc extra full desc files"]:
                file = os.path.join(self.conf["source tree root"],
                                    section["cc full desc file"])
                self.logger.info("Import build commands from {}".format(file))
                with open(file, encoding="ascii") as fh:
                    command = json.loads(fh.read())
                    group["build commands"].append(command)
                    self.files.append(command['in files'][0])

        for group in abstract_task["grps"]:
            self.logger.info("Analyze source files from group {}".format(group["id"]))
            for command in group["build commands"]:
                os.environ["CWD"] = os.path.realpath(os.getcwd())
                os.environ["CC_IN_FILE"] = command['in files'][0]
                stdout = core.utils.execute(self.logger, ('aspectator', '-print-file-name=include'),
                                            collect_all_stdout=True)
                self.logger.info("Analyze source file {}".format(command['in files'][0]))
                core.utils.execute(self.logger, tuple(['cif',
                                                      '--in', command['in files'][0],
                                                      '--aspect', self.aspect,
                                                      '--out', command['out file'],
                                                      '--stage', 'instrumentation',
                                                      '--back-end', 'src',
                                                      '--debug', 'DEBUG'] +
                                                     (['--keep'] if self.conf['debug'] else []) +
                                                     ['--'] +
                                                     command["opts"] +
                                                     ['-I{0}'.format(stdout[0])]),
                                  cwd=self.conf['source tree root'])

    def _import_content(self, file):
        self.logger.info("Import file {} generated by CIF replacing pathes".format(file))
        content = []
        if os.path.isfile(file):
            kernel = os.path.realpath(self.conf["source tree root"]) + "/"
            path_re = re.compile(kernel)
            with open(file, encoding="ascii") as output_fh:
                for line in output_fh:
                    if path_re.search(line):
                        new_line = path_re.sub("", line)
                    else:
                        new_line = line
                    content.append(new_line)
            self.logger.debug("File {} has been successfully imported".format(file))
        else:
            self.logger.debug("File {} does not exist".format(file))
        return content

    def _fulfill_collection(self):
        all_args_re = "(?:\sarg\d+='[^']*')*"
        exec_re = re.compile("^([^\s]*)\s(\w*)\sret='([^']*)'({})(\s\.\.\.)?\n".format(all_args_re))
        call_re = re.compile("^([^\s]*)\s(\w*)\s(\w*)({})\n".format(all_args_re))
        arg_re = re.compile("\sarg(\d+)='([^']*)'")
        short_pair_re = re.compile("^([^\s]*)\s(\w*)\n")

        func_definition_files = [
            {"file": "execution.txt", "static": False},
            {"file": "static-execution.txt", "static": True},
            {"file": "declare-function.txt", "static": False},
            {"file": "static-declare-function.txt", "static": True}
        ]
        for execution_source in func_definition_files:
            self.logger.info("Extract function definitions or declarations from {}".format(execution_source["file"]))
            content = self._import_content(execution_source["file"])
            for line in content:
                if exec_re.fullmatch(line):
                    path, name, ret_type, args, is_var_args = exec_re.fullmatch(line).groups()
                    if not self.collection["functions"][name]["files"][path]:
                        self.collection["functions"][name]["files"][path]["return value type"] = ret_type
                        self.collection["functions"][name]["files"][path]["parameters"] = [arg[1] for arg in arg_re.findall(args)]
                        self.collection["functions"][name]["files"][path]["signature"] = "{} {}({})".\
                            format("$", name, "..")
                        self.collection["functions"][name]["files"][path]["variable arguments"] = is_var_args
                    if not self.collection["functions"][name]["files"][path]["static"]:
                        self.collection["functions"][name]["files"][path]["static"] = execution_source["static"]
                else:
                    raise ValueError("Cannot parse line '{}' in file {}".format(line, execution_source["file"]))

        expand_file = "expand.txt"
        self.logger.info("Extract macro expansions from {}".format(expand_file))
        content = self._import_content(expand_file)
        for line in content:
            if short_pair_re.fullmatch(line):
                path, name = short_pair_re.fullmatch(line).groups()
                if not self.collection["macro expansions"][name][path]:
                    self.collection["macro expansions"][name][path] = True
            else:
                raise ValueError("Cannot parse line '{}' in file {}".format(line, expand_file))

        func_calls_file = "call-function.txt"
        self.logger.info("Extract function calls from {}".format(func_calls_file))
        content = self._import_content(func_calls_file)
        for line in content:
            if call_re.fullmatch(line):
                path, caller_name, name, args = call_re.fullmatch(line).groups()
                if self.collection["functions"][caller_name]["files"][path]:
                    if not self.collection["functions"][caller_name]["files"][path]["calls"][name]:
                        self.collection["functions"][caller_name]["files"][path]["calls"][name] = list()
                    self.collection["functions"][caller_name]["files"][path]["calls"][name].\
                        append([arg[1] for arg in arg_re.findall(args)])
                else:
                    raise ValueError("Expect function definition {} in file {} but it has not been extracted".
                                     format(caller_name, path))
            else:
                raise ValueError("Cannot parse line '{}' in file {}".format(line, func_calls_file))

        global_file = "global.txt"
        self.logger.debug("Extract global variables from {}".format(global_file))
        content = self._import_content(global_file)
        gi_parser = GlobalInitParser(content)
        # todo: add some logging here
        self.collection["global variable initializations"] = gi_parser.analysis

        # export_file = "exported-symbols.txt"
        # self.logger.info("Extract export symbols from {}".format(export_file))
        # content = self._import_content(export_file)
        # for line in content:
        #     if short_pair_re.fullmatch(line):
        #         path, name = short_pair_re.fullmatch(line).groups()
        #         if self.collection["functions"][name]["files"][path]:
        #             self.collection["functions"][name]["files"][path]["exported"] = True
        #             self.logger.debug("Extracted exported function {} from {}".format(name, path))
        #         elif self.collection["global variable initializations"][path][name]:
        #             self.collection["global variable initializations"][path][name]["exported"] = True
        #             self.logger.debug("Extracted exported global variable {} from {}".format(name, path))
        #         else:
        #             raise ValueError("Exported symbol {} in {} should be defined first".format(name, path))
        #     else:
        #         raise ValueError("Cannot parse line '{}' in file {}".format(line, export_file))

        init_file = "init.txt"
        self.logger.info("Extract initialization functions from {}".format(init_file))
        content = self._import_content(init_file)
        for line in content:
            if short_pair_re.fullmatch(line):
                path, func = short_pair_re.fullmatch(line).groups()
                if not self.collection["init"][path]:
                    self.collection["init"][path] = func
                    self.logger.debug("Extracted Init function {} in {}".format(func, path))
                # todo: code below does not work properly
                #else:
                #    raise ValueError("Module cannot contain two initialization functions but file {} contains".
                #                     format(path))
            else:
                raise ValueError("Cannot parse line '{}' in file {}".format(line, init_file))

        exit_file = "exit.txt"
        self.logger.debug("Extract exit functions from {}".format(exit_file))
        content = self._import_content(exit_file)
        for line in content:
            if short_pair_re.fullmatch(line):
                path, func = short_pair_re.fullmatch(line).groups()
                if not self.collection["exit"][path]:
                    self.collection["exit"][path] = func
                    self.logger.debug("Extracted Exit function {} in {}".format(func, path))
                # todo: code below does not work properly
                #else:
                #    raise ValueError("Module cannot contain two exit functions but file {} contains".
                #                     format(path))
            else:
                raise ValueError("Cannot parse line '{}' in file {}".format(line, exit_file))

        if not self.conf['debug']:
            self.logger.info("Remove files with raw extracted data")
            for file in glob.glob("*.txt"):
                self.logger.debug("Remove file {}".format(file))
                os.remove(file)

    def _save_collection(self, km_file):
        with open(km_file, "w", encoding="ascii") as km_fh:
            json.dump(self.collection, km_fh, sort_keys=True, indent=4)

    def _process_collection(self):
        self.logger.info("Process collection according to provided options")

        # Get modules functions
        self.logger.info("Determine functions which are implemented in modules under consideration")
        self.modules_functions = [name for name in self.collection["functions"] if
                                  len(set(self.files).intersection(self.collection["functions"][name]["files"]))]
        self.logger.info("Found {} functions in modules under consideration".format(len(self.modules_functions)))

        # Collect all functions called in module
        self.logger.info("Determine functions which are called in considered modules")
        called_functions = []
        for name in self.modules_functions:
            for path in self.collection["functions"][name]["files"]:
                for called in self.collection["functions"][name]["files"][path]["calls"]:
                    called_functions.append(called)
        self.logger.info("Determine {} functions which are called in considered modules".format(len(called_functions)))

        # Collect all kernel functions called in the module
        self.logger.info("Extract kernel functions")
        self.kernel_functions = set(called_functions) - set(self.modules_functions)
        self.logger.info("Found {} kernel functions which are called in considered modules".
                         format(len(self.kernel_functions)))

        # Remove useless functions
        self.logger.info("Remove useless functions from the collection")
        self._shrink_kernel_functions()

        # Remove useless macro expansions
        self.logger.info("Remove useless macro-expansions from the collection")
        self._shrink_macro_expansions()

        # Split functions into two parts strictly according to source
        self.logger.info("Divide functions in the collection to kernel and modules ones")
        self._split_functions()

        # Remove pathes from kernel functions and keep only single header reference
        self.logger.info("Remove repetitions of function descriptions in the collection")
        self._remove_multi_declarations()

    def _remove_multi_declarations(self):
        functions = list(self.collection["kernel functions"].keys())
        for function in functions:
            files = list(self.collection["kernel functions"][function]["files"].keys())
            if len(files) > 0:
                first_file = files[0]
                for key in self.collection["kernel functions"][function]["files"][first_file]:
                    self.collection["kernel functions"][function][key] = \
                        self.collection["kernel functions"][function]["files"][first_file][key]

                for file in files:
                    self.collection["kernel functions"][function]["files"][file] = True
            else:
                del self.collection["kernel functions"][function]

    def _shrink_kernel_functions(self):
        names = self.collection["functions"].keys()
        for name in list(names):
            if name not in self.kernel_functions and name not in self.modules_functions:
                del self.collection["functions"][name]

        for name in self.collection["functions"]:
            for path in self.collection["functions"][name]:
                if path in self.files:
                    called = list(self.collection["functions"][name]["files"][path]["call"].keys())
                    for f in called:
                        if f not in self.collection["functions"]:
                            del self.collection["functions"][name]["files"][path]["call"][f]

    def _shrink_macro_expansions(self):
        expansions = list(self.collection["macro expansions"].keys())
        for exp in expansions:
            files = list(self.collection["macro expansions"][exp].keys())
            if len(set(self.files).intersection(files)) == 0:
                del self.collection["macro expansions"][exp]

    def _split_functions(self):
        for function in self.kernel_functions:
            self.collection["kernel functions"][function] = self.collection["functions"][function]
        for function in self.modules_functions:
            self.collection["modules functions"][function] = self.collection["functions"][function]
        del self.collection["functions"]

    main = analyze_sources


class GlobalInitParser:
    result = dict()
    indent_re = re.compile("^(\s*)\w")

    def __init__(self, content):
        # todo: add logger here if necessary
        self.content = content
        self.analysis = collections.defaultdict(nested_dict)
        if len(content) > 0:
            self._parse(content)

    def _get_indent(self, string):
        return self.indent_re.match(string).group(1)

    def _parse(self, lines):
        indent_str = self._get_indent(lines[0])

        struct_init_begin_re = \
            re.compile("^{}Structure initializer description begin path='([^']*)' name='([^']*)' type='([^']*)'".
                       format(indent_str))
        # TODO: structure type is unknown in case of (arrays of) structure pointers. Implement them later.
        struct_ptr_init_begin_re = \
            re.compile("^{}Structure pointer initializer description begin path='([^']*)' name='([^']*)'".
                       format(indent_str))
        struct_ptr_array_init_begin_re = \
            re.compile("^{}Structure pointers array initializer description begin path='([^']*)' name='([^']*)'".
                       format(indent_str))
        init_re = re.compile("^{}Initializer list".format(indent_str))
        struct_init_end_re = re.compile("^{}Structure initializer description end".format(indent_str))
        struct_ptr_init_end_re = re.compile("^{}Structure pointer initializer description end".format(indent_str))
        struct_ptr_array_init_end_re = re.compile("^{}Structure pointers array initializer description end".format(indent_str))

        # TODO: add syntax checks and corresponding exceptions!
        # 0 - begin, 1 - in initializer, 2 - out of initializer
        state = 0
        for line in lines:
            if state in [0, 2]:
                current_entity = None
                current_block = None
                match = struct_init_begin_re.match(line)
                if match:
                    path, name, struct_type = match.groups()
                    self.analysis[path][name]["signature"] = "struct {} %s".format(struct_type)
                    self.analysis[path][name]["struct type"] = struct_type
                    current_entity = self.analysis[path][name]
                else:
                    match = struct_ptr_init_begin_re.match(line)
                    if match:
                        path, name = match.groups()
                        self.analysis[path][name]["type"] = "STRUCTURE POINTER"
                        current_entity = self.analysis[path][name]
                    else:
                        match = struct_ptr_array_init_begin_re.match(line)
                        if match:
                            path, name = match.groups()
                            self.analysis[path][name]["type"] = "STRUCTURE POINTERS ARRAY"
                            current_entity = self.analysis[path][name]
                state = 1
            elif state == 1:
                if init_re.match(line):
                    current_block = []
                elif struct_init_end_re.match(line):
                    self._parse_structure(current_entity["fields"], current_block)
                    state = 2
                elif struct_ptr_init_end_re.match(line):
                    current_entity["initializer"] = re.match("^\s*Value\sis\s'([^']*)'", current_block[1]).group(1)
                    state = 2
                elif struct_ptr_array_init_end_re.match(line):
                    self._parse_array(current_entity["elements"], current_block)
                    state = 2
                else:
                    current_block.append(line)
        return

    def _parse_structure(self, fields, block):
        # Do not parse empty initializers like for anx9805_i2c_func (drivers/gpu/drm/nouveau/nouveau.ko) and
        # lme2510_props (drivers/media/usb/dvb-usb-v2/dvb-usb-lmedm04.ko)
        if not len(block):
            return

        indent_str = self._get_indent(block[0])
        begin_re = re.compile("^{}Structure field initialization".format(indent_str))
        name_re = re.compile("^{}Field\sname\sis\s'([^']*)'".format(indent_str))
        type_re = re.compile("^{}Type\sis\s'([^']*)'".format(indent_str))
        sign_re = re.compile("^{}Declaration\sis\s'([^']*)'".format(indent_str))

        # 0 - out of field description,
        # 1 - at the beginning,
        # 2 - with filled name
        # 3 - with filled type
        # 4 - with filled signature
        state = 0

        current_field = None
        current_block = []
        for line in block:
            if state == 0:
                # Skip the first line
                state = 1
            elif state == 1:
                # Parse name
                current_block = None
                current_name = name_re.match(line).group(1)
                current_field = fields[current_name]
                state = 2
            elif state == 2:
                field_type = type_re.match(line).group(1)
                current_field["type"] = field_type
                state = 3
            elif state == 3:
                signature = sign_re.match(line).group(1)
                current_field["signature"] = signature
                current_block = []
                state = 4
            elif state == 4:
                if begin_re.match(line):
                    self._parse_element(current_field, current_block)
                    state = 1
                else:
                    current_block.append(line)

        # Parse last element
        self._parse_element(current_field, current_block)

    def _parse_array(self, elements, block):
        indent_str = self._get_indent(block[0])
        begin_re = re.compile("^{}Array\selement\sinitialization".format(indent_str))
        index_re = re.compile("^{}Array\sindex\sis\s'([^']*)'".format(indent_str))
        type_re = re.compile("^{}Type\sis\s'([^']*)'".format(indent_str))
        sign_re = re.compile("^{}Declaration\sis\s'([^']*)'".format(indent_str))

        # 0 - out of field description,
        # 1 - at the beginning,
        # 2 - with filled name
        # 3 - with filled type
        # 4 - with filled signature
        state = 0

        current_element = None
        current_block = []
        for line in block:
            if state == 0:
                # Skip the first line
                state = 1
            elif state == 1:
                # Parse name
                current_block = None
                current_index = index_re.match(line).group(1)
                current_element = elements[current_index]
                state = 2
            elif state == 2:
                field_type = type_re.match(line).group(1)
                current_element["type"] = field_type
                state = 3
            elif state == 3:
                signature = sign_re.match(line).group(1)
                current_element["signature"] = signature
                current_block = []
                state = 4
            elif state == 4:
                if begin_re.match(line):
                    self._parse_element(current_element, current_block)
                    state = 1
                else:
                    current_block.append(line)

        # Parse last element
        self._parse_element(current_element, current_block)

    def _parse_element(self, element, block):
        value_re = re.compile("^\s*Value\sis\s'([^']*)'")
        string_value_re = re.compile("^\s*Value\sis\s'(\"[^']*\")'")
        array_re = re.compile("^\s*Array\selement\sinitialization")
        struct_re = re.compile("^\s*Structure field initialization")

        if element["type"] == "structure":
            # Ignore "Initializer list" first string
            self._parse_structure(element["fields"], block[1:])
        elif element["type"] == "function pointer":
            ret_re = re.compile("^\s*Pointed\sfunction\sreturn\stype\sdeclaration\sis\s'([^']*)'")
            args_re = re.compile("^\s*Pointed\sfunction\sargument\stype\sdeclarations\sare([^\n]*)\n")
            all_args_re = re.compile("\s'([^']*)'")

            return_type = ret_re.match(block[0]).group(1)
            args = args_re.match(block[1]).group(1)
            parameters = all_args_re.findall(args)
            value = value_re.match(block[2]).group(1)
            signature = "{} (*%name%)({})".format("$", "..")
            element["signature"] = signature
            element["return value type"] = return_type
            element["parameters"] = parameters
            element["value"] = value
        elif element["type"] in ["primitive", "primitive pointer", "pointer to structure variable",
                                 "pointer to pointer"]:
            if not value_re.match(block[0]):
                # TODO: Remove this when CIF will always return only Value for primitives
                element["value"] = None
            else:
                value = value_re.match(block[0]).group(1)
                element["value"] = value
        elif element["type"] == "array":
            # Parse strings (arrays of chars)
            if len(block) == 1:
                match = string_value_re.match(block[0])
                if match:
                    element["value"] = match.group(1)
            # Parse non strings
            if "value" not in element:
                # Ignore "Initializer list" first string
                self._parse_array(element["elements"], block[1:])
        elif element["type"] == "typedef":
            # Check typedef element
            if value_re.match(block[0]):
                value = value_re.match(block[0]).group(1)
                element["value"] = value
            # Do not parse empty initializers like for parport_sysctl_template (drivers/parport/parport.ko)
            # Ignore "Initializer list" first string
            elif len(block[1:]):
                if array_re.match(block[1]):
                    self._parse_array(element["elements"], block[1:])
                elif struct_re.match(block[1]):
                    self._parse_structure(element["fields"], block[1:])
                else:
                    raise NotImplementedError("Could not parse element initializer")
        else:
            raise NotImplementedError("Field type '{}' is not supported by global variables initialization parser".
                                      format(element["type"]))

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
