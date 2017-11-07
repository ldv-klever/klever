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
import copy
import multiprocessing
import core.utils
import core.components


class PW(core.components.Component):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, locks, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=True, include_child_resources=False, session=None, subjobs_number=None):
        super(PW, self).__init__(conf, logger, parent_id, callbacks, mqs, locks, vals, id, work_dir, attrs,
                                 separate_from_parent, include_child_resources)
        # Initialize shared values and queues
        self.first_task_flag = False
        self.mqs['finished and failed tasks'] = multiprocessing.Queue()
        self.mqs['first task appeared'] = multiprocessing.Queue()
        self.mqs['total tasks'] = multiprocessing.Queue()

        self.subjobs = multiprocessing.Manager().dict()
        self.vals['subjobs progress'] = self.subjobs

        self.session = session
        if subjobs_number:
            self.subjobs_number = subjobs_number
            self.job_mode = False
        else:
            self.subjobs_number = 1
            self.job_mode = True
        self.total_tasks = dict()
        self.failed_tasks = dict()
        self.finished_tasks = dict()
        self.tasks_start_time = None
        self.task_update_time = None
        self.subjobs_update_time = None
        self.subjobs_start_time = time.time()
        self.__subjobs_cache = self.subjobs.copy()
        self.__report_cache = dict()

    def watch_progress(self):
        self.logger.info("Start progress caclulator")

        # Status
        total_tasks_messages = list()
        task_messages = list()
        total_tasks_value = None
        if self.job_mode:
            data_report = {}
        else:
            data_report = {
                "total subjobs to be solved": self.subjobs_number,
                "start subjobs solution": True,
            }

        while True:
            # Drain queue to wait for the whole tasks in background
            core.utils.drain_queue(task_messages, self.mqs['finished and failed tasks'])
            if len(task_messages) > 0:
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
                self.task_update_time = time.time()

            # Drain queue to wait for the whole tasks in background
            if not isinstance(total_tasks_value, int):
                core.utils.drain_queue(total_tasks_messages, self.mqs['total tasks'])
                while len(total_tasks_messages) > 0:
                    job_id, number = total_tasks_messages.pop()
                    self.total_tasks[job_id] = number

            # Check that VTG started taks solution
            core.utils.drain_queue(total_tasks_messages, self.mqs['first task appeared'])
            if len(total_tasks_messages) > 0 and not self.first_task_flag:
                self.logger.info('The first task is submitted, starting the time counter')
                self.tasks_start_time = time.time()
                data_report["start tasks solution"] = True
            total_tasks_messages = []

            # Check subjobs
            if any([True for i in self.subjobs.keys() if i not in self.__subjobs_cache]):
                for job_id in (i for i in self.subjobs.keys() if self.subjobs[i] == 'failed' and
                               i not in self.__subjobs_cache):
                    self.logger.debug("The job {!r} has failed".format(job_id))
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
                # Check solved job
                if any([True for i in self.subjobs.keys()
                        if self.subjobs[i] == 'finished' and i not in self.__subjobs_cache]):
                    self.logger.debug("Set new time as some jobs has been finished")
                    self.subjobs_update_time = time.time()
                self.__subjobs_cache = self.subjobs.copy()

            # Total number of tasks is determined
            if not isinstance(total_tasks_value, int) and len(self.total_tasks.keys()) == self.subjobs_number:
                total_tasks_value = sum(self.total_tasks.values())
                data_report["total tasks to be generated"] = total_tasks_value

            # Calculate time on each report sending on base of all time and the whole numbe of tasks/subjobs
            if isinstance(total_tasks_value, int):
                # Estimate tasks
                solved_tasks = sum((self.finished_tasks[j] for j in self.finished_tasks))
                if solved_tasks > 0:
                    failed_tasks = sum((self.failed_tasks[j] for j in self.failed_tasks))
                    rest_tasks = total_tasks_value - solved_tasks - failed_tasks
                    self.logger.debug("Left to solve {} tasks of {} in total".format(rest_tasks, total_tasks_value))
                    if rest_tasks < 0:
                        raise ValueError("Got negative number of rest tasks, seems some tasks are not accounted")
                    task_estimation = self._estimate_time(self.tasks_start_time, self.task_update_time,
                                                          solved_tasks, rest_tasks)
                    self.logger.debug("Task time estimation: {}s".format(task_estimation))
                    data_report["failed tasks"] = failed_tasks
                    data_report["solved tasks"] = solved_tasks
                    data_report["expected time for solving tasks"] = task_estimation
                    if rest_tasks == 0:
                        data_report["finish tasks solution"] = True

            # Estimate subjobs
            solved_subjobs = len([j for j in self.__subjobs_cache.keys() if self.__subjobs_cache[j] == 'finished'])
            if solved_subjobs > 0 and not self.job_mode:
                failed_subjobs = len([j for j in self.subjobs.keys() if self.__subjobs_cache[j] == 'failed'])
                rest_subjobs = self.subjobs_number - solved_subjobs - failed_subjobs
                subjob_estimation = self._estimate_time(self.subjobs_start_time, self.subjobs_update_time,
                                                        solved_subjobs, rest_subjobs)
                self.logger.debug("Left to solve {} subjobs of {} in total".format(rest_subjobs, self.subjobs_number))
                if rest_subjobs < 0:
                    raise ValueError("Got negative number of rest subjobs, seems some subjobs are not accounted")
                self.logger.debug("Subjobs time estimation: {}s".format(subjob_estimation))
                data_report["failed subjobs"] = failed_subjobs
                data_report["solved subjobs"] = solved_subjobs
                data_report["expected time for solving subjobs"] = subjob_estimation
                if rest_subjobs == 0:
                    data_report["finish subjobs solution"] = True

            # Send report
            self._send_report(data_report)

            if (not self.job_mode and len(self.__subjobs_cache.keys()) == self.subjobs_number) or \
                    (self.job_mode and isinstance(total_tasks_value, int) and rest_tasks == 0):
                break
            time.sleep(10)
        self.logger.info("Finish progress calculation")

    main = watch_progress

    def _estimate_time(self, start_time, update_time, solved, rest):
        def f():
            return round((rest / solved) * last_update_time - delta_time)

        if rest > 0:
            delta_time = round(time.time() - update_time)
            last_update_time = round(update_time - start_time)
            estimation = f()
            if estimation < 0:
                self.logger.info("Adjust time estimation including already elapsed time from the last update")
                last_update_time += delta_time
                estimation = f()
                if estimation < 0:
                    raise ValueError("Got negative time estimation: {} "
                                     "with the follwoing values: update time: {}, delta: {}, solved: {}, rest: {}".
                                     format(estimation, last_update_time, delta_time, solved, rest))
            return estimation
        else:
            return 0

    def _send_report(self, report):
        send_report = False
        new_report = dict()

        def check_new_field(name):
            if name not in self.__report_cache and name in report:
                new_report[name] = report[name]
                return True
            else:
                return False

        # Send when appears total tasks, start tasks solution, end task solution, total subjobs and start solution
        for prop in ["total subjobs to be solved", "start subjobs solution", "finish subjobs solution",
                     "total tasks to be generated", "start tasks solution", "finish tasks solution"]:
            hit = check_new_field(prop)
            send_report += hit
            if hit and prop in ["start tasks solution", "finish tasks solution",
                                "finish subjobs solution", "start subjobs solution"]:
                # Do not send it repeatedly
                del report[prop]

        # Check that we can calculate progress and it has changed
        for kind in ["tasks", "subjobs"]:
            exp_key = "expected time for solving {}".format(kind)
            if check_new_field(exp_key):
                send_report += True
            elif exp_key in self.__report_cache:
                percent = self.__report_cache[exp_key] / 100
                diff = abs(self.__report_cache[exp_key] - report[exp_key])
                if (diff != 0 and diff > percent) or (self.__report_cache[exp_key] != 0 and report[exp_key] == 0):
                    send_report += True
                    new_report[exp_key] = report[exp_key]
            if exp_key in new_report:
                for i in ["failed {}".format(kind), "solved {}".format(kind)]:
                    new_report[i] = report[i]

        if send_report:
            self.logger.info("Sending progress report")
            self.session.submit_progress(new_report)
            self.__report_cache = copy.copy(report)