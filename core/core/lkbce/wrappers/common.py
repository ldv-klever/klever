import filecmp
import json
import os
import re
import shutil
import subprocess

import core.utils


class Command:
    # We assume that CC/LD options always start with "-".
    # Some CC/LD options always require values that can be specified either together with option itself (maybe separated
    # with "=") or by means of the following option.
    # Some CC options allow to omit both CC input and output files.
    # Value of -o is CC/LD output file.
    # The rest options are CC/LD input files.
    OPTS = {
        'gcc': {
            'opts requiring vals': ('D', 'I', 'O', 'include', 'isystem', 'mcmodel', 'o', 'print-file-name', 'x'),
            'opts discarding in files': ('print-file-name', 'v'),
            'opts discarding out file': ('E', 'print-file-name', 'v')
        },
        'ld': {
            'opts requiring vals': ('T', 'm', 'o',),
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

    def copy_deps(self):
        # Dependencies can be obtained just for CC commands taking normal C files as input.
        if self.type != 'CC' or re.search(r'\.S$', self.in_files[0], re.IGNORECASE):
            return

        # We assume that dependency files are generated for all C source files.
        deps_file = None
        for opt in self.other_opts:
            match = re.search(r'-MD,(.+)', opt)
            if match:
                deps_file = match.group(1)
                break
        if not deps_file:
            # Generate them by ourselves if not so.
            deps_file = self.out_file + '.d'
            p = subprocess.Popen(['aspectator', '-M', '-MF', deps_file] + self.opts, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            if p.wait():
                raise RuntimeError('Getting dependencies failed')

        deps = []
        with open(deps_file, encoding='ascii') as fp:
            match = re.match(r'[^:]+:(.+)', fp.readline())
            if match:
                first_dep_line = match.group(1)
            else:
                raise AssertionError('Dependencies file has unsupported format')

            for dep_line in [first_dep_line] + fp.readlines():
                dep_line = dep_line.lstrip(' ')
                dep_line = dep_line.rstrip(' \\\n')
                if not dep_line:
                    continue
                deps.extend(dep_line.split(' '))

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
            os.makedirs(os.path.dirname(dest_dep), exist_ok=True)
            with core.utils.LockedOpen(dest_dep, 'a', encoding='ascii'):
                if os.path.getsize(dest_dep):
                    if filecmp.cmp(dep, dest_dep):
                        continue
                    # Just version in "include/generated/compile.h" changes, all other content remain the same.
                    elif not dep == 'include/generated/compile.h':
                        raise AssertionError('Dependency "{0}" changed to "{1}"'.format(dest_dep, dep))
                else:
                    shutil.copy2(dep, dest_dep)

        # Fix up absolute paths including current working directory. We rely on exact matching that will not be the
        # case if there will be ".." in file paths.
        self.other_opts = [re.sub(re.escape(os.getcwd()),
                                  os.path.dirname(os.environ['KLEVER_BUILD_CMD_DESCS_FILE']),
                                  opt)
                           for opt in self.other_opts]

    def dump(self):
        full_desc_file = None

        if self.type == 'CC':
            full_desc = {
                'cwd': os.path.relpath(os.path.dirname(os.environ['KLEVER_BUILD_CMD_DESCS_FILE']),
                                       os.environ['KLEVER_MAIN_WORK_DIR']),
                'in files': self.in_files,
                'out file': self.out_file,
                'opts': self.other_opts
            }

            full_desc_file = os.path.join(os.path.dirname(os.environ['KLEVER_BUILD_CMD_DESCS_FILE']),
                                          '{0}.full.json'.format(self.out_file))

            os.makedirs(os.path.dirname(full_desc_file), exist_ok=True)

            full_desc_file_suffix = 2
            while True:
                if os.path.isfile(full_desc_file):
                    full_desc_file = '{0}.ldv{1}{2}'.format(os.path.splitext(full_desc_file)[0], full_desc_file_suffix,
                                                            os.path.splitext(full_desc_file)[1])
                    full_desc_file_suffix += 1
                else:
                    break

            with open(full_desc_file, 'w', encoding='ascii') as fp:
                json.dump(full_desc, fp, sort_keys=True, indent=4)

        desc = {'type': self.type, 'in files': self.in_files, 'out file': self.out_file}
        if full_desc_file:
            desc['full desc file'] = os.path.relpath(full_desc_file, os.environ['KLEVER_MAIN_WORK_DIR'])

        self.desc_file = os.path.join(os.path.dirname(os.environ['KLEVER_BUILD_CMD_DESCS_FILE']),
                                      '{0}.json'.format(self.out_file))

        os.makedirs(os.path.dirname(self.desc_file), exist_ok=True)

        desc_file_suffix = 2
        while True:
            if os.path.isfile(self.desc_file):
                self.desc_file = '{0}.ldv{1}{2}'.format(os.path.splitext(self.desc_file)[0], desc_file_suffix,
                                                        os.path.splitext(self.desc_file)[1])
                desc_file_suffix += 1
            else:
                break

        with open(self.desc_file, 'w', encoding='ascii') as fp:
            json.dump(desc, fp, sort_keys=True, indent=4)

    def enqueue(self):
        with core.utils.LockedOpen(os.environ['KLEVER_BUILD_CMD_DESCS_FILE'], 'a', encoding='ascii') as fp:
            fp.write(os.path.relpath(self.desc_file, os.path.dirname(os.environ['KLEVER_BUILD_CMD_DESCS_FILE'])) + '\n')

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
        if 'KLEVER_BUILD_CMD_DESCS_FILE' in os.environ and self.name == 'gcc':
            self.opts.append(
                "-I{}".format(os.environ['KLEVER_JOB_ROOT']))
        exit_code = subprocess.call(tuple(['aspectator' if self.name == 'gcc' else self.name] + self.opts))

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
            with core.utils.LockedOpen(os.environ['KLEVER_BUILD_CMD_DESCS_FILE'], 'a', encoding='ascii') as fp:
                fp.write('KLEVER FATAL ERROR\n')
            raise

        return 0

    def parse(self):
        # Input files and output files should be presented almost always.
        cmd_requires_in_files = True
        cmd_requires_out_file = True

        if self.name in ('gcc', 'ld'):
            skip_next_opt = False
            for idx, opt in enumerate(self.opts):
                # Option represents already processed value of the previous option.
                if skip_next_opt:
                    skip_next_opt = False
                    continue

                for opt_discarding_in_files in self.OPTS[self.name]['opts discarding in files']:
                    if re.search(r'^-{0}'.format(opt_discarding_in_files), opt):
                        cmd_requires_in_files = False

                for opt_discarding_out_file in self.OPTS[self.name]['opts discarding out file']:
                    if re.search(r'^-{0}'.format(opt_discarding_out_file), opt):
                        cmd_requires_out_file = False

                # Options with values.
                match = None
                for opt_requiring_val in self.OPTS[self.name]['opts requiring vals']:
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

        if cmd_requires_in_files and not self.in_files:
            raise ValueError(
                'Could not get Linux kernel raw build command input files' + ' from options "{0}"'.format(self.opts))
        if cmd_requires_out_file and not self.out_file:
            raise ValueError(
                'Could not get Linux kernel raw build command output file' + ' from options "{0}"'.format(self.opts))

        # Check thar all original options becomes either input files or output file or options.
        # Option -o isn't included in the resulting set.
        original_opts = self.opts
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
        if self.name != 'gcc':
            self.type = self.name.upper()
        elif len(self.in_files) == 1:
            self.type = 'CC'
        else:
            self.type = 'LD'
