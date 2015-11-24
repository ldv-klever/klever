#!/usr/bin/python3

import json
import os

import psi.components
import psi.utils


class ASG(psi.components.Component):
    def generate_argument_signatures(self):
        self.abstract_task_desc = self.mqs['abstract task description'].get()

        self.request_arg_signs()

        self.mqs['abstract task description'].put(self.abstract_task_desc)

    def request_arg_signs(self):
        self.logger.info('Request argument signatures')

        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Request argument signatures for C files of group "{0}"'.format(grp['id']))

            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                with open(os.path.join(self.conf['source tree root'],
                                       cc_extra_full_desc_file['cc full desc file'])) as fp:
                    cc_full_desc = json.load(fp)

                self.logger.info('Request argument signatures for C file "{0}"'.format(cc_full_desc['in files'][0]))

                request_aspect = psi.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                            os.path.join(self.conf['request aspects directory'],
                                                                         self.conf['request aspect']))
                self.logger.debug('Request aspect is "{0}"'.format(request_aspect))

                # This is required to get compiler (Aspectator) specific stdarg.h since kernel C files are compiled with
                # "-nostdinc" option and system stdarg.h couldn't be used.
                stdout = psi.utils.execute(self.logger,
                                           ('aspectator', '-print-file-name=include'),
                                           collect_all_stdout=True)
                env = dict(os.environ)
                env['LDV_ARG_SIGNS_FILE'] = os.path.relpath('arg signs',
                                                            os.path.realpath(self.conf['source tree root']))
                psi.utils.execute(self.logger,
                                  tuple(['cif',
                                         '--in', cc_full_desc['in files'][0],
                                         '--aspect', os.path.relpath(request_aspect,
                                                                     os.path.realpath(self.conf['source tree root'])),
                                         '--stage', 'instrumentation',
                                         '--out', os.path.relpath('arg signs.c',
                                                                  os.path.realpath(self.conf['source tree root'])),
                                         '--debug', 'DEBUG',
                                         '--keep-prepared-file'] +
                                        (['--keep'] if self.conf['debug'] else []) +
                                        ['--'] +
                                        cc_full_desc['opts'] +
                                        ['-I{0}'.format(stdout[0])]),
                                  env,
                                  self.conf['source tree root'])

    main = generate_argument_signatures
