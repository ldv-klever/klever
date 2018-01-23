#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import collections
import glob
import json
import os
import re

import core.vtg.utils
import core.vtg.plugins
import jinja2
from core.vtg.sa.initparser import parse_initializations

import core.utils


def nested_dict():
    return collections.defaultdict(nested_dict)


class SA(core.vtg.plugins.Plugin):
    depend_on_rule = False

    def __init__(self, conf, logger, parent_id, callbacks, mqs, locks, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False):
        # Rule specification descriptions were already extracted when getting VTG callbacks.
        self.rule_spec_descs = None

        super(SA, self).__init__(conf, logger, parent_id, callbacks, mqs, locks, vals, id, work_dir, attrs,
                                 separate_from_parent, include_child_resources)

        # TODO: Use template processor instead of predefined aspect file and target output files
        self.collection = None
        self.files = []
        self.used_functions = set()

    def analyze_sources(self):
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
        self._perform_info_requests(self.abstract_task_desc)
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
        self.logger.info("Add the collection to an abstract verification task {}".format(self.abstract_task_desc["id"]))
        # todo: better do this way: avt["source analysis"] = self.collection
        self.abstract_task_desc["source analysis"] = os.path.relpath("model.json", os.path.realpath(
            self.conf["main working directory"]))

    def _signify_file(self, cc_file):
        files = [
            'static-execution.txt',
            'execution.txt',
            'static-declare_func.txt',
            'declare_func.txt',
            'init.txt',
            'exit.txt',
            'expand.txt',
            'call-function.txt',
            'typedefs.txt'
        ]
        self.logger.info("Add information about current processing file {!r}".format(cc_file))
        for f in files:
            with open(f, "a", encoding="utf8") as fh:
                fh.writelines(['path: {!r}\n'.format(cc_file)])

    def _generate_aspect_file(self):
        # Prepare aspect file
        if "template aspect" not in self.conf:
            raise TypeError("Source analyzer plugin need a configuration property 'template aspect' to be set")
        template_aspect_file = core.utils.find_file_or_dir(self.logger, self.conf["main working directory"],
                                                           self.conf["template aspect"])
        self.logger.info("Found file with aspect file template {}".format(template_aspect_file))

        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(os.path.dirname(template_aspect_file)),
            line_statement_prefix='//',
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=jinja2.StrictUndefined
        )

        self.logger.info('Render template {}'.format(template_aspect_file))
        with open("requests.aspect", "w", encoding="utf8") as fh:
            fh.write(env.get_template(os.path.basename(template_aspect_file)).render({
                "max_args_num": self.conf["max arguments number"],
                "arg_patterns": {i: ", ".join(["$"] * (i + 1)) for i in range(self.conf["max arguments number"])},
                "arg_printf_patterns": {i: ' '.join(["arg{}='%s'".format(j + 1) for j in range(i + 1)])
                                        for i in range(self.conf["max arguments number"])},
                "arg_types": {i: ",".join(["$arg_type_str{}".format(j + 1) for j in range(i + 1)])
                              for i in range(self.conf["max arguments number"])},
                "arg_values": {i: ",".join(["$arg_value{}".format(j + 1) for j in range(i + 1)])
                               for i in range(self.conf["max arguments number"])},
                "arg_vals": {i: ",".join(["$arg_val{}".format(j + 1) for j in range(i + 1)])
                             for i in range(self.conf["max arguments number"])}
            }))
        self.logger.debug('Rendered template was stored into file {}'.format("requests.aspect"))

        self.aspect = os.path.realpath(os.path.join(os.getcwd(), "requests.aspect"))

    def _perform_info_requests(self, abstract_task):
        self.logger.info("Import source build commands")
        b_cmds = {}
        for group in abstract_task["grps"]:
            b_cmds[group['id']] = []
            for section in group["cc extra full desc files"]:
                file = os.path.join(self.conf["main working directory"],
                                    section["cc full desc file"])
                self.logger.info("Import build commands from {}".format(file))
                with open(file, encoding="utf8") as fh:
                    command = json.loads(fh.read())
                    b_cmds[group['id']].append(command)
                    self.files.append(command['in files'][0])

        for group in abstract_task["grps"]:
            self.logger.info("Analyze source files from group {}".format(group["id"]))
            for command in b_cmds[group['id']]:
                os.environ["CWD"] = os.path.realpath(os.getcwd())
                os.environ["CC_IN_FILE"] = command['in files'][0]
                self._signify_file(command['in files'][0])
                stdout = core.utils.execute(self.logger, ('aspectator', '-print-file-name=include'),
                                            collect_all_stdout=True)
                core.utils.execute(self.logger,
                                   tuple(['cif',
                                          '--in', command['in files'][0],
                                          '--aspect', self.aspect,
                                          '--out', os.path.relpath(
                                           '{0}.c'.format(core.utils.unique_file_name(os.path.splitext(
                                               os.path.basename(command['out file']))[0], '.c.aux')),
                                           os.path.join(self.conf['main working directory'], command['cwd'])),
                                          '--stage', 'instrumentation',
                                          '--back-end', 'src',
                                          '--debug', 'DEBUG'] +
                                         (['--keep'] if self.conf['keep intermediate files'] else []) +
                                         ['--'] +
                                         [opt.replace('"', '\\"') for opt in command["opts"]] +
                                         ['-isystem{0}'.format(stdout[0])]),
                                   cwd=os.path.relpath(
                                       os.path.join(self.conf['main working directory'], command['cwd'])),
                                   filter_func=core.vtg.utils.CIFErrorFilter())

    def _fulfill_collection(self):
        # Patterns to parse
        function_signature_re = re.compile('^(\w+) signature=\'(.+)\'\n$')
        all_args_re = "(?:\sarg\d+='[^']*')*"
        call_re = re.compile("^(\w*)\s(\w*)({})\n".format(all_args_re))
        arg_re = re.compile("\sarg(\d+)='([^']*)'")
        macro_re = re.compile("^(\w*)({})\n".format(all_args_re))
        typedef_declaration = re.compile("^declaration: typedef ([^\n]+);")
        file_re = re.compile("^path:\s'([^\s]*)'\n$")
        func_definition_files = [
            {"file": "execution.txt", "static": False, "definition": True},
            {"file": "static-execution.txt", "static": True, "definition": True},
            {"file": "declare_func.txt", "static": False, "definition": False},
            {"file": "static-declare_func.txt", "static": True, "definition": True}
        ]

        def import_content(f):
            self.logger.info("Import file {} generated by CIF replacing pathes".format(f))
            current_path = None
            if os.path.isfile(f):
                with open(f, encoding="utf8") as output_fh:
                    for ln in output_fh:
                        m = file_re.match(ln)
                        if m:
                            current_path = m.group(1)
                        else:
                            if not current_path:
                                raise ValueError('Cannot determine to which file the line {!r} is relevant'.format(ln))
                            yield current_path, ln
            else:
                self.logger.debug("File {} does not exist".format(f))

        for execution_source in func_definition_files:
            self.logger.info("Extract function definitions or declarations from {}".format(execution_source["file"]))
            for path, line in import_content(execution_source["file"]):
                if function_signature_re.fullmatch(line):
                    name, signature = function_signature_re.fullmatch(line).groups()

                    if not self.collection["functions"][name][path]:
                        self.collection["functions"][name][path]["signature"] = signature
                    if not self.collection["functions"][name][path]["static"]:
                        self.collection["functions"][name][path]["static"] = execution_source["static"]
                    if not self.collection["functions"][name][path]["definition"]:
                        self.collection["functions"][name][path]["definition"] = execution_source["definition"]
                else:
                    raise ValueError("Cannot parse line '{}' in file {}".format(line, execution_source["file"]))

        expand_file = "expand.txt"
        self.logger.info("Extract macro expansions from {}".format(expand_file))
        for path, line in import_content(expand_file):
            if macro_re.fullmatch(line):
                name, args = macro_re.fullmatch(line).groups()
                args = [arg[1] for arg in arg_re.findall(args)]
                if not self.collection["macro expansions"][name][path]:
                    self.collection["macro expansions"][name][path] = {"args": list()}
                self.collection["macro expansions"][name][path]["args"].append(args)
            else:
                # todo: This is not critical but embarassing
                self.logger.warning("Cannot parse line '{}' in file {}".format(line, expand_file))

        func_calls_file = "call-function.txt"
        self.logger.info("Extract function calls from {}".format(func_calls_file))
        for path, line in import_content(func_calls_file):
            if call_re.fullmatch(line):
                caller_name, name, args = call_re.fullmatch(line).groups()
                if self.collection["functions"][caller_name][path]:
                    # Add information to caller
                    if not self.collection["functions"][caller_name][path]["calls"][name]:
                        self.collection["functions"][caller_name][path]["calls"][name] = list()
                    args = [arg[1] for arg in arg_re.findall(args)]
                    self.collection["functions"][caller_name][path]["calls"][name].append(args)
                    self.used_functions.update({a for a in args if a})

                    # Add information to called
                    if "called at" not in self.collection["functions"][name][path]:
                        self.collection["functions"][name][path]["called at"] = [caller_name]
                    elif caller_name not in self.collection["functions"][name][path]["called at"]:
                        self.collection["functions"][name][path]["called at"].append(caller_name)
                else:
                    raise ValueError("Expect function definition {} in file {} but it has not been extracted".
                                     format(caller_name, path))
            else:
                raise ValueError("Cannot parse line '{}' in file {}".format(line, func_calls_file))

        for path, line in import_content("typedefs.txt"):
            if typedef_declaration.match(line):
                declaration = typedef_declaration.match(line).group(1)
                if not self.collection['typedefs'][path]:
                    self.collection['typedefs'][path] = list()
                self.collection['typedefs'][path].append(declaration)
            else:
                raise ValueError("Cannot parse line '{}' in file {}".format(line, path))

        global_file = "global.txt"
        self.logger.debug("Extract global variables from {}".format(global_file))
        if os.path.isfile(global_file):
            self.collection["global variable initializations"], mentioned_values = parse_initializations(global_file)
            self.used_functions.update(mentioned_values.intersection(set(self.collection["functions"].keys())))

        if not self.conf['keep intermediate files']:
            self.logger.info("Remove files with raw extracted data")
            for file in glob.glob("*.txt"):
                self.logger.debug("Remove file {}".format(file))
                os.remove(file)

    def _save_collection(self, km_file):
        with open(km_file, "w", encoding="utf8") as km_fh:
            json.dump(self.collection, km_fh, ensure_ascii=False, sort_keys=True, indent=4)

    def _process_collection(self):
        self.logger.info("Process collection according to provided options")

        # Get functions with definitions
        self.logger.info("Determine functions which are relevant")
        # Then go through call graph
        updated = True
        while updated:
            updated = False

            for func in list(self.used_functions):
                for path in self.collection["functions"][func]:
                    if "calls" in self.collection["functions"][func][path]:
                        for i in self.collection["functions"][func][path]["calls"]:
                            if i not in self.used_functions:
                                self.used_functions.add(i)
                                updated = True
        self.logger.info("There are {} relevant functions found? delete the rest".format(len(self.used_functions)))

        for name in [n for n in self.collection['functions'] if n not in self.used_functions]:
            del self.collection['functions'][name]

        # Remove useless macro expansions
        self.logger.info("Remove useless macro-expansions from the collection")
        self._shrink_macro_expansions()

    def _shrink_macro_expansions(self):
        if "filter macros" in self.conf and isinstance(self.conf["filter macros"], list):
            white_list = self.conf["filter macros"]
            expansions = list(self.collection["macro expansions"].keys())
            for exp in (e for e in expansions if e not in white_list):
                del self.collection["macro expansions"][exp]

    main = analyze_sources
