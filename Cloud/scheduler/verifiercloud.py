import time
import os
import sys
import shutil
import logging
import Cloud.scheduler as scheduler
import Cloud.client.executils as executils


class Run:
    """Class represents VerifierCloud task to solve"""

    futures = {}

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
        if "require authorization" not in self.conf or not self.conf["require authorization"]:
            raise ValueError("Provide 'Scheduler''require authorization' configuration property always as True for VerifierCloud")
        if "VerifierCloud user name" not in self.conf:
            raise KeyError("Provide 'Scheduler''VerifierCloud user name' to login at VerifierCloud within the configuration")
        if "VerifierCloud password" not in self.conf:
            raise KeyError("Provide 'Scheduler''VerifierCloud password' to login at VerifierCloud within the configuration")

        # TODO: Investigate which sources are necessary and which are optional
        # Add path to benchexec directory
        bexec_loc = self.conf["BenchExec location"]
        logging.debug("Add to PATH location {0}".format(bexec_loc))
        sys.path.append(bexec_loc)
        import benchexec

        # Add path to CPAchcker scripts directory
        cpa_loc = os.path.join(self.conf["CPAchecker location"], "scripts", "benchmark")
        logging.debug("Add to PATH location {0}".format(cpa_loc))
        sys.path.append(cpa_loc)
        from webclient import WebInterface
        self.wi = WebInterface(self.conf["Web Interface address"], "{}:{}".format(self.conf["VerifierCloud user name"],
                                                                                  self.conf["VerifierCloud password"]))

        return super(Scheduler, self).launch()

    def _prepare_task(self, identifier):
        """
        Prepare working directory before starting solution.
        :param identifier: Verification task identifier.
        """
        # Prepare working directory
        task_work_dir = os.path.join(self.work_dir, "tasks", identifier)
        task_data_dir = os.path.join(task_work_dir, "data")
        logging.debug("Make directory for the task to solve {0}".format(task_data_dir))
        os.makedirs(task_data_dir, exist_ok=True)

        # Pull the task from the Verification gateway
        archive = os.path.join(task_work_dir, "task.tar.gz")
        logging.debug("Pull from the verification gateway archive {}".format(archive))
        self.gw.pull_task(identifier, archive)
        logging.debug("Unpack archive {} to {}".format(archive, task_data_dir))
        shutil.unpack_archive(archive, task_data_dir)

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

    def _flush(self):
        """Start solution explicitly of all recently submitted tasks."""
        self.wi.flush_runs()

    def _process_result(self, identifier, result):
        """
        Process result and send results to the verification gateway.
        :param identifier:
        :return: Status of the task after solution: FINISHED, UNKNOWN or ERROR.
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
            solution_identifier = executils.extract_description(task_solution_dir, solution_description)
        except (OSError, ValueError) as err:
            logging.warning("Cannot process results for the task {} because of {}".format(identifier, err))

            # Remove task directory
            shutil.rmtree(task_work_dir)

            return "UNKNOWN"
        logging.debug("Successfully extracted solution {} for task {}".format(solution_identifier, identifier))

        # Make archive
        solution_archive = os.path.join(task_work_dir, "solution")
        logging.debug("Make archive {} with a solution of the task {}.tar.gz".format(solution_archive, identifier))
        shutil.make_archive(solution_archive, 'gztar', task_solution_dir)
        solution_archive += ".tar.gz"

        # Push result
        logging.debug("Upload solution archive {} of the task {} to the verification gateway".format(solution_archive,
                                                                                                     identifier))
        self.gw.push_solution(identifier, solution_archive)

        # Remove task directory
        shutil.rmtree(task_work_dir)

        logging.debug("Task {} has been processed successfully".format(identifier))
        return "FINISHED"

    def _cancel_task(self, identifier):
        """
        Stop task solution.
        :param identifier: Verification task ID.
        """
        logging.debug("Cancel task {}".format(identifier))
        super(Scheduler, self)._cancel_task(identifier)
        task_work_dir = os.path.join(self.work_dir, "tasks", identifier)
        shutil.rmtree(task_work_dir)

    def _terminate(self):
        """
        Abort solution of all running tasks and any other actions before
        termination.
        """
        logging.info("Terminate all runs")
        return self.wi.shutdown()

    def _nodes(self, period):
        """
        Update time to time statuses and configurations of available nodes and
        push it to the verification gate.
        :param period: Time in seconds between each update request.
        :return: Dictionary with configurations and statuses of nodes.
        """
        # TODO: Parse CPAchecker master status page and provide data given
        # with the page
        nodes = {}
        while True:
            logging.debug("Send nodes info to the verification gateway")
            self.gw.submit_nodes(nodes)
            time.sleep(period)

    def _tools(self, period):
        """
        Generate time to time dictionary with verification tools available and
        push it to the verification gate.
        :param period: Time in seconds between each update request.
        :return: Dictionary with available verification tools.
        """
        while True:
            logging.debug("Send tools info to the verification gateway")
            # TODO: Implement collecting of working revisions
            self.gw.submit_tools([])
            time.sleep(period)


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
