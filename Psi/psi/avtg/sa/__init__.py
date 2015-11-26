import re
import os
import json
import collections

import psi.components
import psi.utils


class SA(psi.components.Component):
    # TODO: Use template processor instead of predefined aspect file and target output files
    model = None

    def analyze_sources(self):
        self.logger.info("Start source analyzer instance {}".format(self.id))

        self.logger.debug("Receive abstract verification task")
        avt = self.mqs['abstract task description'].get()
        self.logger.info("Analyze source code of an abstract verification task {}".format(avt["id"]))

        # Init empty model
        self.model = collections.defaultdict(self._nested_dict)

        # Generate aspect file
        self._generate_aspect_file()

        # Perform requests
        self._perform_info_requests(avt)

        self._build_km()
        self._store_km("model.json")

        # TODO: Do not forget to place there JSON

        self.mqs['abstract task description'].put(avt)

        return

    def _nested_dict(self):
        return collections.defaultdict(self._nested_dict)

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

        for group in abstract_task["grps"]:
            self.logger.debug("Analyze source files from group {}".format(group["id"]))
            for command in group["build commands"]:
                os.environ["CC_IN_FILE"] = os.path.realpath(os.path.join(os.getcwd(), command['in files'][0]))
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
                    if path_re.match(line):
                        new_line = path_re.sub("", line)
                    else:
                        new_line = line
                    content.append(new_line)
        else:
            self.logger.warning("File {} does not exist".format(file))
        return content

    def _build_km(self):
        self.logger.info("Extract of request results")
        all_args_re = "(?:\sarg\d='[^']*')*"
        exec_re = re.compile("^([^\s]*)\s(\w*)\sret='([^']*)'({})\n".format(all_args_re))
        call_re = re.compile("^([^\s]*)\s(\w*)\s(\w*)({})\n".format(all_args_re))
        arg_re = re.compile("\sarg(\d)='([^']*)'")
        short_pair_re = re.compile("^([^\s]*)\s(\w*)\n")

        func_definition_files = [
            {"file": "execution.txt", "static": False},
            {"file": "static-execution.txt", "static": True}
        ]
        for execution_source in func_definition_files:
            self.logger.debug("Extract function definitions from {}".format(execution_source["file"]))
            content = self._import_content(execution_source["file"])
            for line in content:
                if exec_re.fullmatch(line):
                    path, name, ret_type, args = exec_re.fullmatch(line).groups()
                    if not self.model["functions"][name]["definitions"][path]:
                        self.model["functions"][name]["definitions"][path]["return value type"] = ret_type
                        self.model["functions"][name]["definitions"][path]["parameters"] = \
                            [arg[1] for arg in arg_re.findall(args)]
                        self.model["functions"][name]["definitions"][path]["static"] = execution_source["static"]
                    else:
                        raise ValueError("Function definition {} from file {} has been already described".
                                          format(name, path))
                else:
                    raise ValueError("Cannot parse line '{}' in file {}".format(line, execution_source["file"]))

        func_declaration_files = [
            {"file": "declare-function.txt", "static": False},
            {"file": "static-declare-function.txt", "static": True}
        ]
        for definition_source in func_declaration_files:
            self.logger.debug("Extract function declarations from {}".format(definition_source["file"]))
            content = self._import_content(definition_source["file"])
            for line in content:
                if short_pair_re.fullmatch(line):
                    path, name = short_pair_re.fullmatch(line).groups()
                    self.model["functions"][name]["declarations"][path] = True
                else:
                    raise ValueError("Cannot parse line '{}' in file {}".format(line, definition_source["file"]))

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
                if self.model["functions"][caller_name]["definitions"][path]:
                    if not self.model["functions"][caller_name]["definitions"][path]:
                        raise ValueError("Expect definition of function {} in {}".format(caller_name, path))
                    if not self.model["functions"][caller_name]["definitions"][path]["call"][name]:
                        self.model["functions"][caller_name]["definitions"][path]["call"][name] = []
                    self.model["functions"][caller_name]["definitions"][path]["call"][name].\
                        append([arg[1] for arg in arg_re.findall(args)])

                    if not self.model["functions"][name]["calls"][path]:
                        self.model["functions"][name]["calls"][path] = []
                    self.model["functions"][name]["calls"][path].append(
                        {
                            "called at": caller_name,
                            "parameters":  [arg[1] for arg in arg_re.findall(args)]
                        }
                    )
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
                if self.model["functions"][name]["definitions"][path]:
                    self.model["functions"][name]["definitions"][path]["exported"] = True
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
        content = self._import_content(init_file)
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
        content = self._import_content(init_file)
        self._import_global_var_initializations(self, content)

    def _import_global_var_initializations(self, content):
        # Get blocks of structure declarations
        

    def _store_km(self, km_file):
        """
        Serializes generated model in a form of JSON.
        """

        self.logger.info("Serializing generated model")
        with open(km_file, "w") as km_fh:
            json.dump(self.model, km_fh)

    main = analyze_sources

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
