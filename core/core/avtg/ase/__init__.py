#!/usr/bin/python3

import json
import os

import core.components
import core.utils


class ASE(core.components.Component):
    def extract_argument_signatures(self):
        self.abstract_task_desc = self.mqs['abstract task description'].get()

        self.request_arg_signs()

        arg_signs = []

        if os.path.isfile('arg signs'):
            self.logger.info('Process obtained argument signatures from file "arg signs"')
            # We could obtain the same argument signatures, so remove duplicates.
            with open('arg signs', encoding='ascii') as fp:
                arg_signs = set(fp.read().splitlines())
            self.logger.debug('Obtain following argument signatures "{0}"'.format(arg_signs))

        # Convert each argument signature (that is represented as C identifier) into:
        # * the same identifier but with leading "_" for concatenation with other identifiers ("_" allows to separate
        #   these idetifiers visually more better in rendered templates, while in original templates they are already
        #   separated quite well by template syntax, besides, we can generate models and aspects without agrument
        #   signatures at all on the basis of the same templates)
        # * more nice text representation for notes to be shown to users.
        self.abstract_task_desc['template context'] = {
            self.conf['argument signatures list']:
                [{'id': '_{0}'.format(arg_sign), 'text': ' "{0}"'.format(arg_sign)} for arg_sign in arg_signs]
                if arg_signs else [{'id': '', 'text': ''}],
            'arg_signs': ['_$arg_sign{0}'.format(i) if arg_signs else '' for i in range(10)]
        }

        self.mqs['abstract task description'].put(self.abstract_task_desc)

    def request_arg_signs(self):
        self.logger.info('Request argument signatures')

        if 'request aspect' not in self.conf:
            self.logger.debug('Argument signatures were not requested since request aspect is not specified')
            return

        request_aspect = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                     self.conf['request aspect'])
        self.logger.debug('Request aspect is "{0}"'.format(request_aspect))

        # This is required to get compiler (Aspectator) specific stdarg.h since kernel C files are compiled with
        # "-nostdinc" option and system stdarg.h couldn't be used.
        gcc_search_dir = '-isystem{0}'.format(
            core.utils.execute(self.logger, ('aspectator', '-print-file-name=include'), collect_all_stdout=True)[0])

        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Request argument signatures for C files of group "{0}"'.format(grp['id']))

            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                with open(
                        os.path.join(self.conf['main working directory'], cc_extra_full_desc_file['cc full desc file']),
                        encoding='ascii') as fp:
                    cc_full_desc = json.load(fp)

                self.logger.info('Request argument signatures for C file "{0}"'.format(cc_full_desc['in files'][0]))

                env = dict(os.environ)
                env['LDV_ARG_SIGNS_FILE'] = os.path.relpath('arg signs',
                                                            os.path.join(self.conf['main working directory'],
                                                                         cc_full_desc['cwd']))
                core.utils.execute(self.logger,
                                   tuple(['cif',
                                          '--in', cc_full_desc['in files'][0],
                                          '--aspect', os.path.relpath(request_aspect,
                                                                      os.path.join(self.conf['main working directory'],
                                                                                   cc_full_desc['cwd'])),
                                          '--stage', 'instrumentation',
                                          '--out', os.path.relpath('arg signs.c',
                                                                   os.path.join(self.conf['main working directory'],
                                                                                cc_full_desc['cwd'])),
                                          '--debug', 'DEBUG'] +
                                         (['--keep'] if self.conf['keep intermediate files'] else []) +
                                         ['--'] +
                                         [opt.replace('"', '\\"') for opt in cc_full_desc['opts']] +
                                         [gcc_search_dir]),
                                   env,
                                   os.path.relpath(os.path.join(self.conf['main working directory'],
                                                                cc_full_desc['cwd'])))

    main = extract_argument_signatures
