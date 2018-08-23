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
import multiprocessing
import clade.interface as clade_api

from core.vog.dividers import get_divider
from core.vog.strategies import get_division_strategy
from core.vog.source import get_source_adapter

import core.components
import core.utils


@core.components.before_callback
def __launch_sub_job_components(context):
    context.mqs['model headers'] = multiprocessing.Queue()


@core.components.after_callback
def __set_model_headers(context):
    context.mqs['model headers'].put(context.model_headers)


class VOG(core.components.Component):

    VO_FILE = 'verification_objects.json'

    def generate_verification_objects(self):
        # Get classes
        program = get_source_adapter(self.conf['project']['name'])
        divider = get_divider(self.conf['VOG divider']['name'])
        strategy = get_division_strategy(self.conf['VOG strategy']['name'])

        # Create instances
        program = program(self.logger, self.conf)
        if not self.conf['Clade']["is base cached"]:
            # Prepare project working source tree and extract build commands exclusively but just with other
            # sub-jobs of a given job. It would be more properly to lock working source trees especially if different
            # sub-jobs use different trees (https://forge.ispras.ru/issues/6647).
            with self.locks['build']:
                self.prepare_and_build(program)
        clade_api.setup(self.conf['Clade']["base"])

        divider = divider(self.logger, self.conf, program, clade_api)
        strategy = strategy(self.logger, self.conf, divider)
        self.common_prj_attrs = program.attributes + strategy.attributes + divider.attributes
        self.source_paths = program.source_paths
        self.submit_project_attrs()

        # Generate verification objects
        verification_objects_files = strategy.generate_verification_objects()
        self.prepare_descriptions_file(verification_objects_files)
        self.clean_dir = True
        self.excluded_clean = [d for d in strategy.dynamic_excluded_clean]
        self.logger.debug("Excluded {0}".format(self.excluded_clean))

    main = generate_verification_objects

    def submit_project_attrs(self):
        """Has a callback!"""
        core.utils.report(self.logger,
                          'attrs',
                          {
                              'id': self.id,
                              'attrs': self.common_prj_attrs
                          },
                          self.mqs['report files'],
                          self.vals['report id'],
                          self.conf['main working directory'])

    def prepare_and_build(self, program):
        self.logger.info("Wait for model headers from VOG")
        model_headers = self.mqs["model headers"].get()
        program.prepare_build_directory()
        program.configure()
        if model_headers:
            program.prepare_model_headers(model_headers)
        program.build()

    def prepare_descriptions_file(self, files):
        """Has a callback!"""
        with open(self.VO_FILE, 'w') as fp:
            fp.writelines((os.path.relpath(f, self.conf['main working directory']) + '\n' for f in files))

    # todo: Why does it needed? Maybe wee need to apload data attributes with units instead
    # def send_loc_report(self):
    #     core.utils.report(self.logger,
    #                       'data',
    #                       {
    #                           'id': self.id,
    #                           'data': self.loc
    #                       },
    #                       self.mqs['report files'],
    #                       self.vals['report id'],
    #                       self.conf['main working directory'])

