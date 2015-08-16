import os
import re
import subprocess


class Command:
    def __init__(self, argv):
        self.argv = argv

    def launch(self):
        # Eclude path where wrapper command is located.
        os.environ['PATH'] = re.sub(r'^[^:]+:', '', os.environ['PATH'])

        # Execute original command.
        subprocess.call(tuple([os.path.basename(self.argv[0])] + self.argv[1:]))
