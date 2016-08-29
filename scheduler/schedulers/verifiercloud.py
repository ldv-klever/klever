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

import json
import os
import re
import sys
import shutil
import logging

import schedulers as schedulers
import client.executils as executils


class Run:
    """Class represents VerifierCloud task to solve"""

    def __init__(self, work_dir, description, user, password):
        """
        Initialize Run object.
        :param work_dir: Path to the directory from which paths given in description are relative.
        :param description: Dictionary with task description.
        :param user: VerifierCloud username.
        :param password: VerifierCloud password.
        """
        # Save user credentials
        self.user_pwd = "{}:{}".format(user, password)

        # Check verifier
        if description["verifier"]["name"] != "CPAchecker":
            raise ValueError("VerifierCloud can use only 'CPAchecker' tool, but {} is given instead".format(
                description["verifier"]["name"]))
        else:
            self.tool = "CPAchecker"

        if "version" in description["verifier"]:
            self.version = description["verifier"]["version"]
        else:
            self.version = None

        # Check priority
        if description["priority"] not in ["LOW", "IDLE"]:
            logging.warning("Task {} has priority higher than LOW".format(description["id"]))
        self.priority = description["priority"]

        # Set limits
        self.limits = {
            "memlimit": int(description["resource limits"]["memory size"]),  # In bytes.
            "timelimit": int(description["resource limits"]["CPU time"] / 1000)
        }

        # Check optional limits
        if "CPUs" in description["resource limits"]:
            self.limits["corelimit"] = int(description["resource limits"]["number of CPU cores"])
        if "CPU model" in description["resource limits"]:
            self.cpu_model = description["resource limits"]["CPU model"]
        else:
            self.cpu_model = None

        # Set opts
        # TODO: Implement options support not just forwarding
        self.options = []
        # Convert list of dictionaries to list
        for option in description["verifier"]["options"]:
            for name in option:
                self.options.append(name)
                self.options.append(option[name])

        # Set source, property and specification files if so
        # Some property file should be always specified
        self.propertyfile = None
        if "property file" in description:
            # Update relative path so that VerifierCloud client will be able to find property file
            self.propertyfile = os.path.join(work_dir, description["property file"])
        elif "specification file" in description:
            # Like with property file above
            self.options = [re.sub(r'{0}'.format(description["specification file"]),
                                   os.path.join(work_dir, description["specification file"]),
                                   opt) for opt in self.options]
        self.sourcefiles = [os.path.join(work_dir, file) for file in description["files"]]


class Scheduler(schedulers.SchedulerExchange):
    """
    Implement scheduler which is based on VerifierCloud web-interface cloud. Scheduler forwards task to the remote
    VerifierCloud and fetch results from there.
    """

    wi = None

    def launch(self):
        """Start scheduler loop."""

        # Perform sanity checks before initializing scheduler
        if "web-interface address" not in self.conf["scheduler"] or not self.conf["scheduler"]["web-interface address"]:
            raise KeyError("Provide VerifierCloud address within configuration property "
                           "'scheduler''Web-interface address'")

        web_client_location = os.path.join(self.conf["scheduler"]["web client location"])
        logging.debug("Add to PATH web client location {0}".format(web_client_location))
        sys.path.append(web_client_location)
        from webclient import WebInterface
        self.wi = WebInterface(self.conf["scheduler"]["web-interface address"], None)

        return super(Scheduler, self).launch()

    @staticmethod
    def scheduler_type():
        """Return type of the scheduler: 'VerifierCloud' or 'Klever'."""
        return "VerifierCloud"

    def schedule(self, pending_tasks, pending_jobs, processing_tasks, processing_jobs, sorter):
        """
        Get list of new tasks which can be launched during current scheduler iteration.
        :param pending_tasks: List with all pending tasks.
        :param processing_tasks: List with currently ongoing tasks.
        :param sorter: Function which can by used for sorting tasks according to their priorities.
        :return: List with identifiers of pending tasks to launch.
        """
        pending_tasks = sorted(pending_tasks, key=sorter)
        if "max concurrent tasks" in self.conf["scheduler"] and self.conf["scheduler"]["max concurrent tasks"]:
            if len(processing_tasks) < self.conf["scheduler"]["max concurrent tasks"]:
                diff = self.conf["scheduler"]["max concurrent tasks"] - len(processing_tasks)
                if diff <= len(pending_tasks):
                    new_tasks = pending_tasks[0:diff]
                else:
                    new_tasks = pending_tasks
            else:
                new_tasks = []
        else:
            new_tasks = pending_tasks

        return [new_task["id"] for new_task in new_tasks], []

    def prepare_task(self, identifier, description=None):
        """
        Prepare working directory before starting solution.
        :param identifier: Verification task identifier.
        :param description: Dictionary with task description.
        """
        # Prepare working directory
        task_work_dir = os.path.join(self.work_dir, "tasks", identifier)
        task_data_dir = os.path.join(task_work_dir, "data")
        logging.debug("Make directory for the task to solve {0}".format(task_data_dir))
        os.makedirs(task_data_dir.encode("utf8"), exist_ok=True)

        # Pull the task from the Verification gateway
        archive = os.path.join(task_work_dir, "task.tar.gz")
        logging.debug("Pull from the verification gateway archive {}".format(archive))
        self.server.pull_task(identifier, archive)
        logging.debug("Unpack archive {} to {}".format(archive, task_data_dir))
        shutil.unpack_archive(archive, task_data_dir)

    def prepare_job(self, identifier, configuration):
        """
        Prepare working directory before starting solution.
        :param identifier: Verification task identifier.
        :param configuration: Job configuration.
        """
        # Cannot be called
        pass

    def solve_task(self, identifier, description, user, password):
        """
        Solve given verification task.
        :param identifier: Verification task identifier.
        :param description: Verification task description dictionary.
        :param user: User name.
        :param password: Password.
        :return: Return Future object.
        """
        # TODO: Add more exceptions handling to make code more reliable
        with open(os.path.join(os.path.join(self.work_dir, "tasks", identifier), "task.json"), "w",
                  encoding="utf8") as fp:
            json.dump(description, fp, ensure_ascii=False, sort_keys=True, indent=4)

        # Prepare command to submit
        logging.debug("Prepare arguments of the task {}".format(identifier))
        task_data_dir = os.path.join(self.work_dir, "tasks", identifier, "data")
        run = Run(task_data_dir, description, user, password)
        # Expect branch:revision or revision
        branch, revision = None, None
        if run.version and ":" in run.version:
            branch, revision = run.version.split(':')
        elif run.version:
            revision = run.version

        if not branch:
            logging.warning("Branch has not given for the task {}".format(identifier))
            branch = None
        if not revision:
            logging.warning("Revision has not given for the task {}".format(identifier))
            revision = None

        # Submit command
        logging.info("Submit the task {0}".format(identifier))
        return self.wi.submit(run=run,
                              limits=run.limits,
                              cpu_model=run.cpu_model,
                              result_files_pattern='output/**',
                              priority=run.priority,
                              user_pwd=run.user_pwd,
                              svn_branch=branch,
                              svn_revision=revision,
                              meta_information=json.dumps({'Verification tasks produced by Klever': None}))

    def solve_job(self, configuration):
        """
        Solve given verification task.
        :param identifier: Job identifier.
        :param configuration: Job configuration.
        :return: Return Future object.
        """
        # Cannot be called
        pass

    def flush(self):
        """Start solution explicitly of all recently submitted tasks."""
        self.wi.flush_runs()

    def process_task_result(self, identifier, future):
        """
        Process result and send results to the verification gateway.
        :param identifier:
        :return: Status of the task after solution: FINISHED or ERROR.
        """
        task_work_dir = os.path.join(self.work_dir, "tasks", identifier)
        solution_file = os.path.join(task_work_dir, "solution.zip")
        logging.debug("Save solution to the disk as {}".format(solution_file))
        if future.result():
            with open(solution_file, 'wb') as sa:
                sa.write(future.result())
        else:
            error_msg = "Task {} has been finished but no data has been received: {}".format(identifier, err)
            logging.warning(error_msg)
            raise schedulers.SchedulerException(error_msg)

        # Unpack results
        task_solution_dir = os.path.join(task_work_dir, "solution")
        logging.debug("Make directory for the solution to extract {0}".format(task_solution_dir))
        os.makedirs(task_solution_dir.encode("utf8"), exist_ok=True)
        logging.debug("Extract results from {} to {}".format(solution_file, task_solution_dir))
        shutil.unpack_archive(solution_file, task_solution_dir)
        # Process results and convert RunExec output to result description
        # TODO: what will happen if there will be several input files?
        # Simulate BenchExec behaviour when one input file is provided.
        os.makedirs(os.path.join(task_solution_dir, "output", "benchmarklogfiles").encode("utf8"))
        shutil.move(os.path.join(task_solution_dir, "output.log"),
                    os.path.join(task_solution_dir, "output", "benchmarklogfiles"))
        solution_description = os.path.join(task_solution_dir, "decision results.json")
        logging.debug("Get solution description from {}".format(solution_description))
        try:
            solution_identifier, solution_description = \
                executils.extract_description(task_solution_dir, solution_description)
            logging.debug("Successfully extracted solution {} for task {}".format(solution_identifier, identifier))
        except Exception as err:
            logging.warning("Cannot extract results from a solution: {}".format(err))
            raise err

        # Make archive
        solution_archive = os.path.join(task_work_dir, "solution")
        logging.debug("Make archive {} with a solution of the task {}.tar.gz".format(solution_archive, identifier))
        shutil.make_archive(solution_archive, 'gztar', task_solution_dir)
        solution_archive += ".tar.gz"

        # Push result
        logging.debug("Upload solution archive {} of the task {} to the verification gateway".format(solution_archive,
                                                                                                     identifier))

        try:
            self.server.submit_solution(identifier, solution_description, solution_archive)
        except Exception as err:
            error_msg = "Cannot submit silution results of task {}: {}".format(identifier, err)
            logging.warning(error_msg)
            raise schedulers.SchedulerException(error_msg)

        if "keep working directory" not in self.conf["scheduler"] or \
                not self.conf["scheduler"]["keep working directory"]:
            logging.debug("Clean task working directory {} for {}".format(task_work_dir, identifier))
            shutil.rmtree(task_work_dir)

        logging.debug("Task {} has been processed successfully".format(identifier))
        return "FINISHED"

    def process_job_result(self, identifier, result):
        """
        Process result and send results to the server.
        :param identifier:
        :return: Status of the task after solution: FINISHED or ERROR.
        """
        # Cannot be called
        pass

    def cancel_task(self, identifier):
        """
        Stop task solution.
        :param identifier: Verification task ID.
        """
        logging.debug("Cancel task {}".format(identifier))
        super(Scheduler, self).cancel_task(identifier)
        task_work_dir = os.path.join(self.work_dir, "tasks", identifier)
        shutil.rmtree(task_work_dir)

    def cancel_job(self, identifier):
        """
        Stop task solution.
        :param identifier: Verification task ID.
        """
        # Cannot be called
        pass

    def terminate(self):
        """
        Abort solution of all running tasks and any other actions before
        termination.
        """
        logging.info("Terminate all runs")
        self.wi.shutdown(wait=False)

    def update_nodes(self):
        """
        Update statuses and configurations of available nodes.
        :return: Return True if nothing has changes
        """
        return super(Scheduler, self).update_nodes()

    def update_tools(self):
        """
        Generate dictionary with verification tools available and
        push it to the verification gate.
        :return: Dictionary with available verification tools.
        """
        # TODO: Implement proper revisions sending
        return super(Scheduler, self)._udate_tools()


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
