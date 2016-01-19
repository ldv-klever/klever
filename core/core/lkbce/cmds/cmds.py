import os
import re
import subprocess

import core.utils


class Command:
    # All command line argument will be printed at separate line and they aren't empty strings. So one empty string
    # can safely separate different build commands from each other.
    cmds_separator = '\n'

    def __init__(self, argv):
        self.cmd = os.path.basename(argv[0])
        self.opts = argv[1:]

    def launch(self):
        # TODO: remove these ugly workarounds after updating Aspectator to one of the newest version of GCC.
        if self.cmd == 'gcc':
            for unsupported_opt in ('-Werror=date-time', '-mpreferred-stack-boundary=3', '-Wno-maybe-uninitialized',
                                    '--param=allow-store-data-races=0'):
                if unsupported_opt in self.opts:
                    self.opts.remove(unsupported_opt)

        # TODO: replacement of GCC with CC is incorrect in general case since GCC can accept several input files,
        # compile and link them together. But there is the only example when this happens when complete build of the
        # Linux kernel, and corresponding object file isn't linked to any module. More proper implementation is to
        # replace GCC with CC and LD if it is necessary.
        with core.utils.LockedOpen(os.environ['LINUX_KERNEL_RAW_BUILD_CMDS_FILE'], 'a', encoding='ascii') as fp:
            fp.write('{0}\n{1}'.format('\n'.join([self.cmd.upper() if self.cmd != 'gcc' else 'CC'] + self.opts),
                                       self.cmds_separator))

        # Eclude path where wrapper build command is located.
        os.environ['PATH'] = re.sub(r'^[^:]+:', '', os.environ['PATH'])

        # Execute original build command.
        subprocess.call(tuple(['aspectator' if self.cmd == 'gcc' else self.cmd] + self.opts))
