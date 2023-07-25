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

import time
import os
import shutil

from klever.scheduler import schedulers
import klever.scheduler.schedulers.native
from klever.scheduler import utils


class Debug(klever.scheduler.schedulers.native.Native):
    """
    Implement the scheduler which is used for debugging and prepares jobs but runs nothing.
    """

    def _prepare_solution(self, identifier, configuration, mode='task'):
        """
        Do what usually Native Scheduler does but instead of worker use a sleeping process in case of Job.

        :param identifier: Job or task identifier.
        :param configuration: A dictionary with a configuration or description.
        :param mode: 'task' or 'job'.
        :raise SchedulerException: Raised if the preparation fails and task or job cannot be scheduled.
        """
        original_executor = self._process_starter
        if mode == 'job':
            self._process_starter = self._fake_starter
        super()._prepare_solution(identifier, configuration, mode)
        if mode == 'job':
            self._process_starter = original_executor
        self.logger.warning('You should start Klever Core yourself (most likely in the debug mode)')

    def _postprocess_solution(self, identifier, future, mode):
        """
        Mark resources as released, clean the working directory.

        :param identifier: A job or task identifier
        :param mode: 'task' or 'job'.
        :raise SchedulerException: Raised if an exception occurred during the solution or if results are inconsistent.
        """
        if mode == 'task':
            subdir = 'tasks'
            del self._task_processes[identifier]
        else:
            subdir = 'jobs'
            del self._job_processes[identifier]
        # Mark resources as released
        del self._reserved[subdir][identifier]

        # Include logs into total scheduler logs
        work_dir = os.path.join(self.work_dir, subdir, identifier)

        # Release resources
        if "keep working directory" in self.conf["scheduler"] and self.conf["scheduler"]["keep working directory"]:
            reserved_space = utils.dir_size(work_dir)
        else:
            reserved_space = 0

        self.logger.debug('Yielding result of a future object of {} {}'.format(mode, identifier))
        try:
            if future:
                self._manager.release_resources(identifier, self._node_name, mode == 'job',
                                                reserved_space)
                result = future.result()
                if result != 0:
                    msg = "Work has been interrupted"
                    self.logger.warning(msg)
                    raise schedulers.SchedulerException(msg)
            else:
                self.logger.debug("Seems that {} {} has not been started".format(mode, identifier))
        except Exception as err:
            error_msg = "Execution of {} {} terminated with an exception: {}".format(mode, identifier, err)
            self.logger.warning(error_msg)
            raise schedulers.SchedulerException(error_msg)
        finally:
            # Clean working directory
            if "keep working directory" not in self.conf["scheduler"] or \
                    not self.conf["scheduler"]["keep working directory"]:
                self.logger.debug("Clean task working directory {} for {}".format(work_dir, identifier))
                shutil.rmtree(work_dir)

        return "FINISHED"

    @staticmethod
    def _fake_starter(args, timeout):  # pylint:disable=unused-argument
        while True:
            time.sleep(2)
