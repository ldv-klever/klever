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
                 separate_from_parent=True, include_child_resources=False, session=None, total_subjobs=None):
        super(PW, self).__init__(conf, logger, parent_id, callbacks, mqs, locks, vals, id, work_dir, attrs,
                                 separate_from_parent, include_child_resources)
        # Initialize shared values and queues
        self.mqs['finished and failed tasks'] = multiprocessing.Queue()
        self.mqs['total tasks'] = multiprocessing.Queue()
        self.first_task_flag = multiprocessing.Value('i', 0)
        self.vals['task solving flag'] = self.first_task_flag
        self.subjobs = multiprocessing.Manager().dict()
        self.vals['subjobs progress'] = self.subjobs

        self.session = session
        if total_subjobs:
            self.subjobs_number = total_subjobs
            self.job_mode = False
        else:
            self.subjobs_number = 1
            self.job_mode = True
        self.total_tasks_data = dict()
        self.failed_tasks_data = dict()
        self.finished_tasks_data = dict()
        self.subjobs_cache = self.subjobs.copy()
        self.report_cache = dict()
        self.cached_tasks_progress = None
        self.cached_subjobs_progress = None

    @property
    def solved_subjobs(self):
        return len([j for j in self.subjobs_cache.keys() if self.subjobs_cache[j] == 'finished'])

    @property
    def failed_subjobs(self):
        return len([j for j in self.subjobs_cache.keys() if self.subjobs_cache[j] == 'failed'])

    @property
    def solved_tasks(self):
        return sum((self.finished_tasks_data[j] for j in self.finished_tasks_data))

    @property
    def failed_tasks(self):
        return sum((self.failed_tasks_data[j] for j in self.failed_tasks_data))

    @property
    def total_tasks(self):
        if len(self.total_tasks_data.keys()) == self.subjobs_number:
            return sum(self.total_tasks_data.values())
        else:
            return None

    @property
    def rest_tasks(self):
        t = self.total_tasks
        if t:
            return t - self.solved_tasks - self.failed_tasks
        else:
            return None

    @property
    def rest_subjobs(self):
        return self.subjobs_number - self.solved_subjobs - self.failed_subjobs

    @property
    def tasks_progress(self):
        if isinstance(self.total_tasks, int) and self.failed_tasks != self.total_tasks:
            return round(100 * self.solved_tasks / (self.total_tasks - self.failed_tasks))
        elif isinstance(self.total_tasks, int) and self.failed_tasks == self.total_tasks:
            return 100
        else:
            return None

    @property
    def subjobs_progress(self):
        if not self.job_mode and self.failed_subjobs != self.subjobs_number:
            return round(100 * self.solved_subjobs / (self.subjobs_number - self.failed_subjobs))
        elif self.job_mode and self.failed_subjobs == self.subjobs_number:
            return 100
        else:
            return None

    def watch_progress(self):
        self.logger.info("Start progress caclulator")
        tasks_start_time = None
        task_update_time = None
        subjobs_update_time = None
        subjobs_start_time = time.time()
        first_task_appeared = False
        total_tasks_determined = False
        total_tasks_messages = list()
        task_messages = list()
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
                    if job_id not in self.finished_tasks_data:
                        self.finished_tasks_data[job_id] = 0
                    if job_id not in self.failed_tasks_data:
                        self.failed_tasks_data[job_id] = 0
                    if status == 'finished':
                        self.finished_tasks_data[job_id] += 1
                    elif status == 'failed':
                        self.failed_tasks_data[job_id] += 1
                    else:
                        raise ValueError('Unknown status {!r} received from subjob {!r}'.format(status, job_id))
                task_update_time = time.time()

            # Drain queue to wait for the whole tasks in background
            if not isinstance(self.total_tasks, int):
                core.utils.drain_queue(total_tasks_messages, self.mqs['total tasks'])
                while len(total_tasks_messages) > 0:
                    job_id, number = total_tasks_messages.pop()
                    self.total_tasks_data[job_id] = number

            # Check that VTG started taks solution
            if self.first_task_flag.value and not first_task_appeared:
                self.logger.info('The first task is submitted, starting the time counter')
                data_report["start tasks solution"] = True
                first_task_appeared = True
                tasks_start_time = time.time()

            # Total number of tasks is determined
            if isinstance(self.total_tasks, int) and not total_tasks_determined:
                data_report["total tasks to be generated"] = self.total_tasks
                total_tasks_determined = True

            # Check subjobs
            if any([True for i in self.subjobs.keys() if i not in self.subjobs_cache]):
                for job_id in (i for i in self.subjobs.keys() if self.subjobs[i] == 'failed' and
                               i not in self.subjobs_cache):
                    self.logger.debug("The job {!r} has failed".format(job_id))
                    if job_id in self.total_tasks_data:
                        number = self.total_tasks_data[job_id] - \
                                 (self.finished_tasks_data[job_id] if job_id in self.finished_tasks_data else 0) - \
                                 (self.failed_tasks_data[job_id] if job_id in self.failed_tasks_data else 0)
                        if job_id not in self.finished_tasks_data:
                            self.finished_tasks_data[job_id] = 0
                        if job_id not in self.failed_tasks_data:
                            self.failed_tasks_data[job_id] = number
                        else:
                            self.failed_tasks_data[job_id] += number
                    else:
                        total = (self.finished_tasks_data[job_id] if job_id in self.finished_tasks_data else 0) + \
                                (self.failed_tasks_data[job_id] if job_id in self.failed_tasks_data else 0)
                        # Estimate it as summ of already reaceived tasks
                        self.total_tasks_data[job_id] = total
                # Check solved job
                if any([True for i in self.subjobs.keys()
                        if self.subjobs[i] == 'finished' and i not in self.subjobs_cache]):
                    self.logger.debug("Set new time as some jobs has been finished")
                    subjobs_update_time = time.time()
                self.subjobs_cache = self.subjobs.copy()

            # Calculate time on each report sending on base of all time and the whole numbe of tasks/subjobs
            if isinstance(self.total_tasks, int) and self.solved_tasks > 0:
                self.logger.debug("Left to solve {} tasks of {} in total".format(self.rest_tasks, self.total_tasks))
                task_estimation = self._estimate_time(tasks_start_time, task_update_time,
                                                      self.solved_tasks, self.rest_tasks, self.tasks_progress)
                data_report["failed tasks"] = self.failed_tasks
                data_report["solved tasks"] = self.solved_tasks
                data_report["expected time for solving tasks"] = task_estimation
                if self.tasks_progress == 100:
                    data_report["finish tasks solution"] = True

            # Estimate subjobs
            if not self.job_mode and self.solved_subjobs > 0:
                subjob_estimation = self._estimate_time(subjobs_start_time, subjobs_update_time,
                                                        self.solved_subjobs, self.rest_subjobs, self.subjobs_progress)
                self.logger.debug("Left to solve {} subjobs of {} in total".format(self.rest_subjobs,
                                                                                   self.subjobs_number))
                data_report["failed subjobs"] = self.failed_subjobs
                data_report["solved subjobs"] = self.solved_subjobs
                data_report["expected time for solving subjobs"] = subjob_estimation
                if self.subjobs_progress == 100:
                    data_report["finish subjobs solution"] = True

            # Send report
            self._send_report(data_report)

            if (not self.job_mode and len(self.subjobs_cache.keys()) == self.subjobs_number) or \
                    (self.job_mode and isinstance(self.total_tasks, int) and self.rest_tasks == 0):
                break
            time.sleep(10)
        self.logger.info("Finish progress calculation")

    main = watch_progress

    def _estimate_time(self, start_time, update_time, solved, rest, progress):
        def formula():
            delta_time = round(time.time() - update_time)
            last_update_time = round(update_time - start_time)
            return round((rest / solved) * last_update_time - delta_time)

        if progress <= 10:
            ret = 'Estimating time'
        elif 10 < progress <= 90:
            ret = formula()
            if ret < 0 or ret == 0:
                ret = "Reestimating time"
        elif 90 < progress < 100:
            ret = formula()
            if ret < 0 or ret == 0:
                ret = "Solution is about to finish"
        else:
            ret = 0

        self.logger.info("Solution progress: {}, time estimation: {}".format(progress, ret))
        return ret

    def _send_report(self, report):
        send_report = False
        new_report = dict()

        def check_new_field(name):
            if name not in self.report_cache and name in report:
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
            # Check time
            exp_key = "expected time for solving {}".format(kind)
            if (exp_key in report and isinstance(report[exp_key], str) and
                    ((exp_key in self.report_cache and self.report_cache[exp_key] != report[exp_key]) or
                     exp_key not in self.report_cache)):
                send_report += True
            # Set it here anyway but it is possible we will not send it
            if exp_key in report:
                new_report[exp_key] = report[exp_key]

            # Check progress
            exp_key = "solved {}".format(kind)
            if exp_key in self.report_cache:
                cached = self.__getattribute__('cached_{}_progress'.format(kind))
                percent = self.__getattribute__('{}_progress'.format(kind))
                if not cached or abs(cached - percent) > 1:
                    send_report += True
                    for i in ["failed {}".format(kind), "solved {}".format(kind)]:
                        if i in report:
                            new_report[i] = report[i]
            elif exp_key in report:
                send_report += True
                for i in ["failed {}".format(kind), "solved {}".format(kind)]:
                    if i in report:
                        new_report[i] = report[i]

        if send_report:
            self.logger.info("Sending progress report: {}".format(str(new_report)))
            self.session.submit_progress(new_report)
            self.report_cache = copy.copy(report)