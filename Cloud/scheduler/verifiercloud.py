import time
import os
import sys
import shutil
import logging
import Cloud.scheduler as scheduler
import Cloud.client.executils as executils


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
        self.description = description

        # Save user credentials
        self.user_pwd = "{}:{}".format(user, password)

        # Check verifier
        if self.description["verifier"]["name"] != "cpachecker":
            raise ValueError("VerifierCloud can use only 'cpachecker' tool, but {} is given instead".format(
                self.description["verifier"]["name"]))
        else:
            self.tool = "cpachecker"

        # Expect branch:revision
        if ":" not in self.description["verifier"]["version"]:
            raise ValueError("Expect version as branch:revision pair in task description, but got {}".
                             format(self.description["verifier"]["version"]))
        self.version = self.description["verifier"]["version"].split(":")

        # Check priority
        if self.description["priority"] not in ["LOW", "IDLE"]:
            logging.warning("Task {} has priority higher than LOW".format(self.description["id"]))
        self.priority = self.description["priority"]

        # Set limits
        self.limits = {
            "memoryLimitation": int(float(self.description["resource limits"]["max mem size"]) / 1000),  # MB
            "timeLimitation": int(self.description["resource limits"]["wall time"]),
            "softTimeLimitation": int(self.description["resource limits"]["cpu time"])
        }

        # Check optional limits
        if "CPUs" in self.description["resource limits"]:
            self.limits["coreLimitation"] = int(self.description["resource limits"]["CPUs"])
        if "CPU model" in self.description["resource limits"]:
            self.limits["cpuModel"] = self.description["resource limits"]["CPU model"]
            self.cpu_model = self.description["resource limits"]["CPU model"]
        else:
            self.cpu_model = None

        # Set opts
        # TODO: Implement options support not just forwarding
        self.options = self.description["verifier"]["opts"]

        # Set source files and property
        self.propertyfile = os.path.join(work_dir, self.description["property"])
        self.sourcefiles = [os.path.join(work_dir, file) for file in self.description["files"]]


class Scheduler(scheduler.SchedulerExchange):
    """
    Implement scheduler which is based on VerifierCloud web-interface cloud. Scheduler forwards task to the remote
    VerifierCloud and fetch results from there.
    """

    wi = None

    def launch(self):
        """Start scheduler loop."""

        # Perform sanity checks before initializing scheduler
        if "web-interface address" not in self.conf or not self.conf["web-interface address"]:
            raise KeyError("Provide VerifierCloud address within configuration property "
                           "'scheduler''Web-interface address'")
        if "scheduler user name" not in self.conf:
            raise KeyError("Provide configuration property 'scheduler''scheduler user name'")
        if "scheduler password" not in self.conf:
            raise KeyError("Provide configuration property 'scheduler''scheduler password'")

        # Add path to benchexec directory
        bexec_loc = self.conf["BenchExec location"]
        logging.debug("Add to PATH location {0}".format(bexec_loc))
        sys.path.append(bexec_loc)

        # Add path to CPAchecker scripts directory
        cpa_loc = os.path.join(self.conf["CPAchecker location"], "scripts", "benchmark")
        logging.debug("Add to PATH location {0}".format(cpa_loc))
        sys.path.append(cpa_loc)
        from webclient import WebInterface
        self.wi = WebInterface(self.conf["web-interface address"], "{}:{}".format(self.conf["scheduler user name"],
                                                                                  self.conf["scheduler password"]))

        return super(Scheduler, self).launch()

    def scheduler_type(self):
        """Return type of the scheduler: 'VerifierCloud' or 'Klever'."""
        return "VerifierCloud"

    def _schedule(self, pending, processing, sorter):
        """
        Get list of new tasks which can be launched during current scheduler iteration.
        :param pending: List with all pending tasks.
        :param processing: List with currently ongoing tasks.
        :param sorter: Function which can by used for sorting tasks according to their priorities.
        :return: List with identifiers of pending tasks to launch.
        """
        if "max concurrent tasks" in self.conf and self.conf["max concurrent tasks"]:
            if len(processing) < self.conf["max concurrent tasks"]:
                diff = self.conf["max concurrent tasks"] - len(processing)
                if diff <= len(pending):
                    new = pending[0:diff]
                else:
                    new = pending
            else:
                new = []
        else:
            new = pending

        return new

    def _prepare_task(self, identifier, description=None):
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

    def _prepare_job(self, identifier, configuration):
        """
        Prepare working directory before starting solution.
        :param identifier: Verification task identifier.
        :param configuration: Job configuration.
        """
        # Cannot be called
        pass

    def _solve_task(self, identifier, description, user, password):
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
        branch, revision = run.version
        if branch == "":
            logging.warning("Branch has not given for the task {}".format(identifier))
            branch = None
        if revision == "":
            logging.warning("Revision has not given for the task {}".format(identifier))
            revision = None

        # Submit command
        logging.info("Submit the task {0}".format(identifier))
        return self.wi.submit(run=run,
                              limits=run.limits,
                              cpu_model=run.cpu_model,
                              result_files_pattern=None,
                              priority=run.priority,
                              user_pwd=run.user_pwd,
                              svn_branch=branch,
                              svn_revision=revision)

    def _solve_job(self, configuration):
        """
        Solve given verification task.
        :param identifier: Job identifier.
        :param configuration: Job configuration.
        :return: Return Future object.
        """
        # Cannot be called
        pass

    def _flush(self):
        """Start solution explicitly of all recently submitted tasks."""
        self.wi.flush_runs()

    def _process_task_result(self, identifier, result):
        """
        Process result and send results to the verification gateway.
        :param identifier:
        :return: Status of the task after solution: FINISHED or ERROR.
        """
        task_work_dir = os.path.join(self.work_dir, "tasks", identifier)
        solution_file = os.path.join(task_work_dir, "solution.zip")
        logging.debug("Save solution to the disk as {}".format(solution_file))
        if result:
            with open(solution_file, 'wb') as sa:
                sa.write(result)
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

        # Process results and convert RunExec output to result description
        solution_description = os.path.join(task_solution_dir, "verification task decision result.json")
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
        self.server.submit_solution(identifier, solution_archive, solution_description)

        # Remove task directory
        shutil.rmtree(task_work_dir)

        logging.debug("Task {} has been processed successfully".format(identifier))
        return "FINISHED"

    def _process_job_result(self, identifier, result):
        """
        Process result and send results to the server.
        :param identifier:
        :return: Status of the task after solution: FINISHED or ERROR.
        """
        # Cannot be called
        pass

    def _cancel_task(self, identifier):
        """
        Stop task solution.
        :param identifier: Verification task ID.
        """
        logging.debug("Cancel task {}".format(identifier))
        super(Scheduler, self)._cancel_task(identifier)
        task_work_dir = os.path.join(self.work_dir, "tasks", identifier)
        shutil.rmtree(task_work_dir)

    def _cancel_job(self, identifier):
        """
        Stop task solution.
        :param identifier: Verification task ID.
        """
        # Cannot be called
        pass

    def _terminate(self):
        """
        Abort solution of all running tasks and any other actions before
        termination.
        """
        logging.info("Terminate all runs")
        return self.wi.shutdown()

    def _update_nodes(self):
        """
        Update statuses and configurations of available nodes.
        :return: Return True if nothing has changes
        """
        return super(Scheduler, self)._update_nodes()

    def _update_tools(self):
        """
        Generate dictionary with verification tools available and
        push it to the verification gate.
        :return: Dictionary with available verification tools.
        """
        # TODO: Implement proper revisions sending
        return super(Scheduler, self)._udate_tools()


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
