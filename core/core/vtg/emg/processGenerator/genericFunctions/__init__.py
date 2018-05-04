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
import json

from core.utils import find_file_or_dir
from core.vtg.emg.common import get_necessary_conf_property
from core.vtg.emg.common.c import Function, Variable
from core.vtg.emg.common.c.types import Pointer
from core.vtg.emg.common.process import Process


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
    functions_collection = dict()

    # Import Specifications
    emg.logger.info("Generate an entry process on base of given funcitons list")
    if processes.entry:
        raise ValueError('Do not expect any main process already attached to the model, reorder EMG generators in '
                         'configuration')

    # Read configuration in abstract task
    emg.logger.info("Determine functions")
    functions_file = emg.abstract_task_desc["functions"]
    functions_file = find_file_or_dir(emg.logger, emg.conf["main working directory"], functions_file)
    with open(functions_file, encoding="utf8") as fh:
        functions_list = json.loads(fh.read())
    if not isinstance(functions_list, list):
        raise ValueError("Expect strictly list of functions in file {!r}".format(functions_file))

    # Check that all function are valid
    for func in functions_list:
        obj = source.get_source_function(func)
        if not obj:
            raise ValueError("Source analysis cannot find function {!r}".format(func))
        else:
            functions_collection[func] = obj

    # Read configuration in private configuration about headers
    # todo: in current implementation it is useless but may help in future
    # headers_map = get_conf_property(conf, "additional headers")
    # if headers_map:
    #     for func in (f for f in set(headers_map.keys).intersection(set(functions_list))):
    #         functions_collection[func].headers.extend(headers_map[func])

    # Genrate scenario
    emg.logger.info('Generate main scenario')
    new = __generate_calls(emg.logger, emg, conf, functions_collection)
    processes.entry = new


def __generate_calls(logger, emg, conf, functions_collection):

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
        expr = __generate_call(emg, ep, func, functions_collection[func])
        expressions.append(expr)

    # Generate process description
    code = []
    tab = 0
    if loop:
        code.append(indented_line(tab, "while (1) {"))
        tab += 1

    code.append(indented_line(tab, "switch (ldv_undef_int()) {"))
    tab += 1
    cnt = 0
    for expr in expressions:
        code.append(indented_line(tab, "case {}: {}".format(cnt, expr)))
        cnt += 1
    if loop:
        code.append(indented_line(tab, "default: break;"))
    else:
        code.append(indented_line(tab, "default: ldv_assume(0);"))

    tab -= 1
    code.append(indented_line(tab, "}"))
    if loop:
        code.append("}")
        tab -= 1

    ep.add_condition('function_calls', [], code, 'Call all functions independently.')
    ep.process = "<function_calls>"

    return ep


def __generate_call(emg, ep, func, obj):
    # Add declaration of caller
    caller_func = Function("ldv_emg_{}_caller".format(func), "void a(void)")
    ep.add_declaration("environment model", caller_func.name, caller_func.declare(True)[0])
    expression = ""
    body = []
    initializations = []

    # Check retval and cast to void call
    if obj.declaration.return_value and obj.declaration.return_value.identifier != 'void':
        expression += "(void) "

    # Get arguments and allocate memory for them
    args = []
    free_args = []
    for index, arg in enumerate(obj.declaration.parameters):
        if not isinstance(arg, str):
            argvar = Variable("ldv_arg_{}".format(index), arg)
            body.append(argvar.declare() + ";")
            args.append(argvar.name)
            if isinstance(arg, Pointer):
                # todo: this is an ugly workaround to get translation options directly
                if get_necessary_conf_property(emg.conf["translation options"], "allocate external"):
                    value = "external_allocated_data();"
                else:
                    if get_necessary_conf_property(emg.conf["translation options"], "allocate with sizeof"):
                        apt = arg.points.to_string('', typedef='complex_and_params')
                        value = "ldv_xmalloc(sizeof({}));".\
                            format(apt if apt != 'void' else apt + '*')
                    else:
                        value = "ldv_xmalloc_unknown_size(0);"
                    free_args.append(argvar.name)
                initializations.append("{} = {}".format(argvar.name, value))

    # Generate call
    expression += "{}({});".format(func, ", ".join(args))

    # Generate function body
    body += initializations + [expression]

    # Free memory
    for arg in free_args:
        body.append("ldv_free({});".format(arg))

    caller_func.body = body

    # Add definition of caller
    ep.add_definition(obj.definition_file, caller_func.name, caller_func.define() + ["\n"])

    # Return call expression
    return "{}();".format(caller_func.name)
