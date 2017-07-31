#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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

import multiprocessing
import core.components
import core.utils
from core.vtgvrp.vtg import VTG
from core.vtgvrp.vrp import VRP


@core.utils.before_callback
def __launch_sub_job_components(context):
    context.mqs['VTGVRP common prj attrs'] = multiprocessing.Queue()


@core.utils.after_callback
def __set_common_prj_attrs(context):
    context.mqs['VTGVRP common prj attrs'].put(context.common_prj_attrs)


@core.utils.propogate_callbacks
def propogate_vtg_and_vrp_callbacks(conf, logger):
    logger.info('Get VTG and VRP callbacks')

    # todo: add VRP
    subcomponents = [vtg.VTG]
    return core.utils.get_component_callbacks(logger, subcomponents, conf)


class VTGVRP(core.components.Component):

    def main_routine(self):
        # todo: fix or rewrite
        # self.abstract_task_desc_num = 0
        # self.failed_abstract_task_desc_num = multiprocessing.Value('i', 0)
        # self.abstract_task_descs_num = multiprocessing.Value('i', 0)
        # Tasks waiting for solution
        self.mqs['VTGVRP pending tasks'] = multiprocessing.Queue()

        # core.utils.report(self.logger,
        #                   'attrs',
        #                   {
        #                       'id': self.id,
        #                       'attrs': self.__get_common_prj_attrs()
        #                   },
        #                   self.mqs['report files'],
        #                   self.conf['main working directory'])

        tg = VTG(self.conf, self.logger, self.id, self.callbacks, self.mqs, self.locks, separate_from_parent=True)
        rp = VRP(self.conf, self.logger, self.id, self.callbacks, self.mqs, self.locks, separate_from_parent=True)
        tg.start()
        rp.start()
        tg.join()
        rp.join()

    main = main_routine

    def __get_common_prj_attrs(self):
        self.logger.info('Get common project atributes')

        common_prj_attrs = self.mqs['VTGVRP common prj attrs'].get()

        self.mqs['VTGVRP common prj attrs'].close()

        return common_prj_attrs

    # todo: fix or reimplement
    # def evaluate_abstract_verification_task_descs_num(self):
    #     self.logger.info('Get the total number of verification object descriptions')
    #
    #     verification_obj_descs_num = self.mqs['verification obj descs num'].get()
    #
    #     self.mqs['verification obj descs num'].close()
    #
    #     self.logger.debug('The total number of verification object descriptions is "{0}"'.format(
    #         verification_obj_descs_num))
    #
    #     self.abstract_task_descs_num.value = verification_obj_descs_num * len(self.rule_spec_descs)
    #
    #     self.logger.info(
    #         'The total number of abstract verification task descriptions to be generated in ideal is "{0}"'.format(
    #             self.abstract_task_descs_num.value))
    #
    #     core.utils.report(self.logger,
    #                       'data',
    #                       {
    #                           'id': self.id,
    #                           'data': {
    #                               'total number of abstract verification task descriptions to be generated in ideal':
    #                                   self.abstract_task_descs_num.value
    #                           }
    #                       },
    #                       self.mqs['report files'],
    #                       self.conf['main working directory'])


