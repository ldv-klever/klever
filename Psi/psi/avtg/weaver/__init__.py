#!/usr/bin/python3

import json
import os

import psi.components
import psi.utils


class Weaver(psi.components.Component):
    def weave(self):
        self.abstract_task_desc = self.mqs['abstract task description'].get()

        self.abstract_task_desc['extra C files'] = []

        for grp in self.abstract_task_desc['grps']:
            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                extra_c_file = {}

                with open(os.path.join(self.conf['source tree root'],
                                       cc_extra_full_desc_file['cc full desc file'])) as fp:
                    cc_full_desc = json.load(fp)
                # TODO: GCC can accept several input files but who cares?
                if 'plugin aspect files' not in cc_extra_full_desc_file:
                    psi.utils.execute(self.logger,
                                      ('cif',
                                       '--in', cc_full_desc['in files'][0],
                                       '--aspect', '/dev/null',
                                       '--out', cc_full_desc['out file'],
                                       '--back-end', 'src'),
                                      cwd=self.conf['source tree root'])
                extra_c_file['C file'] = cc_full_desc['out file']

                if 'rule spec id' in cc_extra_full_desc_file:
                    extra_c_file['rule spec id'] = cc_extra_full_desc_file['rule spec id']

                if 'bug kinds' in cc_extra_full_desc_file:
                    extra_c_file['bug kinds'] = cc_extra_full_desc_file['bug kinds']

                self.abstract_task_desc['extra C files'].append(extra_c_file)

        # These sections won't be reffered any more.
        del (self.abstract_task_desc['grps'])
        del (self.abstract_task_desc['deps'])

        self.mqs['abstract task description'].put(self.abstract_task_desc)

    main = weave
