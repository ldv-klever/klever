#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

import os
import re

from core.utils import unique_file_name
from core.vtg.emg.common import get_or_die, model_comment
from core.vtg.emg.common.c import Function
from core.vtg.emg.common.c.types import Pointer, Primitive


def action_model_comment(action, text, begin=None):
    """
    Model comment for identifying an action.

    :param action: Action object.
    :param text: Action comment string.
    :param begin: True if this is a comment before the action and False otherwise.
    :return: Model comment string.
    """
    if action:
        if action.trace_relevant:
            type_comment = 'CALL'
        else:
            type_comment = type(action).__name__.upper()
        if begin is True:
            type_comment += '_BEGIN'
        elif begin is False:
            type_comment += '_END'

        name_comment = action.name.upper()
    else:
        type_comment = 'ARTIFICIAL'
        name_comment = None

    data = {'action': name_comment}
    if action and action.trace_relevant and begin is True:
        data['callback'] = True
    return model_comment(type_comment, text, data)


def control_function_comment_begin(function_name, comment, identifier=None):
    """
    Compose a comment at the beginning of a control function.

    :param function_name: Control function name.
    :param comment: Comment text.
    :param identifier: Thread identifier if necessary.
    :return: Model comment string.
    """
    data = {'function': function_name}
    if isinstance(identifier, int):
        data['thread'] = identifier + 1
    return model_comment('CONTROL_FUNCTION_BEGIN', comment, data)


def control_function_comment_end(function_name, name):
    """
    Compose a comment at the end of a control function.

    :param function_name: Control function name.
    :param name: Process or Automaton name.
    :return: Model comment string.
    """
    data = {'function': function_name}
    return model_comment('CONTROL_FUNCTION_END', "End of control function based on process {!r}".format(name), data)


class Aspect(Function):
    """
    Representation of the aspect file pointcuts for source functions which calls should be modified or replaced by
    models. This is an aspect-oriented extension of the C language which is supported by CIF.
    """

    def __init__(self, name, declaration, aspect_type="after"):
        super(Aspect, self).__init__(name, declaration)
        self.aspect_type = aspect_type

    def define(self, scope=None):
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
    comment_map = {
        'COMMENT': None
    }

    def __init__(self, logger, conf, workdir, files, entry_point_name, entry_file):
        self.entry_file = entry_file
        self.entry_name = entry_point_name
        self.files = files
        self.types = dict()
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
        self._headers.setdefault(file, []).append(headers)

    def add_function_definition(self, func):
        """
        Add a function definition to the main environment model file.

        :param func: Function object.
        :return: None.
        """
        if not func.definition_file:
            raise RuntimeError('Always expect file to place function definition')
        definitions = self._function_definitions.setdefault(func.definition_file, {})
        self._function_definitions.setdefault(self.entry_file, {})

        definitions[func.name] = func.define(scope={func.definition_file})
        self.add_function_declaration(func.definition_file, func, extern=False)

    def add_function_declaration(self, file, func, extern=False):
        """
        Add a function declaration to the file.

        :param file: File name.
        :param func: Function object.
        :param extern: Add it as an extern function.
        :return: None.
        """
        declarations = self._function_declarations.setdefault(file, {})
        if not (extern and func.name in declarations):
            declarations[func.name] = func.declare(extern=extern, scope={file})

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

        declarattions = self._variables_declarations.setdefault(file, {})
        initializations = self._variables_initializations.setdefault(file, {})

        if extern:
            declarattions.setdefault(variable.name, variable.declare(extern=extern) + ";\n")
        else:
            declarattions[variable.name] = variable.declare(extern=extern) + ";\n"
            if initialize:
                if variable.value and (
                        (isinstance(variable.declaration, Pointer) and
                         isinstance(variable.declaration.points, Function)) or
                        isinstance(variable.declaration, Primitive)):
                    initializations[variable.name] = variable.declare_with_init() + ";\n"
                elif not variable.value and isinstance(variable.declaration, Pointer):
                    self.__external_allocated.setdefault(file, []).append(variable)

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

        for file in set(func.files_called_at).union(func.declaration_files):
            self._call_aspects.setdefault(file, []).append(new_aspect)

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

        if self._conf["translation options"].get("propogate headers to instrumented files", True):
            for file in (f for f in self.files if f in additional_lines):
                self.add_headers(file, get_or_die(self._conf["translation options"], "additional headers"))

        addictions = dict()
        # Write aspects
        for file in self.files:
            lines = list()

            # Check headers
            if file == self.entry_file:
                lines += ['#include <{}>\n'.format(h)
                          for h in self._collapse_headers_sets(self._headers.get(self.entry_file, []))] + ["\n"]
            else:
                # Generate function declarations
                self._logger.info('Add aspects to a file {!r}'.format(file))

                # Add headers
                if self._headers.get(file):
                    lines += ['before: file ("$this")\n', '{\n'] + \
                             ['#include <{}>\n'.format(h) for h in self._collapse_headers_sets(self._headers[file])] + \
                             ["\n", "}\n\n"]

                # Add model itself
                lines.extend(['after: file ("$this")\n', '{\n'])

            for tp in self.types.get(file, list()):
                lines += [tp.to_string('') + " {\n"] + \
                         [("\t{};\n".format(tp.fields[field].
                                            to_string(field, typedef='complex_and_params'), scope={file}))
                          for field in list(tp.fields.keys())] + \
                         ["};\n", "\n"]

            # Add declarations
            if additional_lines.get(file, {}).get('declarations'):
                lines += ["\n", "/* EMG aliases */\n"] + additional_lines[file]['declarations']
            if file in self._function_declarations:
                lines += ["\n", "/* EMG Function declarations */\n"] + \
                         [line for func in self._function_declarations[file].keys()
                          for line in self._function_declarations[file][func]]

            if file in self._variables_declarations:
                lines += ["\n", "/* EMG variable declarations */\n"] + \
                         [decl for declarations in self._variables_declarations[file].values() for decl in declarations]

            if self._variables_initializations.get(file):
                lines += ["\n", "/* EMG variable initialization */\n"] + \
                         [i for inits in self._variables_initializations[file].values() for i in inits]

            if additional_lines.get(file, {}).get('definitions'):
                lines.extend(
                    ["\n", "/* EMG aliases for functions */\n"] +
                    additional_lines[file]['definitions']
                )

            if self._function_definitions.get(file):
                lines += ["\n", "/* EMG function definitions */\n"] + \
                         [line for defs in self._function_definitions[file].values() for line in defs + ["\n"]]

            if file != self.entry_file:
                lines.append("}\n\n")

            if self._call_aspects.get(file):
                lines += ["/* EMG kernel function models */\n"] + \
                         [line for aspect in self._call_aspects[file] for line in aspect.define() + ["\n"]]

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
            for file, ext_vars in ((f, v) for f, v in self.__external_allocated.items() if v):
                func = Function('ldv_allocate_external_{}'.format(cnt),
                                "void ldv_allocate_external_{}(void)".format(cnt))
                func.declaration_files.add(file)
                func.definition_file = file

                init = ["{} = {}();".format(var.name, 'external_allocated_data') for var in ext_vars]
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
            body += [
                '/* Initialize external data */',
                'ldv_initialize_external_data();'
            ]

        if self._conf.get("initialize requirements", True):
            body += [
                '/* LDV {"action": "INIT", "type": "CALL_BEGIN", "callback": true, '
                '"comment": "Initialize requirement models."} */',
                'ldv_initialize();',
                '/* LDV {"action": "INIT", "type": "CALL_END"} */'
            ]

        body += ['/* LDV {"action": "SCENARIOS", "type": "CONDITION_BEGIN", '
                 '"comment": "Begin Environment model scenarios."} */'] + given_body + \
                ['/* LDV {"action": "SCENARIOS", "type": "CONDITION_END"} */']

        if self._conf.get("check final state", True):
            body += [
                '/* LDV {"action": "FINAL", "callback": true, "type": "CALL_BEGIN", '
                '"comment": "Check requirement model final state at the exit if required."} */',
                'ldv_check_final_state();',
                '/* LDV {"action": "FINAL", "type": "CALL_END"} */'
            ]

        body += ['return 0;',
                 '/* LDV {' +
                 '"comment": "Exit entry point \'{0}\'", "type": "CONTROL_FUNCTION_END", "function": "{0}"'.
                 format(self.entry_name) + '} */']

        ep.body = body
        self.add_function_definition(ep)

        return body

    @staticmethod
    def _collapse_headers_sets(sets):
        final_list = []
        sortd = sorted(sets, key=lambda f: len(f))
        while len(sortd) > 0:
            data = sortd.pop()
            difference = set(data).difference(set(final_list))
            if len(difference) > 0 and len(difference) == len(data):
                # All headers are new
                final_list.extend(data)
            elif len(difference) > 0:
                position = len(final_list)
                for header in reversed(data):
                    if header not in difference:
                        position = final_list.index(header)
                    else:
                        final_list.insert(position, header)
        return final_list


class FunctionModels:
    """Class represent common C extensions for simplifying environmen model C code generators."""

    mem_function_template = r'\$({})\(%({})%(?:,\s?(\w+))?\)'
    simple_function_template = r'\$({})\('
    access_template = r'\w+(?:(?:[.]|->)\w+)*'
    comment_template = re.compile(r'\$COMMENT\((\w+), (\w+)\);$')
    mem_function_re = re.compile(mem_function_template.format(r'\w+', access_template))
    simple_function_re = re.compile(simple_function_template.format(r'\w+'))
    access_re = re.compile(r'(%{}%)'.format(access_template))
    arg_re = re.compile(r'\$ARG(\d+)')

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

        # First replace simple replacements
        for number in self.arg_re.findall(statement):
            new_number = int(number) - 1
            statement = statement.replace('$ARG{}'.format(number), 'arg{}'.format(new_number))

        # Replace comments
        cmnt_match = self.comment_template.search(statement)
        if cmnt_match:
            replacement = self._replace_comment(cmnt_match)
            statement = statement.replace(cmnt_match.group(0), replacement)
            return [statement]
        else:
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

                    access = automaton.process.resolve_access('%{}%'.format(access))
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
                    raise NotImplementedError("Model function '${}' is not supported at line {!r}".
                                              format(fn, statement))

            if not matched:
                stms = [statement]

            # Replace rest accesses
            final = []
            for original_stm in stms:
                # Collect duplicates
                stm_set = {original_stm}

                while len(stm_set) > 0:
                    stm = stm_set.pop()
                    match = self.access_re.search(stm)
                    if match:
                        expression = match.group(1)
                        access = automaton.process.resolve_access(expression)
                        if not access:
                            raise ValueError("Cannot resolve access in statement {!r} and expression {!r}".
                                             format(stm, expression))
                        var = automaton.determine_variable(access.label)
                        stm = stm.replace(expression, var.name)
                        stm_set.add(stm)
                    else:
                        final.append(stm)

            return final

    def _replace_comment(self, match):
        arguments = match.groups()
        if arguments[0] == 'callback':
            name = arguments[1]
            cmnt = model_comment('callback', name, {'call': "{}();".format(name)})
            return cmnt
        else:
            raise NotImplementedError("Replacement of {!r} comments is not implemented".format(arguments[0]))

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
            if self._conf.get('disable ualloc') and func == 'UALLOC':
                func = 'ALLOC'
            if func != 'UALLOC' and self._conf.get('allocate with sizeof', True):
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
