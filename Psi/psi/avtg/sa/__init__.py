import re
import os
import json
import collections

import psi.components
import psi.utils


class SA(psi.components.Component):
    cif_output = [
        "declare_func.txt",
        "static-declare_func.txt"
        "call.txt",
        "execution.txt",
        "static-execution.txt",
        "static-call.txt",
        "exported.txt",
        "define.txt",
        "callp.txt",
        "object_files.txt"
    ]
    exe_files = [
        "execution.txt",
        "static-execution.txt"
    ]
    call_files = [
        "static-call.txt",
        "call.txt"
    ]
    decl_files = [
        "static-declare_func.txt",
        "declare_func.txt"
    ]
    object = "object_files.txt"
    define = "define.txt"
    exported = "exported.txt"
    callp = "callp.txt"
    model = None

    def analyze_sources(self):
        self.logger.info("Start source analyzer instance {}".format(self.id))

        self.logger.debug("Receive abstract verification task")
        avt = self.mqs['abstract task description'].get()
        self.logger.info("Analyze source code of an abstract verification task {}".format(avt["id"]))

        # TODO: Put logic here
        self._init_source_processor()
        self._process_bc(avt)

        # TODO: Do not forget to place there JSON

        self.mqs['abstract task description'].put(avt)

        return

    def nested_dict(self):
        return collections.defaultdict(self.nested_dict)

    def _init_source_processor(self):
        self.logger.info("Check necessary SA options")

        # Init empty model
        self.model = collections.defaultdict(self.nested_dict)

        # Prepare aspect file
        if "template aspect" not in self.conf:
            raise TypeError("Provide SA cinfiguration property 'template aspect'")
        template_aspect_file = psi.utils.find_file_or_dir(self.logger, self.conf["main working directory"],
                                                          self.conf["template aspect"])

        new_file = []
        fprintf_expr = "\$fprintf\<\""
        printf_re = re.compile("[\s\t]*" + fprintf_expr)
        replacement = "  $fprintf<\"{}/".format(os.path.realpath(os.getcwd()))
        self.logger.info("Import template aspect from {}".format(template_aspect_file))
        with open(template_aspect_file, "r") as fh:
            for line in fh.readlines():
                if printf_re.match(line):
                    new_line = printf_re.sub(replacement, line, count=1)
                else:
                    new_line = line
                new_file.append(new_line)

        new_aspect_file = "requests.aspect"
        self.logger.info("Save aspect file to {}".format(new_aspect_file))
        with open(new_aspect_file, "w") as fh:
            fh.writelines(new_file)
        self.aspect = os.path.realpath(os.path.join(os.getcwd(), new_aspect_file))

    def _process_bc(self, abstract_task):
        self.logger.info("Processing build commands")

        current_command = 0
        number_of_commands = 0
        src = ""

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
            self.logger.debug("Analyze build commands from groups {}".format(group["id"]))
            for command in group["build commands"]:
                self._process_cc_cmd(command)

        # Process output to remove useless printings before importing data
        self._normalize_cif_output()
        self._remove_duplicate_lines()

        self._build_km()
        self._store_km("model.json")

    def _process_cc_cmd(self, command):
        os.environ['CC'] = command["out file"]

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

    def _normalize_cif_output(self):
        print("Normalizing CIF output")

        for output_file in self.cif_output:
            if not os.path.isfile(output_file):
                print("Couldn't find '{}'".format(output_file))
                continue

            with open(output_file, "r") as output_fh:
                with open(output_file + ".temp", "w") as temp_fh:
                    for line in output_fh:
                        m = re.match(r'(\S*) (.*)', line)

                        if m:
                            path = m.group(1)
                            rest = m.group(2)

                            path = os.path.normpath(path)
                            path = re.sub(self.conf['source tree root'] + "/", "", path)

                            temp_fh.write("{} {}\n".format(path, rest))

            os.remove(output_file)
            os.rename(output_file + ".temp", output_file)

    def _remove_duplicate_lines(self):
        print("Removing duplicate lines in CIF output")

        for output_file in self.cif_output:
            if not os.path.isfile(output_file):
                continue

            dup_lines = dict()

            with open(output_file, "r") as output_fh:
                with open(output_file + ".temp", "w") as temp_fh:
                    for line in output_fh:
                        if line not in dup_lines:
                            temp_fh.write(line)
                            dup_lines[line] = 1

            os.remove(output_file)
            os.rename(output_file + ".temp", output_file)

    def _process_of(self):
        print("Processing translation units")
        with open(self.object, "r") as of_fh:
            for line in of_fh:
                m = re.match(r'(\S*) (\S*)', line)
                if m:
                    source_file = m.group(1)
                    object_file = m.group(2)

                    self.model["source files"][source_file]["compiled to"][object_file] = 1
                    self.model["object files"][object_file]["compiled from"][source_file] = 1

    def _process_exe(self):
        print("Processing definitions")
        for exe_file in self.exe_files:
            if not os.path.isfile(exe_file):
                continue

            with open(exe_file, "r") as exe_fh:
                for line in exe_fh:
                    m = re.match(r'(\S*) (\S*) (\S*) (.*)', line)
                    if m:
                        src_file = m.group(1)
                        decl_line = m.group(2)
                        func = m.group(3)
                        func_signature = m.group(4)
                        func_type = "ordinary"

                        if re.search(r'static', exe_file):
                            func_type = "static"

                        if func in self.model["functions"] and src_file in self.model["functions"][func]:
                            raise ValueError("Function '{}' is defined more than once in '{}'".format(func, src_file))

                        self.model["functions"][func][src_file]["type"] = func_type
                        self.model["functions"][func][src_file]["signature"] = func_signature
                        self.model["functions"][func][src_file]["decl line"] = decl_line


    def _process_exp(self):
        # Linux kernel only
        if not os.path.isfile(self.exported):
            return
        print("Processing exported functions")

        with open(self.exported, "r") as exp_fh:
            for line in exp_fh:
                m = re.match(r'(\S*) (\S*)', line)
                if m:
                    src_file = m.group(1)
                    func = m.group(2)

                    # Variables can also be exported
                    if func not in self.model["functions"]:
                        continue
                    elif src_file not in self.model["functions"][func]:
                        continue

                    self.model["functions"][func][src_file]["type"] = "exported"


    def _process_def(self):
        if not os.path.isfile(self.define):
            return
        print("Processing macro functions")

        with open(self.define, "r") as def_fh:
            for line in def_fh:
                m = re.match(r'(\S*) (\S*)', line)
                if m:
                    src_file = m.group(1)
                    macro = m.group(2)

                    self.model["macro"][macro][src_file] = 1

    def _process_decl(self):
        print("Processing declarations")
        for decl_file in self.decl_files:
            if not os.path.isfile(decl_file):
                continue

            with open(decl_file, "r") as decl_fh:
                for line in decl_fh:
                    m = re.match(r'(\S*) (\S*)', line)
                    if m:
                        decl_file = m.group(1)
                        decl_name = m.group(2)

                        if decl_name not in self.model["functions"]:
                            continue

                        decl_type = "ordinary"
                        if re.search(r'static', decl_file):
                            decl_type = "static"

                        for src_file in self.model["functions"][decl_name]:
                            if ((self.model["functions"][decl_name][src_file]["type"] == decl_type) or
                               (self.model["functions"][decl_name][src_file]["type"] == "exported")):
                                if src_file == decl_file:
                                    self.model["functions"][decl_name][src_file]["declared in"][decl_file] = 1
                                elif list(set(self.model["source files"][src_file]["compiled to"]) &
                                          set(self.model["source files"][decl_file]["compiled to"])):
                                    self.model["functions"][decl_name][src_file]["declared in"][decl_file] = 1
                            elif src_file == "unknown":
                                self.model["functions"][decl_name]["unknown"]["declared in"][decl_file] = 1

    def _build_km(self):
        print("Building KM")

        global call_type
        global context_file
        global context_func
        global context_decl_line
        global call_line
        global func
        global call_decl_line

        for call_file in self.call_files:
            if not os.path.isfile(call_file):
                continue

            with open(call_file, "r") as call_fh:
                call_type = "ordinary"
                if re.search(r'static', call_file):
                    call_type = "static"

                for line in call_fh:
                    m = re.match(r'(\S*) (\S*) (\S*) (\S*) (\S*) (\S*)', line)
                    if m:

                        context_file = m.group(1)
                        context_func = m.group(2)
                        context_decl_line = m.group(3)
                        call_line = m.group(4)
                        func = m.group(5)
                        call_decl_line = m.group(6)

                        self._match_call_and_def()

        self._reverse_km()
        self._process_callp()

    def _match_call_and_def(self):
        # Some Linux workarounds
        if re.match(r'(__builtin)|(__compiletime)', func):
            return
        if re.match(r'__bad', func) and func not in self.model["functions"]:
            return
    
        if func not in self.model["functions"]:
            self.model["functions"][func]["unknown"]["decl line"] = "unknown"
            self.model["functions"][func]["unknown"]["type"] = call_type
            self.model["functions"][func]["unknown"]["called in"][context_func][context_file][call_line] = 1
    
            #raise ValueError("NO_DEFS_IN_self.model: {}".format(func))
            self.logger.warning("NO_DEFS_IN_self.model: {}".format(func))
    
            return
    
        possible_src = []
        for src_file in self.model["functions"][func]:
            if src_file == "unknown":
                continue
            elif (self.model["functions"][func][src_file]["type"] == call_type or
                  self.model["functions"][func][src_file]["type"] == "exported"):
                possible_src.append(src_file)
    
        if len(possible_src) == 0:
            self.model["functions"][func]["unknown"]["decl line"] = "unknown"
            self.model["functions"][func]["unknown"]["type"] = call_type
            self.model["functions"][func]["unknown"]["called in"][context_func][context_file][call_line] = 0
    
            # It will be a generator's fault until it supports aliases
            if not re.match(r'__mem', func):
                #raise ValueError("NO_POSSIBLE_DEFS: {}".format(func))
                self.logger.warning("NO_POSSIBLE_DEFS: {}".format(func))
    
        elif len(possible_src) == 1:
            src_file = possible_src[0]
            self.model["functions"][func][src_file]["called in"][context_func][context_file][call_line] = 7
    
        else:
            found_src = [None] * 7
            for x in range(0, len(found_src)):
                found_src[x] = []
    
            for src_file in possible_src:
                if self.model["functions"][func][src_file]["type"] == "exported":
                    found_src[1].append(src_file)
                    continue
    
                decl_line = self.model["functions"][func][src_file]["decl line"]
    
                if src_file == context_file:
                    found_src[6].append(src_file)
                elif (call_decl_line == decl_line and
                      list(set(self.model["source files"][src_file]["compiled to"]) &
                           set(self.model["source files"][context_file]["compiled to"]))):
                    found_src[5].append(src_file)
                elif (list(set(self.model["source files"][src_file]["compiled to"]) &
                           set(self.model["source files"][context_file]["compiled to"]))):
                    found_src[4].append(src_file)
                elif (call_type == "ordinary" and
                      ("used in" in self.model["source files"][src_file] and
                       "used in" in self.model["source files"][context_file] and
                       list(set(self.model["source files"][src_file]["used in"]) &
                            set(self.model["source files"][context_file]["used in"])))):
                    found_src[3].append(src_file)
                elif call_type == "ordinary":
                    for decl_file in self.model["functions"][func][src_file]["declared in"]:
                        if list(set(self.model["source files"][decl_file]["compiled to"]) &
                                set(self.model["source files"][context_file]["compiled to"])):
                            found_src[2].append(src_file)
                            break
    
            found_src[0].append("unknown")
    
            for x in range(len(found_src) - 1, -1, -1):
                if found_src[x] != []:
                    if len(found_src[x]) > 1:
                        raise ValueError("MULTIPLE_MATCHES: {} call in {}".format(func, context_file))
                    for src_file in found_src[x]:
                        self.model["functions"][func][src_file]["called in"][context_func][context_file][call_line] = x
    
                        if src_file == "unknown":
                            self.model["functions"][func][src_file]["decl line"] = "unknown"
                            self.model["functions"][func][src_file]["type"] = call_type
    
                            #raise ValueError("CANT_MATCH_DEF: {} call in {}".format(func, context_file))
                            self.logger.warning("CANT_MATCH_DEF: {} call in {}".format(func, context_file))
                    break

    def _reverse_km(self):
        for func in self.model["functions"]:
            for src_file in self.model["functions"][func]:
                for context_func in self.model["functions"][func][src_file]["called in"]:
                    for context_file in self.model["functions"][func][src_file]["called in"][context_func]:
                        if context_func in self.model["functions"]:
                            self.model["functions"][context_func][context_file]["calls"][func][src_file] = \
                                self.model["functions"][func][src_file]["called in"][context_func][context_file]

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

        print("Serializing generated model")
        with open(km_file, "w") as km_fh:
            json.dump(self.model, km_fh)


    main = analyze_sources

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
