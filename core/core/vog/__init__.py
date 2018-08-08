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

import json
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

    def generate_verification_objects(self):
        # Get classes
        source = get_source_adapter(self.conf['project']['name'])
        # strategy = get_division_strategy(self.conf['VOG strategy']['name'])
        divider = get_divider(self.conf['VOG divider']['name'])

        # Create instances
        # strategy = strategy(self.logger, self.conf)
        source = source(self.logger, self.conf)
        if not self.conf['project'].get("clade cache"):
            # Prepare project working source tree and extract build commands exclusively but just with other
            # sub-jobs of a given job. It would be more properly to lock working source trees especially if different
            # sub-jobs use different trees (https://forge.ispras.ru/issues/6647).
            with self.locks['build']:
                self.prepare_and_build(source)
            clade_api.setup(source.clade_dir)
        else:
            clade_dir = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                    self.conf['project']['clade cache'])
            clade_api.setup(clade_dir)

        divider = divider(self.logger, self.conf, source, clade_api)
        a = divider.target_units
        self.common_prj_attrs = source.attributes # + strategy.attributes + divider.attributes
        # todo: After strategies and dividers work we need to delete them or clean up
        # core.utils.report(self.logger,
        #                   'attrs',
        #                   {
        #                       'id': self.id,
        #                       'attrs': self.common_prj_attrs
        #                   },
        #                   self.mqs['report files'],
        #                   self.vals['report id'],
        #                   self.conf['main working directory'])
        # self.generate_all_verification_obj_descs(divider)
        #
        # self.clean_dir = True
        # self.excluded_clean = [d for d in strategy.dynamic_excluded_clean]
        # self.logger.debug("Excluded {0}".format(self.excluded_clean))

    def prepare_and_build(self, adapter):
        self.logger.info("Wait for model headers from VOG")
        model_headers = self.mqs["model headers"].get()
        adapter.configure()
        adapter.build(model_headers)

    def generate_all_verification_obj_descs(self, divider):
        modules = divider._common_divide(self.strategy.get_specific_files(), self.strategy.get_specific_modules())
        self.logger.debug("Modules are {0}".format(json.dumps(modules, indent=4, sort_keys=True)))
        self.strategy.generate_verification_objects(modules)

    # todo: Why does it needed?
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

    main = generate_verification_objects

