#!/usr/bin/python3

import fileinput
import json
import os

import psi.components
import psi.utils


class Weaver(psi.components.Component):
    def weave(self):
        self.abstract_task_desc = self.mqs['abstract task description'].get()

        self.abstract_task_desc['extra C files'] = []

        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Weave in C files of group "{0}"'.format(grp['id']))

            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                extra_c_file = {}

                with open(os.path.join(self.conf['source tree root'],
                                       cc_extra_full_desc_file['cc full desc file'])) as fp:
                    cc_full_desc = json.load(fp)

                # Produce aspect to be weaved in.
                aspect = None
                if 'plugin aspect files' in cc_extra_full_desc_file:
                    # Concatenate all aspects of all plugins together.
                    aspect = os.path.join(self.conf['source tree root'], '{}.aspect'.format(
                        os.path.splitext(cc_full_desc['out file'])[0]))
                    with open(aspect, 'w') as fout, fileinput.input(
                            [os.path.join(self.conf['main working directory'], aspect) for plugin_aspect_files
                             in cc_extra_full_desc_file['plugin aspect files'] for aspect in
                             plugin_aspect_files['aspect files']]) as fin:
                        for line in fin:
                            fout.write(line)
                else:
                    aspect = '/dev/null'
                self.logger.debug('Aspect to be weaved in is "{0}"'.format(aspect))

                stdout = psi.utils.execute(self.logger,
                                           ('aspectator', '-print-file-name=include'),
                                           collect_all_stdout=True)
                psi.utils.execute(self.logger, tuple(['cif',
                                                      '--in', cc_full_desc['in files'][0],
                                                      '--aspect', aspect,
                                                      '--out', cc_full_desc['out file'],
                                                      '--back-end', 'src',
                                                      '--'] +
                                                     cc_full_desc['opts'] +
                                                     ['-I{0}'.format(stdout[0])]),
                                  cwd=self.conf['source tree root'])
                extra_c_file['C file'] = cc_full_desc['out file']
                self.logger.debug('C file "{0}" was weaved in'.format(extra_c_file['C file']))

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
