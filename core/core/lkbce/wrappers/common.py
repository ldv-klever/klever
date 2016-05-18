import json
import os
import re
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

    def dump(self):
        if 'KLEVER_BUILD_CMD_DESCS_FILE' not in os.environ:
            return

        full_desc_file = None

        if self.type == 'CC':
            full_desc_file = os.path.join(os.path.dirname(os.environ['KLEVER_BUILD_CMD_DESCS_FILE']),
                                          '{0}.full.json'.format(self.out_file))

            if os.path.isfile(full_desc_file):
                # Sometimes when building several individual modules the same modules are built several times including
                # building of corresponding mod.o files. Do not fail in this case.
                if not self.out_file.endswith('mod.o'):
                    raise FileExistsError(
                        'Linux kernel CC full description file "{0}" already exists'.format(full_desc_file))
            else:
                os.makedirs(os.path.dirname(full_desc_file), exist_ok=True)
                with open(full_desc_file, 'w', encoding='ascii') as fp:
                    json.dump({'in files': self.in_files, 'out file': self.out_file, 'opts': self.other_opts}, fp,
                              sort_keys=True, indent=4)

        desc = {'type': self.type, 'in files': self.in_files, 'out file': self.out_file}
        if full_desc_file:
            desc['full desc file'] = os.path.relpath(full_desc_file, os.environ['KLEVER_MAIN_WORK_DIR'])

        desc_file = os.path.join(os.path.dirname(os.environ['KLEVER_BUILD_CMD_DESCS_FILE']),
                                 '{0}.json'.format(self.out_file))

        if os.path.isfile(desc_file):
            raise FileExistsError('Linux kernel build command description file "{0}" already exists'.format(desc_file))
        else:
            os.makedirs(os.path.dirname(desc_file), exist_ok=True)
            with open(desc_file, 'w', encoding='ascii') as fp:
                json.dump(desc, fp, sort_keys=True, indent=4)

        with core.utils.LockedOpen(os.environ['KLEVER_BUILD_CMD_DESCS_FILE'], 'a', encoding='ascii') as fp:
            fp.write(os.path.relpath(desc_file, os.path.dirname(os.environ['KLEVER_BUILD_CMD_DESCS_FILE'])) + '\n')

    def filter(self):
        # Filter out CC commands if input file is absent or '/dev/null' or STDIN ('-') or 'init/version.c' or output
        # file is absent. They won't be used when building verification object descriptions.
        if self.type == 'CC' and (
                        not self.in_files or self.in_files[0] in (
                            '/dev/null', '-', 'init/version.c') or not self.out_file):
            return True

        # Filter out LD commands if input file is absent or output file is temporary. The latter likely corresponds
        # to CC commands filtered out above.
        if self.type == 'LD' and (not self.out_file or self.out_file.endswith('.tmp')):
            return True

        return False

    def launch(self):
        # Exclude path where wrapper build command is located.
        os.environ['PATH'] = re.sub(r'^[^:]+:', '', os.environ['PATH'])

        # Execute original build command.
        exit_code = subprocess.call(tuple(['aspectator' if self.name == 'gcc' else self.name] + self.opts))

        # Do not proceed in case of failures (http://forge.ispras.ru/issues/6704).
        if exit_code:
            return exit_code

        self.parse()
        if not self.filter():
            self.dump()

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
