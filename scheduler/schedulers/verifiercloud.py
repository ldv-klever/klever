import glob
import os
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

        self.version = description["verifier"]["version"]

        # Check priority
        if description["priority"] not in ["LOW", "IDLE"]:
            logging.warning("Task {} has priority higher than LOW".format(description["id"]))
        self.priority = description["priority"]

        # Set limits
        self.limits = {
            "memlimit": int(description["resource limits"]["memory size"] / 1000 ** 2),  # MB
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
        options = description["verifier"]["options"]
        # TODO: like in scheduler/client/__init__.py
        options.append({"-setprop": "parser.readLineDirectives=true"})
        options.append({"-setprop": "cpa.arg.errorPath.graphml=witness.graphml"})
        for option in options:
            for name in option:
                self.options.append(name)
                self.options.append(option[name])

        # Set source files and property
        self.propertyfile = os.path.join(work_dir, description["property file"])
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
        os.makedirs(task_data_dir, exist_ok=True)

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

        # Prepare command to submit
        logging.debug("Prepare arguments of the task {}".format(identifier))
        task_data_dir = os.path.join(self.work_dir, "tasks", identifier, "data")
        run = Run(task_data_dir, description, user, password)
        # Expect branch:revision or revision
        branch, revision = None, None
        if ":" in run.version:
            branch, revision = run.version.split(':')
        else:
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
                              svn_revision=revision)

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
            logging.warning("Task has been finished but no data has been received for the task {}".
                            format(identifier))
            return "ERROR"

        # Unpack results
        task_solution_dir = os.path.join(task_work_dir, "solution")
        logging.debug("Make directory for the solution to extract {0}".format(task_solution_dir))
        os.makedirs(task_solution_dir, exist_ok=True)
        logging.debug("Extract results from {} to {}".format(solution_file, task_solution_dir))
        shutil.unpack_archive(solution_file, task_solution_dir)

        # Move content of output directory to root directory (this is done to correspond to
        # scheduler/client/__init__.py, but this may be wrong and we need to keep output directory as is).
        for file in glob.glob(os.path.join(task_solution_dir, "output/*")):
            shutil.move(file, task_solution_dir)

        # Process results and convert RunExec output to result description
        # TODO: what will happen if there will be several input files?
        # Simulate BenchExec behaviour when one input file is provided (see scheduler/client/__init__.py)
        shutil.move(os.path.join(task_solution_dir, "output.log"), os.path.join(task_solution_dir, "cil.i.log"))
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
        self.server.submit_solution(identifier, solution_description, solution_archive)

        # Remove task directory
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
        self.wi.shutdown()

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
