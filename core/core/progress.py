#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
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
import time
import multiprocessing
import core.utils
import core.components


class PW(core.components.Component):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, locks, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=True, include_child_resources=False, subjobs_number=None):
        super(PW, self).__init__(conf, logger, parent_id, callbacks, mqs, locks, vals, id, work_dir, attrs,
                                 separate_from_parent, include_child_resources)
        # Initialize shared values and queues
        self.first_task_flag = multiprocessing.Value('i', 0)

        self.mqs['finished and failed tasks'] = multiprocessing.Queue()
        self.mqs['total tasks'] = multiprocessing.Queue()
        self.vals['first task is generated'] = self.first_task_flag

        self.subjobs = multiprocessing.Manager().dict()
        self.vals['subjobs progress'] = self.subjobs

        self.subjobs_number = subjobs_number
        self.total_tasks = dict()
        self.failed_tasks = dict()
        self.finished_tasks = dict()
        self.start_time = None
        self.subjobs_copy = self.subjobs.copy()
        self.very_start_time = time.time()

    def watch_progress(self):
        self.logger.info("Start progress caclulator")

        # Status
        total_tasks_messages = list()
        task_messages = list()
        total_tasks_value = None

        while True:
            self.logger.info("tasks {}\n {}\n {}".format(str(self.total_tasks), str(self.finished_tasks),
                                                         str(self.failed_tasks)))
            self.logger.info("Job {}".format(str(self.subjobs_copy)))
            # Drain queue to wait for the whole tasks in background
            core.utils.drain_queue(task_messages, self.mqs['finished and failed tasks'])
            while len(task_messages) > 0:
                job_id, status = task_messages.pop()
                if job_id not in self.finished_tasks:
                    self.finished_tasks[job_id] = 0
                if job_id not in self.failed_tasks:
                    self.failed_tasks[job_id] = 0
                if status == 'finished':
                    self.finished_tasks[job_id] += 1
                elif status == 'failed':
                    self.failed_tasks[job_id] += 1
                else:
                    raise ValueError('Unknown status {!r} received from subjob {!r}'.format(status, job_id))

            # Drain queue to wait for the whole tasks in background
            if not isinstance(total_tasks_value, int):
                core.utils.drain_queue(total_tasks_messages, self.mqs['total tasks'])
                while len(total_tasks_messages) > 0:
                    job_id, number = total_tasks_messages.pop()
                    self.total_tasks[job_id] = number

            # Check failed subjobs
            for job_id in (i for i in self.subjobs.keys() if self.subjobs[i] == 'failed' and
                           i not in self.subjobs_copy):
                if job_id in self.total_tasks:
                    number = self.total_tasks[job_id] - \
                             (self.finished_tasks[job_id] if job_id in self.finished_tasks else 0) - \
                             (self.failed_tasks[job_id] if job_id in self.failed_tasks else 0)
                    if job_id not in self.finished_tasks:
                        self.finished_tasks[job_id] = 0
                    if job_id not in self.failed_tasks:
                        self.failed_tasks[job_id] = number
                    else:
                        self.failed_tasks[job_id] += number
                else:
                    total = (self.finished_tasks[job_id] if job_id in self.finished_tasks else 0) + \
                            (self.failed_tasks[job_id] if job_id in self.failed_tasks else 0)
                    # Estimate it as summ of already reaceived tasks
                    self.total_tasks[job_id] = total

            # Total number of tasks is determined
            if not isinstance(total_tasks_value, int) and len(self.total_tasks.keys()) == self.subjobs_number:
                total_tasks_value = sum(self.total_tasks.values())

            # wait until first task will be submitted after that start time counter
            if self.first_task_flag.value and not self.start_time:
                self.logger.info('The first task is submitted, starting the time counter')
                self.start_time = time.time()

            # Calculate time on each report sending on base of all time and the whole numbe of tasks/subjobs
            if isinstance(total_tasks_value, int):
                # Estimate tasks
                elapsed = round(time.time() - self.start_time)
                solved_tasks = sum((self.finished_tasks[j] for j in self.finished_tasks))
                failed_tasks = sum((self.failed_tasks[j] for j in self.failed_tasks))
                rest_tasks = total_tasks_value - solved_tasks - failed_tasks
                avr_for_task = round(elapsed / solved_tasks)
                task_estimation = avr_for_task * rest_tasks
                self.logger.debug("Left to solve {} tasks of {} in total".format(rest_tasks, total_tasks_value))
                self.logger.debug("Task time estimation: {}s".format(task_estimation))

            # Estimate subjobs
            solved_subjobs = len([j for j in self.subjobs.keys() if self.subjobs[j] == 'finished'])
            if solved_subjobs > 0:
                elapsed = round(time.time() - self.very_start_time)
                failed_subjobs = len([j for j in self.subjobs.keys() if self.subjobs[j] == 'failed'])
                rest_subjobs = self.subjobs_number - solved_subjobs - failed_subjobs
                avr_for_subjob = round(elapsed / solved_subjobs)
                subjob_estimation = avr_for_subjob * rest_subjobs
                self.logger.debug("Left to solve {} subjobs of {} in total".format(rest_subjobs, self.subjobs_number))
                self.logger.debug("Subjobs time estimation: {}s".format(subjob_estimation))

            if len(self.subjobs.keys()) == self.subjobs_number:
                # todo: Send final report
                break

            self.subjobs_copy = self.subjobs.copy()
            time.sleep(5)

        self.logger.info("Finish progress calculation")
        # todo: each time slot check how many tasks/subjobs solved
        # todo: start sending reports if at least one task or subjob solved
        # todo: send a report when we will get total number of tasks
        # todo: send a report when we will get total number of subjobs

    main = watch_progress





