import uuid
import logging
import shutil
import os
import json
import random

import server as server
import utils as utils

task_description_filename = "verification task desc.json"


class Server(server.AbstractServer):
    """Start exchange with verification gate."""

    tasks = {}
    tools = {}
    nodes = {}
    pending_cnt = 0
    processing_cnt = 0
    error_cnt = 0
    finished_cnt = 0

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

            with open(description_file, encoding="ascii") as desc:
                description = json.loads(desc.read())

            # Add task to the pending list
            self.tasks[identifier] = {
                "status": "PENDING",
                "data": os.path.join(work_dir, archive),
                "description file": description_file,
                "description": description
            }
            self.pending_cnt += 1

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
            description["priority"] = random.choice(self.conf["priority options"])
            json_description = json.dumps(description, sort_keys=True, indent=4)
            description_file = os.path.join(task_dir, task_description_filename)
            with open(description_file, "w", encoding="ascii") as fh:
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
            self.pending_cnt += 1

    def auth(self, user, password):
        """
        Using login and password try to proceed with authorization on the
        Verification Gateway server.
        :param user: Scheduler user.
        :param password: Scheduler password
        :return:
        """
        logging.info("Skip user step step.")

    def register(self, scheduler_type):
        """
        Send unique ID to the Verification Gateway with the other properties to
        enable receiving tasks.
        :param scheduler_type: Scheduler scheduler type.
        authorize to send tasks.
        """
        logging.info("Initialize test generator")

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

    def exchange(self, tasks):
        """
        Get list with tasks and their statuses and update own information about
        them. After that return new portion of tasks with user information and
        descriptions.
        :param tasks: Get dictionary with scheduler task statuses.
        :return: Return dictionary with new tasks, descriptions and users.
        """
        logging.info("Start updating statuses according to received task list")
        report = {
            "tasks": {
                "pending": [],
                "processing": [],
                "error": [],
                "finished": []
            },
            "jobs": {
                "pending": [],
                "processing": [],
                "error": [],
                "finished": []
            },
            "task descriptions": {},
        }

        logging.debug("Update statuses in testgenerator")
        # Update PENDING -> ERROR
        for task_id in [task_id for task_id in tasks["tasks"]["error"] if self.tasks[task_id]["status"] == "PENDING"]:
            self.tasks[task_id]["status"] = "ERROR"
            self.tasks[task_id]["error message"] = tasks["task errors"][task_id]
            self.pending_cnt -= 1
            self.error_cnt += 1

        # Update PROCESSING -> ERROR
        for task_id in [task_id for task_id in tasks["tasks"]["error"] if self.tasks[task_id]["status"] == "PROCESSING"]:
            self.tasks[task_id]["status"] = "ERROR"
            self.tasks[task_id]["error"] = tasks["task errors"][task_id]
            self.processing_cnt -= 1
            self.error_cnt += 1

        # Update PENDING -> PROCESSING
        for task_id in [task_id for task_id in tasks["tasks"]["processing"]
                        if self.tasks[task_id]["status"] == "PENDING"]:
            self.tasks[task_id]["status"] = "PROCESSING"
            self.pending_cnt -= 1
            self.processing_cnt += 1

        # Update PROCESSING -> PENDING
        for task_id in [task_id for task_id in tasks["tasks"]["pending"]
                        if self.tasks[task_id]["status"] == "PROCESSING"]:
            self.tasks[task_id]["status"] = "PROCESSING"
            self.processing_cnt -= 1
            self.pending_cnt += 1

        # Update PENDING -> FINISHED
        for task_id in [task_id for task_id in tasks["tasks"]["finished"]
                        if self.tasks[task_id]["status"] == "PENDING"]:
            self.tasks[task_id]["status"] = "FINISHED"
            self.pending_cnt -= 1
            self.finished_cnt += 1

            if "solution" not in self.tasks[task_id] or not self.tasks[task_id]["solution"]:
                raise RuntimeError("Solution is required before FINISHED status can be assigned: {}".format(task_id))

        # Update PROCESSING -> FINISHED
        for task_id in [task_id for task_id in tasks["tasks"]["finished"]
                        if self.tasks[task_id]["status"] == "PROCESSING"]:
            self.tasks[task_id]["status"] = "FINISHED"
            self.processing_cnt -= 1
            self.finished_cnt += 1

            if "solution" not in self.tasks[task_id] or not self.tasks[task_id]["solution"]:
                raise RuntimeError("Solution is required before FINISHED status can be assigned: {}".format(task_id))

        logging.debug("Generate new status report for scheduler")
        report["tasks"]["pending"] = [task_id for task_id in self.tasks if self.tasks[task_id]["status"] == "PENDING"]
        report["tasks"]["processing"] = [task_id for task_id in self.tasks
                                         if self.tasks[task_id]["status"] == "PROCESSING"]
        report["task solutions"] = [self.tasks[task_id]["solution"] for task_id in self.tasks
                                       if (self.tasks[task_id]["status"] == "PENDING" or
                                           self.tasks[task_id]["status"] == "PROCESSING") and
                                       "solution descriptions" in self.tasks[task_id]]

        for task_id in [task_id for task_id in self.tasks if self.tasks[task_id]["status"] == "PENDING"]:
            report["task descriptions"][task_id] = { "description": self.tasks[task_id]["description"] }
            if "scheduler user name" in self.conf and self.conf["scheduler user name"]:
                report["task descriptions"][task_id]["scheduler user name"] = self.conf["scheduler user name"]
                report["task descriptions"][task_id]["scheduler password"] = self.conf["scheduler password"]

        logging.debug("Test-generator state: PENDING: {}, PROCESSING: {}, ERROR: {}, FINISHED: {}".
                      format(self.pending_cnt, self.processing_cnt, self.error_cnt, self.finished_cnt))
        return report

    def pull_task(self, identifier, archive):
        """
        Download verification task data from the verification gateway.
        :param identifier: Verification task identifier.
        :param archive: Path to the zip archive to save.
        """
        logging.debug("Copy task from {} to {}".format(self.tasks[identifier]["data"], archive))
        shutil.copyfile(self.tasks[identifier]["data"], archive)

    def submit_solution(self, identifier, archive, description):
        """
        Send archive and description of an obtained from VerifierCloud solution
         to the verification gateway.
        :param identifier: Verification task identifier.
        :param archive: Path to the zip archive to send.
        :param description: JSON string to send.
        """
        if self.tasks[identifier]["status"] in ["PENDING", "PROCESSING"]:
            data_file = os.path.join(self.solution_dir, "{}.tar.gz".format(identifier))
            logging.debug("Copy the solution {} to {}".format(archive, data_file))
            shutil.copyfile(archive, data_file)

            logging.debug("Save solution result for the task {}".format(identifier))
            self.tasks[identifier]["solution"] = description
            self.tasks[identifier]["result"] = data_file
        else:
            raise RuntimeError("Trying to push solution for {0} which has been already processed".format(identifier))

    def submit_nodes(self, nodes):
        """
        Send string with JSON description of nodes available for verification
        in VerifierCloud.
        :param nodes: String with JSON nodes description.
        """
        self.nodes = nodes
        node_desc = json.dumps(nodes, sort_keys=True, indent=4)
        with open(os.path.join(self.work_dir, "nodes.json"), "w", encoding="ascii") as fh:
            fh.write(node_desc)

    def submit_tools(self, tools):
        """
        Send string with JSON description of verification tools available for
        verification in VerifierCloud.
        :param tools: String with JSON verification tools description.
        """
        self.tools = tools
        tool_desc = json.dumps(tools, sort_keys=True, indent=4)
        with open(os.path.join(self.work_dir, "tools.json"), "w", encoding="ascii") as fh:
            fh.write(tool_desc)

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
