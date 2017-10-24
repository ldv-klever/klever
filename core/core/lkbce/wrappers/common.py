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

import filecmp
import json
import os
import re
import shutil
import subprocess

import core.utils
import core.lkbce.utils


class Command:
    # We assume that CC/LD options always start with "-".
    # Some CC/LD options always require values that can be specified either together with option itself (maybe separated
    # with "=") or by means of the following option.
    # Some CC options allow to omit both CC input and output files.
    # Value of -o is CC/LD output file.
    # The rest options are CC/LD input files.
    OPTS = {
        'gcc': {
            'opts requiring vals': ('D', 'I', 'O', 'include', 'isystem', 'mcmodel', 'o', 'print-file-name', 'x', 'idirafter'),
            'opts discarding in files': ('print-file-name', 'v'),
            'opts discarding out file': ('E', 'print-file-name', 'v')
        },
        'ld': {
            'opts requiring vals': ('T', 'm', 'o',),
            'opts discarding in files': ('-help',),
            'opts discarding out file': ('-help',)
        },
        'objcopy': {
            'opts requiring vals': ('-set-section-flags', '-rename-section'),
            'opts discarding in files': (),
            'opts discarding out file': ()
        }
    }

    def __init__(self, argv):
        self.name = os.path.basename(argv[0])
        self.opts = argv[1:]
        self.in_files = []
        self.out_file = None
        self.other_opts = []
        self.type = None
        self.desc_file = None

        if 'KLEVER_PREFIX' in os.environ:
            self.prefix = os.environ['KLEVER_PREFIX']
        else:
            self.prefix = None

    @property
    def name_without_prefix(self):
        if self.prefix:
            pre, prefix, name = self.name.rpartition(self.prefix)
        else:
            name = self.name

        return name

    def copy_deps(self):
        # Dependencies can be obtained just for CC commands taking normal C files as input.
        if self.type != 'CC' or re.search(r'\.S$', self.in_files[0], re.IGNORECASE):
            return

        # We assume that dependency files are generated for all C source files.
        base_name = '{0}.d'.format(os.path.basename(self.out_file))
        if base_name[0] != '.':
            base_name = '.' + base_name
        deps_file = os.path.join(os.path.dirname(self.out_file), base_name)
        if not os.path.isfile(deps_file):
            p = subprocess.Popen(['aspectator'] + self.opts + ['-Wp,-MD,{0}'.format(deps_file)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if p.wait():
                raise RuntimeError('Getting dependencies failed')

        deps = core.lkbce.utils.get_deps_from_gcc_deps_file(deps_file)

        # There are several kinds of dependencies:
        # - each non-absolute file path represents dependency relative to current working directory (Linux kernel
        #   working source tree is assumed) - they all should be copied;
        # - each absolute file path that starts with current working directory is the same as above;
        # - other absolute file paths represent either system or compiler specific headers that aren't touched by
        #   build process and can be used later as is.
        for dep in deps:
            if os.path.isabs(dep) and os.path.commonprefix((os.getcwd(), dep)) != os.getcwd():
                continue

            dest_dep = os.path.join(os.path.dirname(os.environ['KLEVER_BUILD_CMD_DESCS_FILE']),
                                    os.path.relpath(dep))
            os.makedirs(os.path.dirname(dest_dep).encode('utf8'), exist_ok=True)
            with core.utils.LockedOpen(dest_dep, 'a', encoding='utf8'):
                if os.path.getsize(dest_dep):
                    if filecmp.cmp(dep, dest_dep):
                        continue
                    # Just version in "include/generated/compile.h" changes, all other content remain the same.
                    elif not dep == 'include/generated/compile.h':
                        raise AssertionError('Dependency "{0}" changed to "{1}"'.format(dest_dep, dep))
                else:
                    shutil.copy2(dep, dest_dep)

    def dump(self):
        full_desc_file = None

        if self.type == 'CC':
            full_desc = {
                'cwd': os.path.relpath(os.path.dirname(os.environ['KLEVER_BUILD_CMD_DESCS_FILE']),
                                       os.environ['KLEVER_MAIN_WORK_DIR']),
                'in files': self.in_files,
                'out file': self.out_file,
                # Fix up absolute paths including current working directory. We rely on exact matching that will not be
                # the case if there will be ".." in file paths.
                'opts': [re.sub(re.escape(os.getcwd()),
                                os.path.dirname(os.environ['KLEVER_BUILD_CMD_DESCS_FILE']),
                                opt) for opt in self.other_opts]
            }

            full_desc_file = os.path.join(os.path.dirname(os.environ['KLEVER_BUILD_CMD_DESCS_FILE']),
                                          '{0}.full.json'.format(self.out_file))

            os.makedirs(os.path.dirname(full_desc_file).encode('utf8'), exist_ok=True)

            full_desc_file_suffix = 2
            while True:
                if os.path.isfile(full_desc_file):
                    full_desc_file = '{0}.ldv{1}{2}'.format(os.path.splitext(full_desc_file)[0], full_desc_file_suffix,
                                                            os.path.splitext(full_desc_file)[1])
                    full_desc_file_suffix += 1
                else:
                    break

            with open(full_desc_file, 'w', encoding='utf8') as fp:
                json.dump(full_desc, fp, ensure_ascii=False, sort_keys=True, indent=4)

            # Options used for compilation of this file will be used for compilation of model files written in C.
            if self.in_files[0] == 'scripts/mod/empty.c':
                with open(os.path.join(os.path.dirname(os.environ['KLEVER_BUILD_CMD_DESCS_FILE']),
                                       'model CC opts.json'), 'w', encoding='utf8') as fp:
                    json.dump(self.other_opts, fp, ensure_ascii=False, sort_keys=True, indent=4)

        # Extract info for multimodule analysis
        provided_functions = []
        required_functions = []
        output_size = 0
        HEADER_SIZE = 4

        # Checks, that file is ELF object
        elf_out = subprocess.check_output(['file', '-b', self.out_file], universal_newlines=True).split('\n')
        if elf_out and elf_out[0].startswith('ELF'):
            # Process symbol table. We need to skip first 4 lines, since it is a useless header
            symbol_table = subprocess.check_output(['objdump', '-t', self.out_file], universal_newlines=True).split('\n')
            for table_entry in symbol_table[HEADER_SIZE:]:
                # Split row into columns
                symbol_entities = re.split(r'\s+|\t', table_entry)
                if len(symbol_entities) > 3 and symbol_entities[1] == '*UND*':
                    # Undefined symbol is an import function
                    required_functions.append(symbol_entities[3])
                elif len(symbol_entities) > 5 and symbol_entities[1] == 'g':
                    # Global symbol is an export functions
                    provided_functions.append(symbol_entities[5])
            # Size of output file
            output_size = os.path.getsize(self.out_file)

        desc = {'type': self.type, 'in files': self.in_files, 'out file': self.out_file,
                'provided functions': provided_functions, 'required functions': required_functions,
                'output size': output_size}
        if full_desc_file:
            desc['full desc file'] = os.path.relpath(full_desc_file, os.environ['KLEVER_MAIN_WORK_DIR'])

        self.desc_file = os.path.join(os.path.dirname(os.environ['KLEVER_BUILD_CMD_DESCS_FILE']),
                                      '{0}.json'.format(self.out_file))

        os.makedirs(os.path.dirname(self.desc_file).encode('utf8'), exist_ok=True)

        bn, ext = os.path.splitext(self.desc_file)
        cnt = 0
        while True:
            if os.path.isfile(self.desc_file):
                self.desc_file = '{0}.ldv{1}'.format(bn, str(cnt))
                cnt += 1
            else:
                break

        with open(self.desc_file, 'w', encoding='utf8') as fp:
            json.dump(desc, fp, ensure_ascii=False, sort_keys=True, indent=4)

    def enqueue(self):
        with core.utils.LockedOpen(os.environ['KLEVER_BUILD_CMD_DESCS_FILE'], 'a', encoding='utf8') as fp:
            fp.write(os.path.relpath(self.desc_file, os.environ['KLEVER_MAIN_WORK_DIR']) + '\n')

    def filter(self):
        # Filter out CC commands if input files or output file are absent or input files are '/dev/null' or STDIN ('-')
        # or samples. They won't be used when building verification object descriptions.
        if self.type == 'CC':
            if self.in_files[0].endswith('.mod.c'):
                return True
            if not self.in_files or not self.out_file:
                return True
            if self.in_files[0] in ('/dev/null', '-'):
                return True

        # Filter out LD commands if input file is absent or output file is temporary. The latter likely corresponds
        # to CC commands filtered out above.
        if self.type == 'LD':
            self.in_files = [in_file for in_file in self.in_files if not in_file.endswith('.mod.o')]
            if not self.out_file or self.out_file.endswith('.tmp'):
                return True

        return False

    def launch(self):
        # Exclude path where wrapper build command is located.
        os.environ['PATH'] = re.sub(r'^[^:]+:', '', os.environ['PATH'])

        # Execute original build command.
        if self.name_without_prefix == 'gcc':
            self.opts.append('-I{0}'.format(os.environ['KLEVER_RULE_SPECS_DIR']))
        exit_code = subprocess.call(tuple(['aspectator' if self.name_without_prefix == 'gcc'
                                           else self.name] + self.opts))

        # Do not proceed in case of failures (http://forge.ispras.ru/issues/6704).
        if exit_code:
            return exit_code

        try:
            self.parse()

            if not self.filter() and 'KLEVER_BUILD_CMD_DESCS_FILE' in os.environ:
                self.copy_deps()
                self.dump()
                self.enqueue()
        except Exception:
            # TODO: KLEVER_BUILD_CMD_DESCS_FILE could be not specified at this point.
            with core.utils.LockedOpen(os.environ['KLEVER_BUILD_CMD_DESCS_FILE'], 'a', encoding='utf8') as fp:
                fp.write('KLEVER FATAL ERROR\n')
            raise

        return 0

    def parse(self):
        # Input files and output files should be presented almost always.
        cmd_requires_in_files = True
        cmd_requires_out_file = True

        if self.name_without_prefix in ('gcc', 'ld', 'objcopy'):
            skip_next_opt = False
            for idx, opt in enumerate(self.opts):
                # Option represents already processed value of the previous option.
                if skip_next_opt:
                    skip_next_opt = False
                    continue

                for opt_discarding_in_files in self.OPTS[self.name_without_prefix]['opts discarding in files']:
                    if re.search(r'^-{0}'.format(opt_discarding_in_files), opt):
                        cmd_requires_in_files = False

                for opt_discarding_out_file in self.OPTS[self.name_without_prefix]['opts discarding out file']:
                    if re.search(r'^-{0}'.format(opt_discarding_out_file), opt):
                        cmd_requires_out_file = False

                # Options with values.
                match = None
                for opt_requiring_val in self.OPTS[self.name_without_prefix]['opts requiring vals']:
                    match = re.search(r'^-({0})(=?)(.*)'.format(opt_requiring_val), opt)
                    if match:
                        opt, eq, val = match.groups()

                        # Option value is specified by means of the following option.
                        if not val:
                            val = self.opts[idx + 1]
                            skip_next_opt = True

                        # Output file.
                        if opt == 'o':
                            self.out_file = val
                        else:
                            # Use original formatting of options.
                            if skip_next_opt:
                                self.other_opts.extend(['-{0}'.format(opt), val])
                            else:
                                self.other_opts.append('-{0}{1}{2}'.format(opt, eq, val))

                        break

                if not match:
                    # Options without values.
                    if re.search(r'^-.+$', opt):
                        self.other_opts.append(opt)
                    # Input files.
                    else:
                        self.in_files.append(opt)
        elif self.name == 'mv':
            # We assume that MV options always have such the form:
            #     [-opt]... in_file out_file
            for opt in self.opts:
                if re.search(r'^-', opt):
                    self.other_opts.append(opt)
                elif not self.in_files:
                    self.in_files.append(opt)
                else:
                    self.out_file = opt
        else:
            raise NotImplementedError(
                'Linux kernel raw build command "{0}" is not supported yet'.format(self.name))

        if self.name == 'objcopy':
            # objcopy has only one input file and no more than one output file.
            # out file is the same as in file if it didn't specified.
            if len(self.in_files) == 2:
                self.out_file = self.in_files[-1]
                self.in_files = self.in_files[:-1]
            else:
                self.out_file = self.in_files[-1]

        if cmd_requires_in_files and not self.in_files:
            raise ValueError(
                'Could not get Linux kernel raw build command input files' + ' from options "{0}"'.format(self.opts))
        if cmd_requires_out_file and not self.out_file:
            raise ValueError(
                'Could not get Linux kernel raw build command output file' + ' from options "{0}"'.format(self.opts))

        # Check thar all original options becomes either input files or output file or options.
        # Option -o isn't included in the resulting set.
        original_opts = list(self.opts)
        if '-o' in original_opts:
            original_opts.remove('-o')
        resulting_opts = self.in_files + self.other_opts
        if self.out_file:
            resulting_opts.append(self.out_file)
        if set(original_opts) != set(resulting_opts):
            raise RuntimeError(
                'Some options were not parsed: "{0} != {1} + {2} + {3}"'.format(original_opts, self.in_files,
                                                                                self.out_file, self.opts))

        # We treat all invocations of GCC with more than one input file as pure linking whereas this might be not the
        # case in general.
        if self.name_without_prefix != 'gcc':
            self.type = self.name_without_prefix.upper()
        elif len(self.in_files) > 1:
            self.type = 'LD'
        else:
            for in_file in self.in_files:
                if not in_file.endswith('.o'):
                    self.type = 'CC'
                    break
            else:
                self.type = 'LD'
