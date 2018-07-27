#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

import uuid
import shutil
import os
import json
import random

import server as server

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
                    os.path.splitext(file)[-1] == ".zip"]
        self.logger.info("Found {} tasks in {}".format(len(archives), work_dir))

        for archive in archives:
            identifier = os.path.splitext(archive)[0]
            description_file = os.path.join(work_dir, identifier, task_description_filename)
            self.logger.debug("Import task {} from description file {}".format(identifier, description_file))

            with open(description_file, encoding="utf8") as desc:
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
        self.logger.info("Found {0} C files".format(str(len(c_files))))
        prop_file = os.path.join(location, base_description["property"])
        self.logger.info("Going to use property file {0}".format(prop_file))

        # Generate packages
        for source in c_files:
            # Generate ID and prepare dir
            task_id = str(uuid.uuid4())
            task_dir = os.path.join(work_dir, task_id)
            os.makedirs(task_dir.encode("utf8"))

            # Move data
            shutil.copyfile(os.path.join(location, source), os.path.join(task_dir, source))
            shutil.copyfile(prop_file, os.path.join(task_dir, base_description["property"]))

            # Save JSON base_description
            description = base_description.copy()
            description["id"] = task_id
            description["files"] = [source]
            description["priority"] = random.choice(self.conf["priority options"])
            json_description = json.dumps(description, ensure_ascii=False, sort_keys=True, indent=4)
            description_file = os.path.join(task_dir, task_description_filename)
            with open(description_file, "w", encoding="utf8") as fh:
                fh.write(json_description)
            self.logger.debug("Generated JSON base_description {0}".format(description_file))

            # Make archive package
            archive = os.path.join(work_dir, task_id)
            shutil.make_archive(archive, 'gztar', task_dir)
            self.logger.debug("Generated archive with task {0}.zip".format(archive))

            # Add task to the pending list
            self.tasks[task_id] = {
                "status": "PENDING",
                "data": "{0}.zip".format(archive),
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
        self.logger.info("Skip user step step.")

    def register(self, scheduler_type):
        """
        Send unique ID to the Verification Gateway with the other properties to
        enable receiving tasks.
        :param scheduler_type: Scheduler scheduler type.
        authorize to send tasks.
        """
        self.logger.info("Initialize test generator")

        if "exchange task number" not in self.conf:
            self.conf["exchange task number"] = 10
        self.logger.debug("Exchange rate is {} tasks per request".format(self.conf["exchange task number"]))

        # Prepare tasks
        task_work_dir = os.path.join(self.work_dir, "tasks")
        if "keep task dir" in self.conf and self.conf["keep task dir"] and os.path.isdir(task_work_dir):
            self.logger.info("Use existing task directory {} and import tasks from there".format(task_work_dir))
            self.__import_tasks(task_work_dir)
            self.logger.info("Tasks are successfully imported")
        else:
            self.logger.info("Clean working dir for the test generator: {0}".format(self.work_dir))
            shutil.rmtree(self.work_dir, True)

            self.logger.info("Make directory for tasks {0}".format(task_work_dir))
            os.makedirs(task_work_dir.encode("utf8"), exist_ok=True)

            self.logger.debug("Create working dir for the test generator: {0}".format(self.work_dir))
            os.makedirs(self.work_dir.encode("utf8"), exist_ok=True)

            self.logger.info("Begin task preparation")
            for task_set in self.conf["task prototypes"]:
                src_dir = self.conf["sv-comp repo location"] + task_set
                self.logger.debug("Prepare tasks from the directory {0}".format(src_dir))
                self.__make_tasks(task_work_dir, src_dir, self.conf["task prototypes"][task_set])

            self.logger.info("Tasks are generated in the directory {0}".format(task_work_dir))

        # Prepare directory for solutions
        self.solution_dir = os.path.join(self.work_dir, "solutions")
        self.logger.info("Clean solution dir for the test generator: {0}".format(self.solution_dir))
        shutil.rmtree(self.solution_dir, True)
        self.logger.info("Make directory for solutions {0}".format(task_work_dir))
        os.makedirs(self.solution_dir.encode("utf8"), exist_ok=True)

    def exchange(self, tasks):
        """
        Get list with tasks and their statuses and update own information about
        them. After that return new portion of tasks with user information and
        descriptions.
        :param tasks: Get dictionary with scheduler task statuses.
        :return: Return dictionary with new tasks, descriptions and users.
        """
        self.logger.info("Start updating statuses according to received task list")
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

        self.logger.debug("Update statuses in testgenerator")
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

        self.logger.debug("Generate new status report for scheduler")
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

        self.logger.debug("Test-generator state: PENDING: {}, PROCESSING: {}, ERROR: {}, FINISHED: {}".
                      format(self.pending_cnt, self.processing_cnt, self.error_cnt, self.finished_cnt))
        return report

    def pull_task(self, identifier, archive):
        """
        Download verification task data from the verification gateway.
        :param identifier: Verification task identifier.
        :param archive: Path to the zip archive to save.
        """
        self.logger.debug("Copy task from {} to {}".format(self.tasks[identifier]["data"], archive))
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
            data_file = os.path.join(self.solution_dir, "{}.zip".format(identifier))
            self.logger.debug("Copy the solution {} to {}".format(archive, data_file))
            shutil.copyfile(archive, data_file)

            self.logger.debug("Save solution result for the task {}".format(identifier))
            self.tasks[identifier]["solution"] = description
            self.tasks[identifier]["result"] = data_file
        else:
            raise RuntimeError("Trying to push solution for {0} which has been already processed".format(identifier))

    def submit_nodes(self, nodes, looping=True):
        """
        Send string with JSON description of nodes available for verification
        in VerifierCloud.
        :param nodes: String with JSON nodes description.
        :param looping: Flag that indicates that this request should be attempted until it is successful.
        """
        self.nodes = nodes
        node_desc = json.dumps(nodes, ensure_ascii=False, sort_keys=True, indent=4)
        with open(os.path.join(self.work_dir, "nodes.json"), "w", encoding="utf8") as fh:
            fh.write(node_desc)

    def submit_tools(self, tools):
        """
        Send string with JSON description of verification tools available for
        verification in VerifierCloud.
        :param tools: String with JSON verification tools description.
        """
        self.tools = tools
        tool_desc = json.dumps(tools, ensure_ascii=False, sort_keys=True, indent=4)
        with open(os.path.join(self.work_dir, "tools.json"), "w", encoding="utf8") as fh:
            fh.write(tool_desc)

    def stop(self):
        """
        Log out if necessary.
        """
        return

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
