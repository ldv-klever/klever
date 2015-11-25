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
        fprintf_re = re.compile("[\s\t]*\$fprintf\<\"")
        fprintf_list_re = re.compile("[\s\t]*\$fprintf_var_init_list\<\"")
        replacement = "  $fprintf<\"{}/".format(os.path.realpath(os.getcwd()))
        list_replacement = "  $fprintf_var_init_list<\"{}".format(os.path.realpath(os.getcwd()))
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
                    content.append(line)
        else:
            self.logger.warning("File {} does not exist".format(file))
        return content

    def _build_km(self):
        self.logger.info("Extract of request results")

        func_definition_file = "execution.txt"
        self.logger.debug("Extract function definitions from {}".format(func_definition_file))
        content = self._import_content(func_definition_file)
        exec_re = re.compile("^([^\s]*)\s(\w*)\sret='([^']*)('(?:\sarg\d='[^']*')*)\n")
        arg_re = re.compile("\sarg(\d)='([^']*)'")
        for line in content:
            if exec_re.fullmatch(line):
                path, name, ret_type, args = exec_re.fullmatch(line).groups()
                for arg_pair in arg_re.findall(args):
                    position, arg_type = arg_pair
            else:
                raise ValueError("Cannot parse line '{}' in file {}".format(line, func_definition_file))


        return

    def _process_callp(self):
        if not os.path.isfile(self.callp):
            return

        with open(self.callp, "r") as callp_fh:
            for line in callp_fh:
                m = re.match(r'(\S*) (\S*) (\S*) (\S*) (\S*)', line)
                if m:
                    context_file = m.group(1)
                    context_func = m.group(2)
                    context_decl_line = m.group(3)
                    call_line = m.group(4)
                    func_ptr = m.group(5)

                    self.model["functions"][context_func][context_file]["calls by pointer"][func_ptr][call_line] = 1

    def _store_km(self, km_file):
        """
        Serializes generated model in a form of JSON.
        """

        self.logger.info("Serializing generated model")
        with open(km_file, "w") as km_fh:
            json.dump(self.model, km_fh)

    main = analyze_sources

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
