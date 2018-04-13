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

from core.vtg.emg.common import model_comment, get_necessary_conf_property, get_conf_property
from core.vtg.emg.common.c import Function
from core.vtg.emg.common.c.types import import_declaration
from core.vtg.emg.common.process import Process, Condition


def generate_processes(emg, source, processes, conf):
    """
    This generator generates processes for verifying Linux kernel modules. It generates the main process which calls
    module and kernel initialization functions and then modules exit functions.

    :param emg: EMG Plugin object.
    :param source: Source collection object.
    :param processes: ProcessCollection object.
    :param conf: Configuration dictionary of this generator.
    :return: None
    """

    # Import Specifications
    emg.logger.info("Generate an entry process on base of given funcitons list")
    if processes.entry:
        raise ValueError('Do not expect any main process already attached to the model, reorder EMG generators in '
                         'configuration')

    # Read configuration in abstract task
    emg.logger.info("Determine functions")
    functions_list = emg.abstract_task_desc["functions"]
    functions_collection = dict()

    # Check that all function are valid
    for func in functions_list:
        obj = source.get_source_function(func)
        if not obj:
            raise ValueError("Source analysis cannot find function {!r}".format(func))
        else:
            functions_collection[func] = obj

    # Read configuration in private configuration about headers
    headers_map = get_conf_property(conf, "additional headers")
    if headers_map:
        for func in (f for f in set(headers_map.keys).intersection(set(functions_list))):
            functions_collection[func].headers.extend(headers_map[func])

    # Genrate scenario
    emg.logger.info('Generate main scenario')
    new = __generate_calls(emg.logger, conf, functions_collection)
    processes.entry = new


def __generate_calls(logger, conf, functions_collection):

    def indented_line(t, s):
        return (t * "\t") + s

    loop = get_necessary_conf_property(conf, "infinite call")

    # Generate process
    ep = Process("main")
    ep.category = 'generic'
    ep.comment = "Call exported functions."
    ep.pretty_id = 'generic'
    ep.process = ''

    # Generate actions for all sequence
    expressions = []
    for func in functions_collection:
        logger.info("Call function {!r}".format(func))
        expr = __generate_action(ep, func, functions_collection[func])
        expressions.append(expr)

    # Generate process description
    code = []
    tab = 0
    if loop:
        code.append(indented_line(tab, "while (true) {"))

    code.append(indented_line(tab, "switch (ldv_nondet_int()) {"))
    tab += 1
    cnt = 0
    for expr in expressions:
        code.append(indented_line(tab, "case {}: {}".format(cnt, expr)))
        cnt += 1
    tab -= 1
    code.append(indented_line(tab, "}"))
    if loop:
        code.append("}")

    ep.add_condition('function_calls', [], code, 'Call all functions independently.')
    ep.process = "<function_calls>"

    return ep


def __generate_action(ep, func, obj):
    # Add declaration of caller
    caller_func = Function("ldv_emg_{}_caller".format(func), "void a(void)")
    ep.add_declaration("environment model", caller_func.name, caller_func.declare(True))

    # todo: Add definition of caller 





def __generate_insmod_process(logger, conf, source, inits, exits, kernel_initializations):
    logger.info("Generate artificial process description to call Init and Exit module functions 'insmod'")
    ep = Process("insmod")
    ep.category = 'linux'
    ep.comment = "Initialize or exit module."
    ep.self_parallelism = False
    ep.identifier = 0
    ep.process = ''
    ep.pretty_id = 'linux/initialization'

    if len(kernel_initializations) > 0:
        body = [
            "int ret;"
        ]
        label_name = 'ldv_kernel_initialization_exit'

        # Generate kernel initializations
        for name, calls in kernel_initializations:
            for filename, func_name in calls:
                func = source.get_source_function(func_name, filename)
                if func:
                    retval = False if func.declaration.return_value.identifier == 'void' else True
                else:
                    raise RuntimeError("Cannot resolve function {!r} in file {!r}".format(name, filename))
                new_name = __generate_alias(ep, func_name, filename, retval)
                statements = [
                    model_comment('callback', func_name, {'call': "{}();".format(func_name)}),
                ]
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
        func = Function('ldv_kernel_init', 'int ldv_kernel_init(void)')
        func.body = body
        addon = func.define()
        ep.add_definition('environment model', 'ldv_kernel_init', addon)
        ki_subprocess = ep.add_condition('kernel_initialization', [], ["%ret% = ldv_kernel_init();"],
                                         'Kernel initialization stage.')
        ki_success = ep.add_condition('kerninit_success', ["%ret% == 0"], [], "Kernel initialization is successful.")
        ki_failed = ep.add_condition('kerninit_failed', ["%ret% != 0"], [], "Kernel initialization is unsuccessful.")
    if len(inits) > 0:
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

    # Add subprocesses finally
    process = ''
    for i, pair in enumerate(inits):
        process += "<{0}>.(<init_failed>".format(pair[1])
        for j, pair2 in enumerate(exits[::-1]):
            if pair2[0] == pair[0]:
                break
        j = 1
        for _, exit_name in exits[:j - 1:-1]:
            process += ".<{}>".format(exit_name)
        process += "|<init_success>."

    for _, exit_name in exits:
        process += "<{}>.".format(exit_name)

    if get_conf_property(conf, "check final state"):
        final_statments = ["ldv_check_final_state();"]
    else:
        final_statments = []
    final_statments += ["ldv_assume(0);"]
    final = ep.add_condition('final', [], final_statments, "Check rule model state at the exit if required.")
    process += '<{}>'.format(final.name)
    process += ")" * len(inits)

    if len(kernel_initializations) > 0 and len(inits) > 0:
        ep.process += "<{}>.(<{}> | <{}>.({}))".format(ki_subprocess.name, ki_failed.name, ki_success.name, process)
    elif len(kernel_initializations) == 0 and len(inits) > 0:
        ep.process += process
    elif len(kernel_initializations) > 0 and len(inits) == 0:
        ep.process += "<{}>.(<{}> | <{}>)".format(ki_subprocess.name, ki_failed.name, ki_success.name, process) + \
                      '.<{}>'.format(final.name)
    else:
        raise NotImplementedError("There is no both kernel initilization functions and module initialization functions")
    return ep


def __generate_alias(process, name, file, int_retval=False):
    new_name = "ldv_emg_{}".format(name)
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
