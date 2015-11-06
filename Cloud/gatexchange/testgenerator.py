import uuid
import logging
import shutil
import os
import json

import Cloud.gatexchange as gatexchange
import Cloud.utils as utils

task_description_filename = "verification task desc.json"


class Taskgenerator(gatexchange.Session):
    """Start exchange with verification gate."""

    pending = []
    tasks = {}
    tools = {}
    nodes = {}
    work_dir = ""
    solution_dir = ""

    def __import_tasks(self, work_dir):
        """
        Import tasks from the current working directory and assign them PENDING status.
        :param work_dir: Path to the directory with tasks.
        """

        archives = [file for file in os.listdir(work_dir) if os.path.isfile(os.path.join(work_dir, file)) and
                    utils.split_archive_name(file)[1] == ".tar.gz"]
        logging.info("Found {} tasks in {}".format(len(archives), work_dir))

        for archive in archives:
            identifier = utils.split_archive_name(archive)[0]
            description_file = os.path.join(work_dir, identifier, task_description_filename)
            logging.debug("Import task {} from description file {}".format(identifier, description_file))

            with open(description_file, "r") as desc:
                description = json.loads(desc.read())

            # Add task to the pending list
            self.tasks[identifier] = {
                "status": "PENDING",
                "data": os.path.join(work_dir, archive),
                "description file": description_file,
                "description": description
            }
            self.pending.append(identifier)

    def __make_tasks(self, work_dir, location, base_description):
        """
        Get path to XML job and generate set of equivalent separate tasks on
        each c file.
        :param work_dir: Path to the working directory with tasks to generate.
        :param location: Path to the directory with tasks in sv-benchmarks
        repository.
        :param base_description: JSON prototype for task descriptions.
        """

        # Get files
        c_files = [file for file in os.listdir(location) if os.path.isfile(os.path.join(location, file)) and
                   os.path.splitext(file)[1] == ".c"]
        logging.info("Found {0} C files".format(str(len(c_files))))
        prop_file = os.path.join(location, base_description["property"])
        logging.info("Going to use property file {0}".format(prop_file))

        # Generate packages
        for source in c_files:
            # Generate ID and prepare dir
            task_id = str(uuid.uuid4())
            task_dir = os.path.join(work_dir, task_id)
            os.makedirs(task_dir)

            # Move data
            shutil.copyfile(os.path.join(location, source), os.path.join(task_dir, source))
            shutil.copyfile(prop_file, os.path.join(task_dir, base_description["property"]))

            # Save JSON base_description
            description = base_description.copy()
            description["id"] = task_id
            description["files"] = [source]
            json_description = json.dumps(description)
            description_file = os.path.join(task_dir, task_description_filename)
            with open(description_file, "w") as fh:
                fh.write(json_description)
            logging.debug("Generated JSON base_description {0}".format(description_file))

            # Make archive package
            archive = os.path.join(work_dir, task_id)
            shutil.make_archive(archive, 'gztar', task_dir)
            logging.debug("Generated archive with task {0}.tar.gz".format(archive))

            # Add task to the pending list
            self.tasks[task_id] = {
                "status": "PENDING",
                "data": "{0}.tar.gz".format(archive),
                "description file": description_file,
                "description": description
            }
            self.pending.append(task_id)

    def auth(self, user, password):
        """
        Using login and password try to proceed with authorization on the
        Verification Gateway server.
        :param user: Scheduler user user.
        :param password: Scheduler user password
        :return:
        """
        logging.info("Skip user step step.")

    def register(self, name, require_login=False):
        """
        Send unique ID to the Verification Gateway with the other properties to
        enable receiving tasks.
        :param name: Scheduler name.
        :param require_login: Flag indicating whether or not user should
        authorize to send tasks.
        """
        logging.info("Initialize test generator")

        if "user" not in self.conf:
            raise KeyError("Provide gateway username within 'user' attribute in configuration")
        if not {"gate user name", "VerifierCloud user name", "VerifierCloud password"}.\
                issubset(self.conf["user"].keys()):
            raise KeyError("Provide 'gate user name', 'VerifierCloud user name' and 'VerifierCloud password' "
                           "credentials within the configuration")
        if "exchange task number" not in self.conf:
            self.conf["exchange task number"] = 10
        logging.debug("Exchange rate is {} tasks per request".format(self.conf["exchange task number"]))

        # Prepare tasks
        task_work_dir = os.path.join(self.work_dir, "tasks")
        if "keep task dir" in self.conf and self.conf["keep task dir"] and os.path.isdir(task_work_dir):
            logging.info("Use existing task directory {} and import tasks from there".format(task_work_dir))
            self.__import_tasks(task_work_dir)
            logging.info("Tasks are successfully imported")
        else:
            logging.info("Clean working dir for the test generator: {0}".format(self.work_dir))
            shutil.rmtree(self.work_dir, True)

            logging.info("Make directory for tasks {0}".format(task_work_dir))
            os.makedirs(task_work_dir, exist_ok=True)

            logging.debug("Create working dir for the test generator: {0}".format(self.work_dir))
            os.makedirs(self.work_dir, exist_ok=True)

            logging.info("Begin task preparation")
            for task_set in self.conf["task prototypes"]:
                src_dir = self.conf["sv-comp repo location"] + task_set
                logging.debug("Prepare tasks from the directory {0}".format(src_dir))
                self.__make_tasks(task_work_dir, src_dir, self.conf["task prototypes"][task_set])

            logging.info("Tasks are generated in the directory {0}".format(task_work_dir))

        # Prepare directory for solutions
        self.solution_dir = os.path.join(self.work_dir, "solutions")
        logging.info("Clean solution dir for the test generator: {0}".format(self.solution_dir))
        shutil.rmtree(self.solution_dir, True)
        logging.info("Make directory for solutions {0}".format(task_work_dir))
        os.makedirs(self.solution_dir, exist_ok=True)

    def exchange_tasks(self, tasks):
        """
        Get list with tasks and their statuses and update own information about
        them. After that return new portion of tasks with user information and
        descriptions.
        :param tasks: Get dictionary with task statuses in the Scheduler.
        :return: Return dictionary with new tasks, descriptions and users.
        """
        logging.info("Start updating statuses according to received task list")
        new_report = {
            "tasks": {
                "pending": [],
                "processing": [],
                "error": [],
                "unknown": [],
                "finished": []
            },
            "task descriptions": {},
            "users": {}
        }

        # First update failed or finished tasks
        finished_tasks = [tsk for tsk in tasks["tasks"]["finished"] if tsk in self.tasks and self.tasks[tsk]["status"]
                          in ["PENDING", "PROCESSING"]]
        for task in finished_tasks:
            self.tasks[task]["status"] = "FINISHED"
        logging.debug("Mark {} finished tasks".format(str(len(finished_tasks))))

        # Update failed tasks
        unknown_tasks = [tsk for tsk in tasks["tasks"]["unknown"] if tsk in self.tasks and self.tasks[tsk]["status"]
                         in ["PENDING", "PROCESSING"]]
        for task in finished_tasks:
            self.tasks[task]["status"] = "UNKNOWN"
        logging.debug("Mark {} unknown tasks".format(str(len(unknown_tasks))))

        # Update error tasks
        error_tasks = [tsk for tsk in tasks["tasks"]["error"] if tsk in self.tasks and self.tasks[tsk]["status"]
                       in ["PENDING", "PROCESSING"]]
        for task in finished_tasks:
            self.tasks[task]["status"] = "ERROR"
        logging.debug("Mark {} error tasks".format(str(len(error_tasks))))

        # Update processing tasks
        to_processing = [tsk for tsk in tasks["tasks"]["processing"] if self.tasks[tsk]["status"] == "PENDING"]
        logging.debug("Mark {} processing tasks".format(str(len(to_processing))))
        for task in to_processing:
            self.tasks[task]["status"] = "PROCESSING"

        # Get tasks which should be canceled
        cancel_err = [tsk for tsk in (tasks["tasks"]["processing"] + tasks["tasks"]["pending"])
                      if self.tasks[tsk]["status"] in ["UNKNOWN", "ERROR"]]
        logging.debug("Cancel {} tasks".format(str(len(cancel_err))))
        new_report["tasks"]["unknown"] = cancel_err

        # Remove tasks from pending
        logging.debug("Remove from pending error, unknown and finished tasks")
        self.pending = set(self.pending) - set(error_tasks + finished_tasks + unknown_tasks + to_processing)

        # Add new tasks
        if len(self.pending) < self.conf["exchange task number"] or self.conf["exchange task number"] == 0:
            new_pending = list(self.pending)
        else:
            new_pending = list(self.pending)[:self.conf["exchange task number"]]
        old_pending = [tsk for tsk in tasks["tasks"]["pending"] if self.tasks[tsk]["status"] == "PENDING"]
        for task in new_pending:
            new_report["task descriptions"][task] = {
                "description": self.tasks[task]["description"],
                "user": self.conf["user"]["gate user name"]
            }
        logging.debug("Add {} new pending tasks and {} old ones".format(len(new_pending), len(old_pending)))
        new_report["tasks"]["pending"] = new_pending + old_pending

        # Add processing tasks
        whole_proc = [tsk for tsk in self.tasks if self.tasks[tsk]["status"] == "PROCESSING"]
        logging.debug("Add {} processing tasks".format(str(len(whole_proc))))
        new_report["tasks"]["processing"] = whole_proc

        # Add user credentials
        new_report["users"][self.conf["user"]["gate user name"]] = {
            "user": self.conf["user"]["VerifierCloud user name"],
            "password": self.conf["user"]["VerifierCloud password"]
        }

        return new_report

    def pull_task(self, identifier, archive):
        """
        Download verification task data from the verification gateway.
        :param identifier: Verification task identifier.
        :param archive: Path to the zip archive to save.
        """
        logging.debug("Copy task from {} to {}".format(self.tasks[identifier]["data"], archive))
        shutil.copyfile(self.tasks[identifier]["data"], archive)

    def push_solution(self, identifier, archive, description=None):
        """
        Send archive and description of an obtained from VerifierCloud solution
         to the verification gateway.
        :param identifier: Verification task identifier.
        :param archive: Path to the zip archive to send.
        :param description: JSON string to send.
        """
        if self.tasks[identifier]["status"] not in ["FINISHED", "ERROR", "UNKNOWN"]:
            data_file = os.path.join(self.solution_dir, "{}.tar.gz".format(identifier))
            logging.debug("Copy the solution {} to {}".format(archive, data_file))
            shutil.copyfile(archive, data_file)

            logging.debug("Save solution result for the task {}".format(identifier))
            self.tasks[identifier]["solution"] = {
                "data": data_file,
                "description": description
            }
        else:
            raise RuntimeError("Trying to push solution for {0} which has been already processed".format(identifier))

    def submit_nodes(self, nodes):
        """
        Send string with JSON description of nodes available for verification
        in VerifierCloud.
        :param nodes: String with JSON nodes description.
        """
        self.nodes = nodes
        node_desc = json.dumps(nodes)
        with open(os.path.join(self.work_dir, "nodes.json"), "w") as fh:
            fh.write(node_desc)

    def submit_tools(self, tools):
        """
        Send string with JSON description of verification tools available for
        verification in VerifierCloud.
        :param tools: String with JSON verification tools description.
        """
        self.tools = tools
        tool_desc = json.dumps(tools)
        with open(os.path.join(self.work_dir, "tools.json"), "w") as fh:
            fh.write(tool_desc)

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
