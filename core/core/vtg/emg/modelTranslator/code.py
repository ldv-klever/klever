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
import os
import re

from core.utils import unique_file_name
from core.vtg.emg.common import get_conf_property
from core.vtg.emg.common.c import Function
from core.vtg.emg.common.c.types import Pointer, Primitive
from core.vtg.emg.modelTranslator.fsa_translator.common import initialize_automaton_variables


class Aspect(Function):
    """
    Representation of the aspect file pointcuts for source functions which calls should be modified or replaced by
    models. This is an aspect-oriented extension of the C language which is supported by CIF.
    """

    def __init__(self, name, declaration, aspect_type="after"):
        super(Aspect, self).__init__(name, declaration)
        self.aspect_type = aspect_type

    def define(self):
        """
        Print description of the replacement that should be made to the source funtion calls.

        :return: List of strings.
        """
        lines = list()
        lines.append("around: call({}) ".format("$ {}(..)".format(self.name)) +
                     " {\n")
        lines.extend(['\t{}\n'.format(stm) for stm in self.body])
        lines.append("}\n")
        return lines


class CModel:
    """Representation of the environment model in the C language (with extensions)."""

    mem_function_map = {
        "ALLOC": "ldv_xmalloc",
        "UALLOC": "ldv_xmalloc_unknown_size",
        "ZALLOC": "ldv_zalloc"
    }
    free_function_map = {
        "FREE": "ldv_free"
    }
    irq_function_map = {
        "IN_INTERRUPT_CONTEXT": 'ldv_in_interrupt_context',
        "SWITCH_TO_IRQ_CONTEXT": 'ldv_switch_to_interrupt_context',
        "SWITCH_TO_PROCESS_CONTEXT": 'ldv_switch_to_process_context'
    }

    def __init__(self, logger, conf, workdir, files, entry_point_name, entry_file):
        self.entry_file = entry_file
        self.entry_name = entry_point_name
        self.files = files
        self.types = list()
        self._logger = logger
        self._conf = conf
        self._workdir = workdir
        self._variables_declarations = dict()
        self._variables_initializations = dict()
        self._function_definitions = dict()
        self._function_declarations = dict()
        self._headers = dict()
        self._before_aspects = dict()
        self._call_aspects = dict()
        self.__external_allocated = dict()

    def add_headers(self, file, headers):
        """
        Add headers include directives to the particular file.

        :param file: C file.
        :param headers: List of header files.
        :return: None.
        """
        if file not in self._headers:
            self._headers[file] = headers
        else:
            # This is to avoid dependencies broken
            if len(headers) > 1:
                for h in [h for h in headers if h in self._headers[file]]:
                    self._headers[file].remove(h)
                self._headers[file].extend(headers)
            elif headers[0] not in self._headers[file]:
                self._headers[file].append(headers[0])

    def add_function_definition(self, func):
        """
        Add a function definition to the main environment model file.

        :param func: Function object.
        :return: None.
        """
        if not func.definition_file:
            raise RuntimeError('Always expect file to place function definition')
        if func.definition_file not in self._function_definitions:
            self._function_definitions[func.definition_file] = dict()
        if self.entry_file not in self._function_definitions:
            self._function_definitions[self.entry_file] = dict()

        self._function_definitions[func.definition_file][func.name] = func.define()
        self.add_function_declaration(func.definition_file, func, extern=False)

    def add_function_declaration(self, file, func, extern=False):
        """
        Add a function declaration to the file.

        :param file: File name.
        :param func: Function object.
        :param extern: Add it as an extern function.
        :return: None.
        """
        if file not in self._function_declarations:
            self._function_declarations[file] = dict()

        if extern and func.name in self._function_declarations[file]:
            return
        self._function_declarations[file][func.name] = func.declare(extern=extern)

    def add_global_variable(self, variable, file, extern=False, initialize=True):
        """
        Add a global variable declararation or/and initalization to the target file.

        :param variable: Variable object.
        :param file: File name.
        :param extern: Add it as an extern variable.
        :param initialize: Add also the global variable initialization.
        :return: None.
        """
        if not file and variable.file:
            file = variable.file
        elif not file:
            file = self.entry_file

        if file not in self._variables_declarations:
            self._variables_declarations[file] = dict()
        if file not in self._variables_initializations:
            self._variables_initializations[file] = dict()

        if extern and variable.name not in self._variables_declarations[file]:
            self._variables_declarations[file][variable.name] = variable.declare(extern=extern) + ";\n"
        elif not extern:
            self._variables_declarations[file][variable.name] = variable.declare(extern=extern) + ";\n"
            if initialize:
                if variable.value and \
                        ((isinstance(variable.declaration, Pointer) and isinstance(variable.declaration.points, Function))
                         or isinstance(variable.declaration, Primitive)):
                    self._variables_initializations[file][variable.name] = variable.declare_with_init() + ";\n"
                elif not variable.value and isinstance(variable.declaration, Pointer):
                    if file not in self.__external_allocated:
                        self.__external_allocated[file] = []
                    self.__external_allocated[file].append(variable)

    def text_processor(self, automaton, statement):
        """
        Analyze given C code statement and replace all found EMG extensions with the clean C code.

        :param automaton: Automaton object.
        :param statement: Statement string.
        :return: Refined C statements list.
        """
        models = FunctionModels(self._logger, self._conf, self.mem_function_map, self.free_function_map,
                                self.irq_function_map)
        return models.text_processor(automaton, statement)

    def add_function_model(self, func, body):
        """
        Add function model to the environment model.

        :param func: Function object to model.
        :param body: List of C statements which should replace function calls.
        :return: None.
        """
        new_aspect = Aspect(func.name, func.declaration)
        new_aspect.body = body
        files = set()
        files.update(func.files_called_at)
        files.update(func.declaration_files)
        for file in files:
            if file not in self._call_aspects:
                self._call_aspects[file] = list()
            self._call_aspects[file].append(new_aspect)

    def print_source_code(self, additional_lines):
        """
        Generate an environment model as a C code. The code is distributed across aspect addictions for original
        source files and the main environment model C code.

        :param additional_lines: Dictionary with the user-defined C code:
                                 {'file name': {'definitions': [...], 'declarations': []}}
        :return: Dictionary {'file': Path to generated file with the Code}
        """
        aspect_dir = "aspects"
        self._logger.info("Create directory for aspect files {}".format("aspects"))
        os.makedirs(aspect_dir.encode('utf8'), exist_ok=True)

        addictions = dict()
        # Write aspects
        for file in self.files:
            lines = list()

            # Check headers
            if file == self.entry_file:
                if self.entry_file in self._headers:
                    lines.extend(['#include <{}>\n'.format(h) for h in self._headers[self.entry_file]])
                lines.append("\n")

                for tp in self.types:
                    lines.append(tp.to_string('') + " {\n")
                    for field in list(tp.fields.keys()):
                        lines.append("\t{};\n".format(tp.fields[field].to_string(field, typedef='complex_and_params'),
                                                      scope={self.entry_file}))
                    lines.append("};\n")
                    lines.append("\n")
            else:
                # Generate function declarations
                self._logger.info('Add aspects to a file {!r}'.format(file))

                # Add model itself
                lines.append('after: file ("$this")\n')
                lines.append('{\n')

            if file in additional_lines and 'declarations' in additional_lines[file] and \
                    len(additional_lines[file]['declarations']) > 0:
                lines.append("\n")
                lines.append("/* EMG aliases */\n")
                lines.extend(additional_lines[file]['declarations'])

            if file in self._function_declarations:
                lines.append("\n")
                lines.append("/* EMG Function declarations */\n")
                for func in self._function_declarations[file].keys():
                    lines.extend(self._function_declarations[file][func])

            if file in self._variables_declarations:
                lines.append("\n")
                lines.append("/* EMG variable declarations */\n")
                for variable in self._variables_declarations[file].keys():
                    lines.extend(self._variables_declarations[file][variable])

            if file in self._variables_initializations and len(self._variables_initializations[file]) > 0:
                lines.append("\n")
                lines.append("/* EMG variable initialization */\n")
                for variable in self._variables_initializations[file].keys():
                    lines.extend(self._variables_initializations[file][variable])

            if file in additional_lines and 'definitions' in additional_lines[file] and \
                    len(additional_lines[file]['definitions']) > 0:
                lines.append("\n")
                lines.append("/* EMG aliases for functions */\n")
                lines.extend(additional_lines[file]['definitions'])

            if file in self._function_definitions and len(self._function_definitions[file]) > 0:
                lines.append("\n")
                lines.append("/* EMG function definitions */\n")
                for func in self._function_definitions[file].keys():
                    lines.extend(self._function_definitions[file][func])
                    lines.append("\n")

            if file != self.entry_file:
                lines.append("}\n\n")

            if file in self._call_aspects and len(self._call_aspects[file]) > 0:
                lines.append("/* EMG kernel function models */\n")
                for aspect in self._call_aspects[file]:
                    lines.extend(aspect.define())
                    lines.append("\n")

            if file != self.entry_file:
                name = "{}.aspect".format(unique_file_name("aspects/ldv_" + os.path.splitext(os.path.basename(file))[0],
                                                           '.aspect'))
                path = os.path.relpath(name, self._workdir)
                self._logger.info("Add aspect file {!r}".format(path))
                addictions[file] = path
            else:
                name = self.entry_file
            with open(name, "w", encoding="utf8") as fh:
                fh.writelines(lines)

        return addictions

    def compose_entry_point(self, given_body):
        """
        Generate an entry point function for the environment model.

        :param given_body: Body of the main function provided by a translator.
        :return: List of C statements of the generated function body.
        """
        ep = Function(self.entry_name, "int {}(void)".format(self.entry_name))
        ep.definition_file = self.entry_file
        body = ['/* LDV {' + '"thread": 1, "type": "CONTROL_FUNCTION_BEGIN", "comment": "Entry point \'{0}\'", '
                '"function": "{0}"'.format(self.entry_name) + '} */']

        # Init external allocated pointers
        cnt = 0
        functions = []
        if len(self.__external_allocated.keys()) > 0:
            for file in sorted([f for f in self.__external_allocated.keys() if len(self.__external_allocated[f]) > 0]):
                func = Function('ldv_allocate_external_{}'.format(cnt),
                                "void ldv_allocate_external_{}(void)".format(cnt))
                func.declaration_files.add(file)
                func.definition_file = file

                init = ["{} = {}();".format(var.name, 'external_allocated_data') for
                        var in self.__external_allocated[file]]
                func.body = init

                self.add_function_definition(func)
                self.add_function_declaration(self.entry_file, func, extern=True)
                functions.append(func)
                cnt += 1

            gl_init = Function('ldv_initialize_external_data',
                               'void ldv_initialize_external_data(void)')
            gl_init.declaration_files.add(self.entry_file)
            gl_init.definition_file = self.entry_file
            init_body = ['{}();'.format(func.name) for func in functions]
            gl_init.body = init_body
            self.add_function_definition(gl_init)
            body.extend([
                '/* Initialize external data */',
                'ldv_initialize_external_data();'
            ])

        body += given_body
        body.append('return 0;')
        body.append('/* LDV {' + '"comment": "Exit entry point \'{0}\'", "type": "CONTROL_FUNCTION_END",'
                    ' "function": "{0}"'.format(self.entry_name) + '} */')

        ep.body = body
        self.add_function_definition(ep)

        return body


class FunctionModels:
    """Class represent common C extensions for simplifying environmen model C code generation."""

    mem_function_template = "\$({})\(%({})%(?:,\s?(\w+))?\)"
    simple_function_template = "\$({})\("
    access_template = '\w+(?:(?:[.]|->)\w+)*'
    mem_function_re = re.compile(mem_function_template.format('\w+', access_template))
    simple_function_re = re.compile(simple_function_template.format('\w+'))
    access_re = re.compile('(%{}%)'.format(access_template))
    arg_re = re.compile('\$ARG(\d+)')

    def __init__(self, logger, conf, mem_function_map, free_function_map, irq_function_map):
        self._logger = logger
        self._conf = conf
        self.mem_function_map = mem_function_map
        self.free_function_map = free_function_map
        self.irq_function_map = irq_function_map
        self.signature = None
        self.ualloc_flag = None

    def text_processor(self, automaton, statement):
        """
        Analyze given C code statement and replace all found EMG extensions with the clean C code.

        :param automaton: Automaton object.
        :param statement: C statement string.
        :return: New statements list.
        """
        # Replace function names
        stms = []
        matched = False

        # Find state reinitialization
        if re.compile('\$REINITIALIZE_STATE;').search(statement):
            statements = initialize_automaton_variables(self._conf, automaton)
            stms.extend(statements)

        # First replace simple replacements
        for number in self.arg_re.findall(statement):
            new_number = int(number) - 1
            statement = statement.replace('$ARG{}'.format(number), 'arg{}'.format(new_number))

        # Replace function calls
        for fn in self.simple_function_re.findall(statement):
            matched = True

            # Bracket is required to ignore CIF expressions like $res or $arg1
            if fn in self.mem_function_map or fn in self.free_function_map:
                access = self.mem_function_re.search(statement).group(2)
                if fn in self.mem_function_map:
                    replacement = self._replace_mem_call
                else:
                    replacement = self._replace_free_call

                accesses = automaton.process.resolve_access('%{}%'.format(access))
                for access in accesses:
                    signature = access.label.declaration
                    if signature:
                        var = automaton.determine_variable(access.label)
                        if isinstance(var.declaration, Pointer):
                            self.signature = var.declaration
                            self.ualloc_flag = True
                            new = self.mem_function_re.sub(replacement, statement)
                            stms.append(new)
                    else:
                        self._logger.warning("Cannot get signature for the label {!r}".format(access.label.name))
            elif fn in self.irq_function_map:
                statement = self.simple_function_re.sub(self.irq_function_map[fn] + '(', statement)
                stms.append(statement)
            else:
                raise NotImplementedError("Model function '${}' is not supported".format(fn))

        if not matched:
            stms = [statement]

        # Replace rest accesses
        final = []
        for original_stm in stms:
            # Collect dublicates
            stm_set = {original_stm}

            while len(stm_set) > 0:
                stm = stm_set.pop()
                match = self.access_re.search(stm)
                if match:
                    expression = match.group(1)
                    accesses = automaton.process.resolve_access(expression)
                    for access in accesses:
                        var = automaton.determine_variable(access.label)
                        stm = stm.replace(expression, var.name)
                        stm_set.add(stm)
                else:
                    final.append(stm)

        return final

    def _replace_mem_call(self, match):
        func, label_name, flag = match.groups()
        size = '0'

        if func not in self.mem_function_map:
            raise NotImplementedError("Model of {} is not supported".format(func))
        elif not self.mem_function_map[func]:
            raise NotImplementedError("Set implementation for the function {}".format(func))

        if isinstance(self.signature, Pointer):
            if func == 'ALLOC' and self.ualloc_flag:
                # Do not alloc memory anyway for unknown resources anyway to avoid incomplete type errors
                func = 'UALLOC'
            if get_conf_property(self._conf, 'disable ualloc') and func == 'UALLOC':
                func = 'ALLOC'
            if func != 'UALLOC' and get_conf_property(self._conf, 'allocate with sizeof'):
                size = 'sizeof({})'.format(self.signature.points.to_string('', typedef='complex_and_params'))

            return "{}({})".format(self.mem_function_map[func], size)
        else:
            raise ValueError('This is not a pointer')

    def _replace_free_call(self, match):
        func, label_name, flag = match.groups()
        if func not in self.free_function_map:
            raise NotImplementedError("Model of {} is not supported".format(func))
        elif not self.free_function_map[func]:
            raise NotImplementedError("Set implementation for the function {}".format(func))

        # Create function call
        if isinstance(self.signature, Pointer):
            return "{}(%{}%)".format(self.free_function_map[func], label_name)
        else:
            raise ValueError('This is not a pointer')
