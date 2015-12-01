import re
import os
import json
import collections

import psi.components
import psi.utils


def nested_dict():
    return collections.defaultdict(nested_dict)


class SA(psi.components.Component):
    # TODO: Use template processor instead of predefined aspect file and target output files
    model = None
    files = []
    modules_functions = []
    kernel_functions = []

    def analyze_sources(self):
        self.logger.info("Start source analyzer instance {}".format(self.id))

        self.logger.debug("Receive abstract verification task")
        avt = self.mqs['abstract task description'].get()
        self.logger.info("Analyze source code of an abstract verification task {}".format(avt["id"]))

        # Init empty model
        self.model = collections.defaultdict(nested_dict)

        # Generate aspect file
        self._generate_aspect_file()

        # Perform requests
        self._perform_info_requests(avt)

        # Extract data
        self._fill_model()

        # Model postprocessing
        self._process_model()

        # Save data to file
        self._save_model("model.json")

        # Save data to abstract task
        self.logger.info("Add extracted data to abstract verification task {}".format(avt["id"]))
        avt["source analysis"] = os.path.relpath("model.json", os.path.realpath(self.conf["main working directory"]))

        # Put edited task and terminate
        self.mqs['abstract task description'].put(avt)
        self.logger.info("SA successfully finished")

    def _generate_aspect_file(self):
        # Prepare aspect file
        if "template aspect" not in self.conf:
            raise TypeError("Provide SA cinfiguration property 'template aspect'")
        template_aspect_file = psi.utils.find_file_or_dir(self.logger, self.conf["main working directory"],
                                                          self.conf["template aspect"])

        self.logger.debug("Add workdir path to each fprintf command in the aspect file")
        new_file = []
        fprintf_re = re.compile("[\s\t]*\$fprintf<\"")
        fprintf_list_re = re.compile("[\s\t]*\$fprintf_var_init_list<\"")
        replacement = "  $fprintf<\"{}/".format(os.path.realpath(os.getcwd()))
        list_replacement = "  $fprintf_var_init_list<\"{}/".format(os.path.realpath(os.getcwd()))
        self.logger.info("Import template aspect from {}".format(template_aspect_file))
        with open(template_aspect_file, "r") as fh:
            for line in fh.readlines():
                if fprintf_re.match(line):
                    new_line = fprintf_re.sub(replacement, line, count=1)
                elif fprintf_list_re.match(line):
                    new_line = fprintf_list_re.sub(list_replacement, line, count=1)
                else:
                    new_line = line
                new_file.append(new_line)

        new_aspect_file = "requests.aspect"
        self.logger.info("Save aspect file to {}".format(new_aspect_file))
        with open(new_aspect_file, "w") as fh:
            fh.writelines(new_file)
        self.aspect = os.path.realpath(os.path.join(os.getcwd(), new_aspect_file))

    def _perform_info_requests(self, abstract_task):
        self.logger.info("Import source build commands")
        for group in abstract_task["grps"]:
            group["build commands"] = []
            for section in group["cc extra full desc files"]:
                file = os.path.join(self.conf["source tree root"],
                                    section["cc full desc file"])
                self.logger.debug("Import build commands from {}".format(file))
                with open(file, "r") as fh:
                    command = json.loads(fh.read())
                    group["build commands"].append(command)
                    self.files.append(command['in files'][0])

        for group in abstract_task["grps"]:
            self.logger.debug("Analyze source files from group {}".format(group["id"]))
            for command in group["build commands"]:
                os.environ["CC_IN_FILE"] = command['in files'][0]
                stdout = psi.utils.execute(self.logger, ('aspectator', '-print-file-name=include'),
                                           collect_all_stdout=True)
                psi.utils.execute(self.logger, tuple(['cif',
                                                      '--in', command['in files'][0],
                                                      '--aspect', self.aspect,
                                                      '--out', command['out file'],
                                                      '--stage', 'instrumentation',
                                                      '--back-end', 'src',
                                                      '--debug', 'DEBUG',
                                                      '--keep-prepared-file'] +
                                                     (['--keep'] if self.conf['debug'] else []) +
                                                     ['--'] +
                                                     command["opts"] +
                                                     ['-I{0}'.format(stdout[0])]),
                                  cwd=self.conf['source tree root'])

    def _import_content(self, file):
        self.logger.debug("Import file {} content".format(file))
        content = []
        if os.path.isfile(file):
            kernel = os.path.realpath(self.conf["source tree root"]) + "/"
            path_re = re.compile(kernel)
            with open(file, "r") as output_fh:
                for line in output_fh:
                    if path_re.search(line):
                        new_line = path_re.sub("", line)
                    else:
                        new_line = line
                    content.append(new_line)
        else:
            self.logger.warning("File {} does not exist".format(file))
        return content

    def _fill_model(self):
        self.logger.info("Extract of request results")
        all_args_re = "(?:\sarg\d='[^']*')*"
        exec_re = re.compile("^([^\s]*)\s(\w*)\sret='([^']*)'({})\n".format(all_args_re))
        call_re = re.compile("^([^\s]*)\s(\w*)\s(\w*)({})\n".format(all_args_re))
        arg_re = re.compile("\sarg(\d)='([^']*)'")
        short_pair_re = re.compile("^([^\s]*)\s(\w*)\n")

        func_definition_files = [
            {"file": "execution.txt", "static": False},
            {"file": "static-execution.txt", "static": True},
            {"file": "declare-function.txt", "static": False},
            {"file": "static-declare-function.txt", "static": True}
        ]
        for execution_source in func_definition_files:
            self.logger.debug("Extract function definitions or declarations from {}".format(execution_source["file"]))
            content = self._import_content(execution_source["file"])
            for line in content:
                if exec_re.fullmatch(line):
                    path, name, ret_type, args = exec_re.fullmatch(line).groups()
                    if not self.model["functions"][name]["files"][path]:
                        self.model["functions"][name]["files"][path]["return value type"] = ret_type
                        self.model["functions"][name]["files"][path]["parameters"] = [arg[1] for arg in arg_re.findall(args)]
                        prms = ", ".join(self.model["functions"][name]["files"][path]["parameters"])
                        self.model["functions"][name]["files"][path]["signature"] = "{} {}({})".format(ret_type, name, prms)
                    if not self.model["functions"][name]["files"][path]["static"]:
                        self.model["functions"][name]["files"][path]["static"] = execution_source["static"]
                else:
                    raise ValueError("Cannot parse line '{}' in file {}".format(line, execution_source["file"]))

        expand_file = "expand.txt"
        self.logger.debug("Extract macro expansions from {}".format(expand_file))
        content = self._import_content(expand_file)
        for line in content:
            if short_pair_re.fullmatch(line):
                path, name = short_pair_re.fullmatch(line).groups()
                if not self.model["macro expansions"][name][path]:
                    self.model["macro expansions"][name][path] = True
            else:
                raise ValueError("Cannot parse line '{}' in file {}".format(line, expand_file))

        func_calls_file = "call-function.txt"
        self.logger.debug("Extract function calls from {}".format(func_calls_file))
        content = self._import_content(func_calls_file)
        for line in content:
            if call_re.fullmatch(line):
                path, caller_name, name, args = call_re.fullmatch(line).groups()
                if self.model["functions"][caller_name]["files"][path]:
                    if not self.model["functions"][caller_name]["files"][path]["calls"][name]:
                        self.model["functions"][caller_name]["files"][path]["calls"][name] = list()
                    self.model["functions"][caller_name]["files"][path]["calls"][name].\
                        append([arg[1] for arg in arg_re.findall(args)])
                else:
                    raise ValueError("Expect function definition {} in file {} but it has not been extracted".
                                     format(name, path))
            else:
                raise ValueError("Cannot parse line '{}' in file {}".format(line, func_calls_file))

        export_file = "exported-symbols.txt"
        self.logger.debug("Extract export symbols from {}".format(export_file))
        content = self._import_content(export_file)
        for line in content:
            if short_pair_re.fullmatch(line):
                path, name = short_pair_re.fullmatch(line).groups()
                if self.model["functions"][name]["files"][path]:
                    self.model["functions"][name]["files"][path]["exported"] = True
                else:
                    raise ValueError("Exported function {} in {} should be defined first".format(name, path))
            else:
                raise ValueError("Cannot parse line '{}' in file {}".format(line, export_file))

        init_file = "init.txt"
        self.logger.debug("Extract initialization functions from {}".format(init_file))
        content = self._import_content(init_file)
        for line in content:
            if short_pair_re.fullmatch(line):
                path, func = short_pair_re.fullmatch(line).groups()
                if not self.model["init"][path]:
                    self.model["init"][path] = func
                else:
                    raise ValueError("Module cannot contain two initialization functions but file {} contains".
                                     format(path))
            else:
                raise ValueError("Cannot parse line '{}' in file {}".format(line, init_file))

        exit_file = "exit.txt"
        self.logger.debug("Extract exit functions from {}".format(exit_file))
        content = self._import_content(exit_file)
        for line in content:
            if short_pair_re.fullmatch(line):
                path, func = short_pair_re.fullmatch(line).groups()
                if not self.model["exit"][path]:
                    self.model["exit"][path] = func
                else:
                    raise ValueError("Module cannot contain two exit functions but file {} contains".
                                     format(path))
            else:
                raise ValueError("Cannot parse line '{}' in file {}".format(line, exit_file))

        global_file = "global.txt"
        self.logger.debug("Extract global variables from {}".format(global_file))
        content = self._import_content(global_file)
        gi_parser = GlobalInitParser(content)
        self.model["global variable initializations"] = gi_parser.analysis

    def _save_model(self, km_file):
        self.logger.info("Save source analysis results to the file {}".format(km_file))
        with open(km_file, "w") as km_fh:
            json.dump(self.model, km_fh, sort_keys=True, indent=4)

    def _process_model(self):
        self.logger.info("Process model according to provided options")

        self.modules_functions = [name for name in self.model["functions"] if
                                  len(set(self.files).intersection(self.model["functions"][name]["files"]))]

        # Collect all functions called in module
        called_functions = []
        for name in self.modules_functions:
            for path in self.model["functions"][name]["files"]:
                for called in self.model["functions"][name]["files"][path]["calls"]:
                    called_functions.append(called)

        # Collect all kernel functions called in the module
        self.kernel_functions = set(called_functions) - set(self.modules_functions)

        # Remove useless functions
        self._shrink_kernel_functions()

        # Remove useless macro expansions
        self._shrink_macro_expansions()

        # Split functions into two parts strictly according to source
        self._split_functions()

        # Remove pathes from kernel functions and keep only single header reference
        self._remove_multi_declarations()

    def _remove_multi_declarations(self):
        functions = list(self.model["kernel functions"].keys())
        for function in functions:
            files = list(self.model["kernel functions"][function]["files"].keys())
            if len(files) > 0:
                first_file = files[0]
                for key in self.model["kernel functions"][function]["files"][first_file]:
                    self.model["kernel functions"][function][key] = \
                        self.model["kernel functions"][function]["files"][first_file][key]

                for file in files:
                    self.model["kernel functions"][function]["files"][file] = True
            else:
                del self.model["kernel functions"][function]

    def _shrink_kernel_functions(self):
        names = self.model["functions"].keys()
        for name in list(names):
            if name not in self.kernel_functions and name not in self.modules_functions:
                del self.model["functions"][name]

        for name in self.model["functions"]:
            for path in self.model["functions"][name]:
                if path in self.files:
                    called = list(self.model["functions"][name]["files"][path]["call"].keys())
                    for f in called:
                        if f not in self.model["functions"]:
                            del self.model["functions"][name]["files"][path]["call"][f]

        return

    def _shrink_macro_expansions(self):
        expansions = list(self.model["macro expansions"].keys())
        for exp in expansions:
            files = list(self.model["macro expansions"][exp].keys())
            if len(set(self.files).intersection(files)) == 0:
                del self.model["macro expansions"][exp]

    def _split_functions(self):
        for function in self.kernel_functions:
            self.model["kernel functions"][function] = self.model["functions"][function]
        for function in self.modules_functions:
            self.model["modules functions"][function] = self.model["functions"][function]
        del self.model["functions"]

    main = analyze_sources


class GlobalInitParser:
    result = dict()
    indent_re = re.compile("^(\s*)\w")

    def __init__(self, content):
        self.content = content
        self.analysis = collections.defaultdict(nested_dict)
        if len(content) > 0:
            self._parse(content)

    def _get_indent(self, string):
        return self.indent_re.match(string).group(1)

    def _parse(self, lines):
        indent_str = self._get_indent(lines[0])

        begin_re = \
            re.compile("^{}Structure\sdescription\sbegin\spath='([^']*)'\sname='([^']*)'\stype='([^']*)'".
                       format(indent_str))
        init_re = re.compile("^{}Initializer list".format(indent_str))
        end_re = re.compile("^{}Structure description end".format(indent_str))

        # 0 - begin, 1 - in structure, 2 - out of structure
        state = 0
        current_block = []
        current_struct = None
        for line in lines:
            if state in [0, 2]:
                path, name, struct_type = begin_re.match(line).groups()
                self.analysis[path][name]["signature"] = "struct {} %s".format(struct_type)
                self.analysis[path][name]["struct type"] = struct_type
                current_struct = self.analysis[path][name]
                state = 1
            elif state == 1:
                if init_re.match(line):
                    current_block = []
                elif end_re.match(line):
                    self._parse_structure(current_struct["fields"], current_block)
                    current_struct = None
                    current_block = None
                    state = 2
                else:
                    current_block.append(line)
        return

    def _parse_structure(self, structure, block):
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
                current_field = structure[current_name]
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

    def _parse_array(self, array, block):
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
                current_element = array[current_index]
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

        if element["type"] == "structure":
            # Ignore Initializer list first string
            element["value"] = self._parse_structure(element["value"], block[1:])
        elif element["type"] == "function pointer":
            ret_re = re.compile("^\s*Pointed\sfunction\sreturn\stype\sdeclaration\sis\s'([^']*)'")
            args_re = re.compile("^\s*Pointed\sfunction\sargument\stype\sdeclarations\sare([^\n]*)\n")
            all_args_re = re.compile("\s'([^']*)'")

            return_type = ret_re.match(block[0]).group(1)
            args = args_re.match(block[1]).group(1)
            parameters = all_args_re.findall(args)
            value = value_re.match(block[2]).group(1)
            signature = "{} (*%name%)({})".format(return_type, ", ".join(parameters))
            element["signature"] = signature
            element["return value type"] = return_type
            element["parameters"] = parameters
            element["value"] = value
        elif element["type"] in ["primitive", "primitive pointer", "pointer to structure variable"]:
            value = value_re.match(block[0]).group(1)
            element["value"] = value
        elif element["type"] == "array":
            # Ignore Initializer list first string
            self._parse_array(element["value"], block[1:])
        else:
            raise NotImplementedError("Field type '{}' is not supported by global variables initialization parser".
                                      format(element["type"]))

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
