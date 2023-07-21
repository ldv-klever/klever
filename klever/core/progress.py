#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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
import copy
import multiprocessing
import klever.core.utils
import klever.core.components


class PW(klever.core.components.Component):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, cur_id=None, work_dir=None, attrs=None,
                 separate_from_parent=True, include_child_resources=False, total_subjobs=None):
        super().__init__(conf, logger, parent_id, callbacks, mqs, vals, cur_id, work_dir, attrs,
                                 separate_from_parent, include_child_resources)
        # Initialize shared values and queues
        self.mqs['finished and failed tasks'] = multiprocessing.Queue()
        self.mqs['total tasks'] = multiprocessing.Queue()
        self.first_task_flag = multiprocessing.Value('i', 0)
        self.vals['task solving flag'] = self.first_task_flag
        self.subjobs = multiprocessing.Manager().dict()
        self.vals['subjobs progress'] = self.subjobs
        self.session = klever.core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])
        if total_subjobs:
            self.subjobs_number = total_subjobs
            self.job_mode = False
        else:
            self.subjobs_number = 1
            self.job_mode = True
        self.total_tasks_data = {}
        self.failed_tasks_data = {}
        self.finished_tasks_data = {}
        self.subjobs_cache = {}
        self.report_cache = {}
        self.cached_tasks_progress = None
        self.cached_subjobs_progress = None

    @property
    def solved_subjobs(self):
        return len([j for j, stat in self.subjobs_cache.items() if stat == 'finished'])

    @property
    def failed_subjobs(self):
        return len([j for j, stat in self.subjobs_cache.items() if stat == 'failed'])

    @property
    def solved_tasks(self):
        return sum((data for data in self.finished_tasks_data.values()))

    @property
    def failed_tasks(self):
        return sum((data for data in self.failed_tasks_data.values()))

    @property
    def total_tasks(self):
        if len(self.total_tasks_data.keys()) == self.subjobs_number:
            return sum(self.total_tasks_data.values())

        return None

    @property
    def rest_tasks(self):
        t = self.total_tasks
        if t:
            return t - self.solved_tasks - self.failed_tasks

        return None

    @property
    def rest_subjobs(self):
        return self.subjobs_number - self.solved_subjobs - self.failed_subjobs

    @property
    def tasks_progress(self):
        if isinstance(self.total_tasks, int) and self.failed_tasks != self.total_tasks:
            # We should not round the progress value as it may lead to an incomplete progress submitting
            return int(100 * self.solved_tasks / (self.total_tasks - self.failed_tasks))
        if isinstance(self.total_tasks, int) and self.failed_tasks == self.total_tasks:
            return 100

        return None

    @property
    def subjobs_progress(self):
        if not self.job_mode and self.failed_subjobs != self.subjobs_number:
            # We should not round the progress value as it may lead to an incomplete progress submitting
            return int(100 * self.solved_subjobs / (self.subjobs_number - self.failed_subjobs))
        if not self.job_mode and self.failed_subjobs == self.subjobs_number:
            return 100

        return None

    def watch_progress(self):
        self.logger.info("Start progress calculator")
        tasks_start_time = None
        task_update_time = None
        subjobs_update_time = None
        subjobs_start_time = time.time()
        first_task_appeared = False
        total_tasks_determined = False
        total_tasks_messages = []
        task_messages = []
        if self.conf.get('wall time limit', None):
            self.logger.info("Expecting wall time limitation as %s", self.conf.get('wall time limit', None))
            given_finish_time = subjobs_start_time + klever.core.utils.time_units_converter(
                self.conf['wall time limit'])[0]
        else:
            given_finish_time = None

        if self.job_mode:
            data_report = {}
        else:
            data_report = {
                "total_sj": self.subjobs_number,
                "subjobs_started": True,
            }

        delay = 1
        while True:
            if not data_report:
                data_report = {}

            # Drain queue to wait for the whole tasks in background
            klever.core.utils.drain_queue(task_messages, self.mqs['finished and failed tasks'])
            if len(task_messages) > 0:
                while len(task_messages) > 0:
                    job_id, status = task_messages.pop()
                    self.finished_tasks_data.setdefault(job_id, 0)
                    self.failed_tasks_data.setdefault(job_id, 0)
                    if status == 'finished':
                        self.finished_tasks_data[job_id] += 1
                    elif status == 'failed':
                        self.failed_tasks_data[job_id] += 1
                    else:
                        raise ValueError('Unknown status {!r} received from subjob {!r}'.format(status, job_id))
                task_update_time = time.time()

            # Drain queue to wait for the whole tasks in background
            if not isinstance(self.total_tasks, int):
                klever.core.utils.drain_queue(total_tasks_messages, self.mqs['total tasks'])
                while len(total_tasks_messages) > 0:
                    job_id, number = total_tasks_messages.pop()
                    self.total_tasks_data[job_id] = number

            # Check that VTG started tasks solution
            if self.first_task_flag.value and not first_task_appeared:
                self.logger.info('The first task is submitted, starting the time counter')
                data_report["tasks_started"] = True
                first_task_appeared = True
                tasks_start_time = time.time()

            # Total number of tasks is determined
            if isinstance(self.total_tasks, int) and not total_tasks_determined:
                data_report["total_ts"] = self.total_tasks
                total_tasks_determined = True

            # Check subjobs
            changes = [i for i in self.subjobs.keys() if i not in self.subjobs_cache]
            if any(changes):
                for job_id in (i for i, stat in self.subjobs.items() if stat == 'failed' and
                               i not in self.subjobs_cache):
                    self.logger.debug("The job %r has failed", job_id)
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
                        # Estimate it as sum of already received tasks
                        self.total_tasks_data[job_id] = total
                # Check solved job
                if any(True for i, stat in self.subjobs.items()
                        if stat == 'finished' and i not in self.subjobs_cache):
                    self.logger.debug("Set new time as some jobs has been finished")
                    subjobs_update_time = time.time()
                for i in changes:
                    self.subjobs_cache[i] = self.subjobs[i]

            # Calculate time on each report sending on base of all time and the whole number of tasks/subjobs
            if isinstance(self.total_tasks, int) and isinstance(self.tasks_progress, int):
                self.logger.info(f"Current tasks progress is {self.tasks_progress}")
                self.logger.debug(f"Left to solve {self.rest_tasks} tasks of {self.total_tasks} in total")
                task_estimation = self._estimate_time(tasks_start_time, task_update_time, self.solved_tasks,
                                                      self.rest_tasks, self.tasks_progress, given_finish_time)
                data_report["failed_ts"] = self.failed_tasks
                data_report["solved_ts"] = self.solved_tasks
                if isinstance(task_estimation, int):
                    data_report["expected_time_ts"] = task_estimation
                else:
                    data_report["gag_text_ts"] = task_estimation
                if self.tasks_progress == 100:
                    data_report["tasks_finished"] = True

            # Estimate subjobs
            if not self.job_mode and isinstance(self.subjobs_progress, int):
                self.logger.info(f"Current subjobs progress is {self.subjobs_progress}")
                subjob_estimation = self._estimate_time(subjobs_start_time, subjobs_update_time, self.solved_subjobs,
                                                        self.rest_subjobs, self.subjobs_progress, given_finish_time)
                self.logger.debug(f"Left to solve {self.rest_subjobs} subjobs of {self.subjobs_number} in total")
                data_report["failed_sj"] = self.failed_subjobs
                data_report["solved_sj"] = self.solved_subjobs
                if isinstance(subjob_estimation, int):
                    data_report["expected_time_sj"] = subjob_estimation
                else:
                    data_report["gag_text_sj"] = subjob_estimation
                if self.subjobs_progress == 100:
                    data_report["subjobs_finished"] = True

            # Send report
            self._send_report(data_report)

            if (not self.job_mode and self.subjobs_progress == 100) or \
                    (self.job_mode and self.tasks_progress == 100):
                break

            # Wait for 1, 2, 3, ..., 10, 10, 10, ... seconds.
            time.sleep(delay)
            data_report = None
            if delay < 10:
                delay += 1

        self.logger.info("Finish progress calculation")

    main = watch_progress

    def _estimate_time(self, start_time, update_time, solved, rest, progress, given_finish_time):
        def formula():
            delta_time = round(time.time() - update_time)
            last_update_time = round(update_time - start_time)
            estimation = round((rest / solved) * last_update_time - delta_time)
            if given_finish_time:
                estimation = max(round(given_finish_time - time.time()),
                                 estimation)

            return estimation

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

        self.logger.info(f"Solution progress: {progress}, time estimation: {ret}")
        return ret

    def _send_report(self, report):
        send_report = False
        new_report = {}

        def check_new_field(name):
            if name not in self.report_cache and name in report:
                new_report[name] = report[name]
                return True

            return False

        # Send when appears total tasks, start tasks solution, end task solution, total subjobs and start solution
        for prop in ["total_sj", "subjobs_started", "subjobs_finished",
                     "total_ts", "tasks_started", "tasks_finished"]:
            hit = check_new_field(prop)
            send_report += hit
            if hit and prop in {"tasks_started", "tasks_finished",
                                "subjobs_finished", "subjobs_started"}:
                # Do not send it repeatedly
                del report[prop]

        # Check that we can calculate tasks progress and it has changed
        if "gag_text_ts" in report:
            if report["gag_text_ts"] != self.report_cache.get("gag_text_ts"):
                send_report += True
            # Set it here anyway but it is possible we will not send it
            new_report['gag_text_ts'] = report['gag_text_ts']
        elif 'expected_time_ts' in report:
            # Set it here anyway but it is possible we will not send it
            new_report['expected_time_ts'] = report['expected_time_ts']

        # Check progress
        if 'solved_ts' in self.report_cache:
            cached = self.cached_tasks_progress
            percent = self.tasks_progress
            if not cached or abs(cached - percent) > 1:
                send_report += True
        elif 'solved_ts' in report:
            send_report += True

        # Check that we can calculate jobs progress and it has changed
        if "gag_text_sj" in report:
            if report["gag_text_sj"] != self.report_cache.get("gag_text_sj"):
                send_report += True
            # Set it here anyway but it is possible we will not send it
            new_report['gag_text_sj'] = report['gag_text_sj']
        elif 'expected_time_sj' in report:
            # Set it here anyway but it is possible we will not send it
            new_report['expected_time_sj'] = report['expected_time_sj']

        # Check progress
        if 'solved_sj' in self.report_cache:
            cached = self.cached_subjobs_progress
            percent = self.subjobs_progress
            if not cached or abs(cached - percent) > 1:
                send_report += True
        elif 'solved_sj' in report:
            send_report += True

        if send_report:
            for i in ["failed_ts", "solved_ts", "failed_sj", "solved_sj"]:
                if i in report:
                    new_report[i] = report[i]

        if send_report:
            self.logger.info("Sending progress report: %s", str(new_report))
            self.session.submit_progress(new_report)
            self.report_cache = copy.copy(report)
