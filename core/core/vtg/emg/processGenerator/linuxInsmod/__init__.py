#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
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

from core.vtg.emg.common import model_comment
from core.vtg.emg.common.c.types import import_declaration
from core.vtg.emg.common.process import Process, Receive, Condition
from core.vtg.emg.processGenerator.linuxInsmod.tarjan import calculate_load_order


def generate_processes(logger, conf, avt, sa, analysis_data, processes):
    modelp, envp, entry = processes

    logger.info("Determine initialization and exit functions")
    inits, exits = __import_inits_exits(avt, sa)

    logger.info('Generate insmod scenario')
    insmod = __generate_insmod_process(logger, inits, exits)
    envp.append(insmod)
    return [modelp, envp, entry]


def __import_inits_exits(collection, analysis, avt):
    # todo: Do this as soon as you add data converted from the macros section in general sa object. Then you can just
    # todo: filer these macros and use them as inits and exits. Also add new initialization functions. Use order from
    # todo: configuration for them

    def add_init(self, module, function_name):
        """
        Add Linux module initialization function.

        :param module: Module kernel object name string.
        :param function_name: Initialization function name string.
        :return: None
        """
        if module in self._inits and function_name != self._inits[module]:
            raise KeyError("Cannot set two initialization functions for a module {!r}".format(module))
        elif module not in self._inits:
            self._inits[module] = function_name

    def add_exit(self, module, function_name):
        """
        Add Linux module exit function.

        :param module: Linux module kernel object name string.
        :param function_name: Function name string.
        :return: None
        """
        if module in self._exits and function_name != self._exits[module]:
            raise KeyError("Cannot set two exit functions for a module {!r}".format(module))
        elif module not in self._exits:
            self._exits[module] = function_name

    _inits = collections.OrderedDict()
    _exits = collections.OrderedDict()


    collection.logger.debug("Move module initilizations functions to the modules interface specification")
    deps = {}
    for module, dep in avt['deps'].items():
        deps[module] = list(sorted(dep))
    order = calculate_load_order(collection.logger, deps)
    order_c_files = []
    for module in order:
        for module2 in avt['grps']:
            if module2['id'] != module:
                continue
            order_c_files.extend([file['in file'] for file in module2['cc extra full desc files']])
    #todo: Change with the new source analysis
    if "init" in analysis:
        for module in (m for m in order_c_files if m in analysis["init"]):
            collection.add_init(module, analysis['init'][module])
    if len(collection.inits) == 0:
        raise ValueError('There is no module initialization function provided')

    collection.logger.debug("Move module exit functions to the modules interface specification")
    if "exit" in analysis:
        for module in (m for m in reversed(order_c_files) if m in analysis['exit']):
            collection.add_exit(module, analysis['exit'][module])
    if len(collection.exits) == 0:
        collection.logger.warning('There is no module exit function provided')

    inits = [(module, _inits[module]) for module in _inits]
    exits = [(module, _exits[module]) for module in _exits]
    return inits, exits


def __generate_insmod_process(logger, inits, exits):
    logger.info("Generate artificial process description to call Init and Exit module functions 'insmod'")
    ep = Process("insmod")
    ep.comment = "Initialize or exit module."
    ep.self_parallelism = False
    ep.identifier = 0

    # Add register
    insmod_register = Receive('insmod_register')
    insmod_register.replicative = True
    insmod_register.comment = 'Trigger module initialization.'
    insmod_register.parameters = []
    ep.actions[insmod_register.name] = insmod_register
    ep.process = '(!{}).'.format(insmod_register.name)

    if len(inits) == 0:
        raise RuntimeError('Module does not have Init function')

    # Generate init subprocess
    for filename, init_name in inits:
        new_name = __generate_alias(ep, init_name, filename, True)
        init_subprocess = Condition(init_name)
        init_subprocess.comment = 'Initialize the module after insmod with {!r} function.'.format(init_name)
        init_subprocess.statements = [
            model_comment('callback', init_name, {'call': "{}();".format(init_name)}),
            "%ret% = {}();".format(new_name),
            "%ret% = ldv_post_init(%ret%);"
        ]
        logger.debug("Found init function {}".format(init_name))
        ep.actions[init_subprocess.name] = init_subprocess

    # Add ret label
    ep.add_label('ret', import_declaration("int label"))

    # Generate exit subprocess
    if len(exits) == 0:
        logger.debug("There is no exit function found")
    else:
        for filename, exit_name in exits:
            new_name = __generate_alias(ep, exit_name, filename, False)
            exit_subprocess = Condition(exit_name)
            exit_subprocess.comment = 'Exit the module before its unloading with {!r} function.'.format(exit_name)
            exit_subprocess.statements = [
                model_comment('callback', exit_name, {'call': "{}();".format(exit_name)}),
                "{}();".format(new_name)
            ]
            logger.debug("Found exit function {}".format(exit_name))
            ep.actions[exit_subprocess.name] = exit_subprocess

    # Generate conditions
    success = ep.add_condition('init_success', ["%ret% == 0"], [], "Module has been initialized.")
    ep.actions[success.name] = success
    # Generate else branch
    failed = ep.add_condition('init_failed', ["%ret% != 0"], [], "Failed to initialize the module.")
    ep.actions[failed.name] = failed

    # Add deregister
    insmod_deregister = Receive('insmod_deregister')
    insmod_deregister.comment = 'Trigger module exit.'
    insmod_deregister.parameters = []
    ep.actions[insmod_deregister.name] = insmod_deregister

    # Add subprocesses finally
    for i, pair in enumerate(inits):
        ep.process += "<{0}>.(<init_failed>.".format(pair[1])
        for j, pair2 in enumerate(exits[::-1]):
            if pair2[0] == pair[0]:
                break
        j = 1
        for _, exit_name in exits[:j - 1:-1]:
            ep.process += "<{}>.".format(exit_name)
        ep.process += "({})|<init_success>.".format(insmod_deregister.name)

    for _, exit_name in exits:
        ep.process += "<{}>.".format(exit_name)
    ep.process += "({})".format(insmod_deregister.name)
    ep.process += ")" * len(inits)
    logger.debug("Artificial process for invocation of Init and Exit module functions is generated")
    return ep


def __generate_alias(process, name, file, int_retval=False):
    new_name = "ldv_emg_{}".format(name)
    code = [
        "{}(void)\n".format("int {}".format(new_name) if int_retval else "void {}".format(new_name)),
        "{\n",
        "\t{}();\n".format("return {}".format(name) if int_retval else name),
        "}\n"
    ]
    # Add definition
    process.add_definition(file, name, code)
    process.add_declaration('environment model', name,
                            'extern {} {}(void);\n'.format("int" if int_retval else "void", new_name))

    return new_name
