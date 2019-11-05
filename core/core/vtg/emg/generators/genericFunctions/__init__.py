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

import re

from core.vtg.emg.common import get_or_die, get_conf_property
from core.vtg.emg.common.c import Function, Variable
from core.vtg.emg.common.c.types import Pointer
from core.vtg.emg.common.process import Process
from core.vtg.emg.generators.abstract import AbstractGenerator


class genericFunctions(AbstractGenerator):

    def generate_processes(self, emg, source, processes, conf, specifications):
        """
        This generator generates processes for verifying Linux kernel modules. It generates the main process which calls
        module and kernel initialization functions and then modules exit functions.

        :param emg: EMG Plugin object.
        :param source: Source collection object.
        :param processes: ProcessCollection object.
        :param conf: Configuration dictionary of this generator.
        :param specifications: Dictionary with required specifications of required kinds
        :return: None
        """
        functions_collection = dict()

        # Import Specifications
        emg.logger.info("Generate an entry process on base of given funcitons list")
        if processes.entry:
            raise ValueError('Do not expect any main process already attached to the model, reorder EMG generators in '
                             'configuration')

        # Read configuration in abstract task
        emg.logger.info("Determine functions to call in the environment model")

        # Allow setting file regex to filter functions with several definitions
        expressions = []
        for expr in get_conf_property(conf, "functions to call"):
            if isinstance(expr, str):
                obj = re.compile(expr)
                expressions.append((None, obj))
            elif isinstance(expr, list) and len(expr) == 2:
                file_obj = re.compile(expr[0])
                func_obj = re.compile(expr[1])
                expressions.append((file_obj, func_obj))
            else:
                raise ValueError('Unknown element given instead of a file and function regular expressions pair: {!r}'.
                                 format(str(expr)))

        strict = get_conf_property(conf, "prefer not called")
        statics = get_conf_property(conf, "call static")
        for func in source.source_functions:
            objs = source.get_source_functions(func)
            suits = []
            for obj in objs:
                if (not strict or strict and len(obj.called_at) == 0) and (obj.static and statics or not obj.static) and \
                        obj.definition_file:
                    for file_expr, func_expr in expressions:
                        if func_expr.fullmatch(func) and (not file_expr or file_expr.fullmatch(obj.definition_file)):
                            emg.logger.debug('Add function {!r} from {!r}'.format(func, obj.definition_file))
                            suits.append(obj)
                            break

            if suits:
                functions_collection[func] = suits

        if len(functions_collection) == 0:
            raise ValueError("There is no suitable functions to call in the environment model")

        # Read configuration in private configuration about headers
        # todo: in current implementation it is useless but may help in future
        # headers_map = get_conf_property(conf, "additional headers")
        # if headers_map:
        #     for func in (f for f in set(headers_map.keys).intersection(set(functions_list))):
        #         functions_collection[func].headers.extend(headers_map[func])

        # Genrate scenario
        emg.logger.info('Generate main scenario')
        new = self.__generate_calls(emg.logger, emg, conf, functions_collection)
        processes.entry = new

    def __generate_calls(self, logger, emg, conf, functions_collection):
        def indented_line(t, s):
            return (t * "\t") + s

        loop = get_or_die(conf, "infinite call")

        # Generate process
        ep = Process("main")
        ep._category = 'generic'
        ep.comment = "Call exported functions."
        ep.pretty_id = 'generic'
        ep.process = ''

        # Generate actions for all sequence
        expressions = []
        identifier = 0
        for func in functions_collection:
            for obj in functions_collection[func]:
                logger.info("Call function {!r} from {!r}".format(func, obj.definition_file))
                expr = self.__generate_call(emg, conf, ep, func, obj, identifier)
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
            # Add a break after a function call
            code.append(indented_line(tab, "case {}: ".format(cnt) + '{'))
            code.append(indented_line(tab + 1, "{}".format(expr)))
            code.append(indented_line(tab + 1, "break;"))
            code.append(indented_line(tab, "}"))
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

    def __generate_call(self, emg, conf, ep, func, obj, identifier):
        # Add declaration of caller
        caller_func = Function("ldv_emg_{}_caller_{}".format(func, identifier), "void a(void)")
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
                    elements = get_conf_property(conf, "initialize strings as null terminated")
                    if elements and arg.identifier == 'char **':
                        if isinstance(elements, int) or elements.isnumeric():
                            elements = int(elements)
                        else:
                            elements = 'ldv_undef_int()'
                        argvar_len = Variable(argvar.name + '_len', 'int')
                        # Define explicitly number of arguments, since undef value is too difficult sometimes
                        initializations.append("int {} = {};".format(argvar_len.name, elements))
                        initializations.append("{} = (char **) ldv_xmalloc({} * sizeof(char *));".format(argvar.name,
                                                                                                         argvar_len.name))
                        # Initialize all elements but the last one
                        initializations.append("for (int i = 0; i < {} - 1; i++)".format(argvar_len.name))
                        # Some undefined data
                        initializations.append("\t{}[i] = (char *) external_allocated_data();".format(argvar.name))
                        # The last element is a string
                        initializations.append("{}[{}] = (char * ) 0;".format(argvar.name, elements - 1))
                        free_args.append(argvar.name)
                    elif get_or_die(emg.conf["translation options"], "allocate external"):
                        value = "external_allocated_data();"
                        initializations.append("{} = {}".format(argvar.name, value))
                    else:
                        if get_or_die(emg.conf["translation options"], "allocate with sizeof"):
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
