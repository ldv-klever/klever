#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
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

from klever.core.vtg.emg.common.c import Function
from klever.core.vtg.emg.common.process import Process, Block
from klever.core.vtg.emg.common import model_comment, get_or_die
from klever.core.vtg.emg.common.c.types import import_declaration
from klever.core.vtg.emg.common.process.parser import parse_process
from klever.core.vtg.emg.generators.abstract import AbstractGenerator
from klever.core.vtg.emg.generators.linuxInsmod.tarjan import calculate_load_order


specifications_endings = []


DEFAULT_INIT_FUNCS = (
    "early_initcall",
    "pure_initcall",
    "core_initcall",
    "core_initcall_sync",
    "postcore_initcall",
    "postcore_initcall_sync",
    "arch_initcall",
    "arch_initcall_sync",
    "subsys_initcall",
    "subsys_initcall_sync",
    "fs_initcall",
    "fs_initcall_sync",
    "rootfs_initcall",
    "device_initcall",
    "device_initcall_sync",
    "late_initcall",
    "late_initcall_sync",
    "console_initcall",
    "security_initcall"
)


class ScenarioModelgenerator(AbstractGenerator):

    def make_scenarios(self, abstract_task_desc, collection, source, specifications):
        """
        This generator generates processes for verifying Linux kernel modules. It generates the main process which calls
        module and kernel initialization functions and then modules exit functions.

        :param abstract_task_desc: Abstract task dictionary.
        :param collection: ProcessCollection.
        :param source: Source collection.
        :param specifications: dictionary with merged specifications.
        :return: None
        """

        # Import Specifications
        self.logger.info("Generate an entry process on base of source analysis of provided Linux kernel files")
        if collection.entry:
            raise ValueError('Do not expect any main process already attached to the model, reorder EMG generators in '
                             'configuration to generate insmod process')

        self.conf.setdefault('kernel initialization', DEFAULT_INIT_FUNCS)
        self.conf.setdefault('init', "module_init")
        self.conf.setdefault('exit', "module_exit")
        self.conf.setdefault('kernel', False)
        self.logger.info("Determine initialization and exit functions")
        inits, exits, kernel_initializations = self.__import_inits_exits(abstract_task_desc, source)

        self.logger.info('Generate initializing scenario')
        insmod = self.__generate_insmod_process(source, inits, exits, kernel_initializations)
        collection.entry = insmod

    def __import_inits_exits(self, avt, source):
        _inits = collections.OrderedDict()
        _exits = collections.OrderedDict()
        deps = {}
        for module, dep in avt['deps'].items():
            deps[module] = list(dep)
        order = calculate_load_order(self.logger, deps)
        order_c_files = []
        for module in order:
            for module2 in avt['grps']:
                if module2['id'] != module:
                    continue
                order_c_files.extend([file['in file'] for file in module2['Extra CCs']])

        init = source.get_macro(get_or_die(self.conf, 'init'))
        if init:
            parameters = {}
            for path in init.parameters:
                if len(init.parameters[path]) > 1:
                    raise ValueError("Cannot set two initialization functions for a file {!r}".format(path))
                if len(init.parameters[path]) == 1:
                    parameters[path] = init.parameters[path][0][0]

            for module in (m for m in order_c_files if m in parameters):
                _inits[module] = parameters[module]
        elif not self.conf.get('kernel'):
            raise ValueError('There is no module initialization function provided')

        exitt = source.get_macro(get_or_die(self.conf, 'exit'))
        if exitt:
            parameters = {}
            for path in exitt.parameters:
                if len(exitt.parameters[path]) > 1:
                    raise KeyError("Cannot set two exit functions for a file {!r}".format(path))
                if len(exitt.parameters[path]) == 1:
                    parameters[path] = exitt.parameters[path][0][0]

            for module in (m for m in reversed(order_c_files) if m in parameters):
                _exits[module] = parameters[module]
        if not exitt and not self.conf.get('kernel'):
            self.logger.warning('There is no module exit function provided')

        kernel_initializations = []
        if self.conf.get('kernel'):
            if get_or_die(self.conf, "add functions as initialization"):
                extra = get_or_die(self.conf, "add functions as initialization")
            else:
                extra = {}

            for name in get_or_die(self.conf, 'kernel initialization'):
                mc = source.get_macro(name)

                same_list = []
                if mc:
                    for module in (m for m in order_c_files if m in mc.parameters):
                        for call in mc.parameters[module]:
                            same_list.append((module, call[0]))
                if name in extra:
                    for func in (source.get_source_function(f) for f in extra[name] if source.get_source_function(f)):
                        if func.definition_file:
                            file = func.definition_file
                        elif len(func.declaration_files) > 0:
                            file = list(func.declaration_files)[0]
                        else:
                            file = None

                        if file:
                            same_list.append((file, func.name))
                        else:
                            self.logger.warning("Cannot find file to place alias for {!r}".format(func.name))
                if len(same_list) > 0:
                    kernel_initializations.append((name, same_list))

        inits = [(module, _inits[module]) for module in _inits]
        exits = [(module, _exits[module]) for module in _exits]
        return inits, exits, kernel_initializations

    def __generate_insmod_process(self, source, inits, exits, kernel_initializations):
        self.logger.info("Generate artificial process description to call Init and Exit module functions 'insmod'")
        ep = Process("insmod")
        ep.comment = "Initialize or exit module."
        ep.self_parallelism = False

        # Add subprocesses finally
        process = ''
        for i, pair in enumerate(inits):
            process += "<{0}>.(<init_failed_{1}>".format(pair[1], i)
            for j, pair2 in enumerate(exits[::-1]):
                if pair2[0] == pair[0]:
                    break
            j = 1
            for _, exit_name in exits[:j - 1:-1]:
                process += ".<{}>".format(exit_name)
            process += "|<init_success_{}>.".format(i)

        for _, exit_name in exits:
            process += "<{}>.".format(exit_name)
        # Remove the last dot
        process = process[:-1]

        process += ")" * len(inits)
        if kernel_initializations and inits:
            process += "<kernel_initialization>." \
                       "(<kerninit_success> | <kerninit_failed>.(" + process + "))"
        elif kernel_initializations and not inits:
            process += "<kernel_initialization>.(<kernel_initialization_success> | <kernel_initialization_fail>)"
        elif not inits and not kernel_initializations:
            raise NotImplementedError("There is no both kernel initialization functions and module initialization "
                                      "functions")

        # This populates all actions
        parse_process(ep, process)
        ep.actions.populate_with_empty_descriptions()

        if len(kernel_initializations) > 0:
            body = [
                "int ret;"
            ]
            label_name = 'emg_kernel_initialization_exit'

            # Generate kernel initializations
            for name, calls in kernel_initializations:
                for filename, func_name in calls:
                    func = source.get_source_function(func_name, filename)
                    if func:
                        retval = not func.declaration.return_value == 'void'
                    else:
                        raise RuntimeError("Cannot resolve function {!r} in file {!r}".format(name, filename))
                    new_name = self.__generate_alias(ep, func_name, filename, retval)
                    statements = []
                    if retval:
                        statements.extend([
                            "ret = {}();".format(new_name),
                            "ret = ldv_post_init(ret);",
                            "if (ret)",
                            "\tgoto {};".format(label_name)
                        ])
                    else:
                        statements.append("{}();".format(new_name))

                    body.extend(statements)
            body.extend([
                "{}:".format(label_name),
                "return ret;"
            ])
            func = Function('emg_kernel_init', 'int emg_kernel_init(void)')
            func.body = body
            addon = func.define()
            ep.add_definition('environment model', 'emg_kernel_init', addon)

            ki_subprocess = ep.actions['kernel initialization']
            ki_subprocess.statements = ["%ret% = emg_kernel_init();"]
            ki_subprocess.comment = 'Kernel initialization stage.'
            ki_subprocess.trace_relevant = True

            ki_success = ep.actions['ki_success']
            ki_success.condition = ["%ret% == 0"]
            ki_success.comment = "Kernel initialization is successful."

            ki_failed = ep.actions['kerninit_failed']
            ki_failed.condition = ["%ret% != 0"]
            ki_failed.comment = "Kernel initialization is unsuccessful."
        if len(inits) > 0:
            # Generate init subprocess
            for filename, init_name in inits:
                self.logger.debug("Found init function {!r}".format(init_name))
                new_name = self.__generate_alias(ep, init_name, filename, True)
                init_subprocess = ep.actions[init_name]
                init_subprocess.comment = 'Initialize the module after insmod with {!r} function.'.format(init_name)
                init_subprocess.statements = [
                    "%ret% = {}();".format(new_name),
                    "%ret% = ldv_post_init(%ret%);"
                ]
                init_subprocess.trace_relevant = True

        # Add ret label
        ep.add_label('ret', import_declaration("int label"))

        # Generate exit subprocess
        if len(exits) == 0:
            self.logger.debug("There is no exit function found")
        else:
            for filename, exit_name in exits:
                self.logger.debug("Found exit function {!r}".format(exit_name))
                new_name = self.__generate_alias(ep, exit_name, filename, False)
                exit_subprocess = ep.actions[exit_name]
                exit_subprocess.comment = 'Exit the module before its unloading with {!r} function.'.format(exit_name)
                exit_subprocess.statements = [
                    "{}();".format(new_name)
                ]
                exit_subprocess.trace_relevant = True

        # Generate successful conditions
        for action in (a for a in ep.actions.filter(include={Block}) if str(a).startswith('init_success')):
            action.condition = ["%ret% == 0"]
            action.comment = "Module has been initialized."

        # Generate else branch
        for action in (a for a in ep.actions.filter(include={Block}) if str(a).startswith('init_failed')):
            action.condition = ["%ret% != 0"]
            action.comment = "Failed to initialize the module."

        return ep

    @staticmethod
    def __generate_alias(process, name, file, int_retval=False):
        new_name = "emg_{}".format(name)
        code = [
            "{}();".format("return {}".format(name) if int_retval else name)
        ]
        # Add definition
        func = Function(new_name,
                        "{}(void)".format("int {}".format(new_name) if int_retval else "void {}".format(new_name)))
        func.body = code
        process.add_definition(file, name, func.define())
        process.add_declaration('environment model', name,
                                'extern {} {}(void);\n'.format("int" if int_retval else "void", new_name))

        return new_name
