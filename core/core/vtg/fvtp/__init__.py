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

import importlib

import core.vtg.plugins


class FVTP(core.vtg.plugins.Plugin):
    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False):
        super(FVTP, self).__init__(conf, logger, parent_id, callbacks, mqs, vals, id, work_dir, attrs,
                                   separate_from_parent, include_child_resources)

    def final_task_preparation(self):
        """
        Main routine of the component. It prepares a number of verification tasks and submit them to Bridge and the VRP
        component.

        :return: None
        """

        if 'strategy' in self.conf:
            strategy_name = self.conf['strategy']
        else:
            strategy_name = 'basic'

        self.logger.info("Going to use strategy {!r} to generate verification tasks".format(strategy_name))
        try:
            strategy = getattr(importlib.import_module('.{0}'.format(strategy_name.lower()), 'core.vtg.fvtp'),
                               strategy_name.capitalize())
        except ImportError:
            raise ValueError("There is no strategy {!r}".format(strategy_name))

        self.logger.info('Initialize strategy {!r}'.format(strategy_name))
        s = strategy(self.logger, self.conf, self.abstract_task_desc)

        self.logger.info('Begin task generating')
        s.generate_verification_task()

        # Prepare final abstract verification task
        self.abstract_task_desc['verifier'] = self.conf['verifier']['name']
        self.abstract_task_desc["result processing"] = {'code coverage details': self.conf['code coverage details']}

        # Specific requirement specification settings can complement or/and overwrite common ones.
        if 'result processing' in self.conf:
            self.abstract_task_desc["result processing"].update(self.conf["result processing"])

    main = final_task_preparation

