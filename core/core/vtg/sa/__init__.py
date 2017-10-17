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
        self.modules_functions = []
        self.kernel_functions = []

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

    def _generate_aspect_file(self):
        # Prepare aspect file
        if "template aspect" not in self.conf:
            raise TypeError("Source analyzer plugin need a configuration property 'template aspect' to be set")
        template_aspect_file = core.utils.find_file_or_dir(self.logger, self.conf["main working directory"],
                                                           self.conf["template aspect"])
        self.logger.info("Found file with aspect file template {}".format(template_aspect_file))

        # TODO: extract to common library (the same code as in core/vtg/tr/__init__.py).
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
                "arg_vals": {i: ",".join(["$arg_value{}".format(j + 1) for j in range(i + 1)])
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
                stdout = core.utils.execute(self.logger, ('aspectator', '-print-file-name=include'),
                                            collect_all_stdout=True)
                self.logger.info("Analyze source file {}".format(command['in files'][0]))
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
                                       os.path.join(self.conf['main working directory'], command['cwd'])))

    def _import_content(self, file):
        self.logger.info("Import file {} generated by CIF replacing pathes".format(file))
        content = []
        if os.path.isfile(file):
            with open(file, encoding="utf8") as output_fh:
                content = output_fh.readlines()
            self.logger.debug("File {} has been successfully imported".format(file))
        else:
            self.logger.debug("File {} does not exist".format(file))
        return content

    def _fulfill_collection(self):
        # Patterns to parse
        function_signature_re = re.compile('([^\s]+) (\w+) signature=\'(.+)\'\n$')
        all_args_re = "(?:\sarg\d+='[^']*')*"
        call_re = re.compile("^([^\s]*)\s([^\s]*)\s(\w*)\s(\w*)({})\n".format(all_args_re))
        arg_re = re.compile("\sarg(\d+)='([^']*)'")
        short_pair_re = re.compile("^([^\s]*)\s(\w*)\n")
        typedef_declaration = re.compile("^declaration: typedef ([^\n]+); path: ([^\n]+)")

        func_definition_files = [
            {"file": "execution.txt", "static": False},
            {"file": "static-execution.txt", "static": True},
            {"file": "declare_func.txt", "static": False},
            {"file": "static-declare_func.txt", "static": True}
        ]
        for execution_source in func_definition_files:
            self.logger.info("Extract function definitions or declarations from {}".format(execution_source["file"]))
            content = self._import_content(execution_source["file"])
            for line in content:
                if function_signature_re.fullmatch(line):
                    path, name, signature = function_signature_re.fullmatch(line).groups()

                    if not self.collection["functions"][name]["files"][path]:
                        self.collection["functions"][name]["files"][path]["signature"] = signature
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
                path, cc_path, caller_name, name, args = call_re.fullmatch(line).groups()
                if self.collection["functions"][caller_name]["files"][path]:
                    # Add information to caller
                    if not self.collection["functions"][caller_name]["files"][path]["calls"][name]:
                        self.collection["functions"][caller_name]["files"][path]["calls"][name] = list()
                    self.collection["functions"][caller_name]["files"][path]["calls"][name].\
                        append([arg[1] for arg in arg_re.findall(args)])

                    # Add information to called
                    if "called at" not in self.collection["functions"][name]:
                        self.collection["functions"][name]["called at"] = list()
                    if cc_path not in self.collection["functions"][name]["called at"]:
                        self.collection["functions"][name]["called at"].append(cc_path)
                else:
                    raise ValueError("Expect function definition {} in file {} but it has not been extracted".
                                     format(caller_name, path))
            else:
                raise ValueError("Cannot parse line '{}' in file {}".format(line, func_calls_file))

        typedef_file = "typedefs.txt"
        content = self._import_content(typedef_file)
        self.collection['typedefs'] = dict()
        for line in content:
            if typedef_declaration.match(line):
                declaration = typedef_declaration.match(line).group(1)
                scope_file = typedef_declaration.match(line).group(2)
                if scope_file not in self.collection['typedefs']:
                    self.collection['typedefs'][scope_file] = list()
                self.collection['typedefs'][scope_file].append(declaration)
            else:
                raise ValueError("Cannot parse line '{}' in file {}".format(line, typedef_file))

        global_file = "global.txt"
        self.logger.debug("Extract global variables from {}".format(global_file))
        # todo: add some logging here
        if os.path.isfile(global_file):
            self.collection["global variable initializations"] = parse_initializations(global_file)

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

        # todo: support non-standart kinds of initializations (issues #6571, #6558)
        init_file = "init.txt"
        self.logger.info("Extract initialization functions from {}".format(init_file))
        content = self._import_content(init_file)
        for line in content:
            if short_pair_re.fullmatch(line):
                path, func = short_pair_re.fullmatch(line).groups()
                if not isinstance(self.collection["init"][path], str):
                    self.collection["init"][path] = func
                    self.logger.debug("Extracted Init function {} in {}".format(func, path))
                elif self.collection["init"][path] != func:
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
                if not self.collection["exit"][path]:
                    self.collection["exit"][path] = func
                    self.logger.debug("Extracted Exit function {} in {}".format(func, path))
                # todo: code below does not work properly
                #else:
                #    raise ValueError("Module cannot contain two exit functions but file {} contains".
                #                     format(path))
            else:
                raise ValueError("Cannot parse line '{}' in file {}".format(line, exit_file))

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
        # todo: what if several headers have the same function ?
        for function in functions:
            files = list(self.collection["kernel functions"][function]["files"].keys())
            if len(files) > 0:
                first_file = files[0]
                for key in self.collection["kernel functions"][function]["files"][first_file]:
                    self.collection["kernel functions"][function][key] = \
                        self.collection["kernel functions"][function]["files"][first_file][key]

                self.collection["kernel functions"][function]["header"] = first_file
                del self.collection["kernel functions"][function]["files"]
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

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
