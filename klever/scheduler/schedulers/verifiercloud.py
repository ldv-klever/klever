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

import os
import re
import sys
import yaml
import glob
import uuid
import json
import shutil
import traceback
import collections
from xml.dom import minidom
import xml.etree.ElementTree as ET

import klever.scheduler.schedulers as schedulers
import klever.scheduler.schedulers.runners as runners
import klever.scheduler.utils as utils


class Run:
    """Class represents VerifierCloud scheduler for task forwarding to the cloud."""

    def __init__(self, work_dir, description):
        """
        Initialize Run object.

        :param work_dir: A path to the directory from which paths given in description are relative.
        :param description: Dictionary with a task description.
        """
        self.branch = None
        self.revision = None
        self.version = None
        self.options = []

        # Check verifier
        if description["verifier"]["name"] != "CPAchecker":
            raise ValueError("VerifierCloud can use only 'CPAchecker' tool, but {} is given instead".format(
                description["verifier"]["name"]))
        else:
            self.tool = "CPAchecker"

        if "version" in description["verifier"]:
            self.version = description["verifier"]["version"]
            if ":" in self.version:
                self.branch, self.revision = self.version.split(':')
            else:
                self.revision = self.version

        self.priority = description["priority"]

        # Set limits
        self.limits = {
            "memlimit": int(description["resource limits"]["memory size"]),  # In bytes.
            "timelimit": int(description["resource limits"]["CPU time"])
        }

        # Check optional limits
        if "number of CPU cores" in description["resource limits"] and \
                description["resource limits"]["number of CPU cores"] != 0:
            self.limits["corelimit"] = int(description["resource limits"]["number of CPU cores"])
        if "CPU model" in description["resource limits"]:
            self.cpu_model = description["resource limits"]["CPU model"]
        else:
            self.cpu_model = None

        # Parse Benchmark XML
        with open(os.path.join(work_dir, 'benchmark.xml'), encoding="utf-8") as fp:
            result = ET.parse(fp).getroot()
            # Expect single run definition
            if len(result.findall("rundefinition")) != 1:
                raise ValueError('Expect a single rundefinition tag')
            opt_tags = result.findall("rundefinition")[0].findall('option')
            for tag in opt_tags:
                if 'name' in tag.attrib:
                    self.options.append(tag.get('name'))
                if tag.text:
                    self.options.append(tag.text)

        # Set source, property and specification files if so
        # Some property file should be always specified
        if len(result.findall("propertyfile")) != 1:
            raise ValueError('Expect a single property file given with "propertyfile" tag')
        self.propertyfile = os.path.abspath(os.path.join(work_dir, result.findall("propertyfile")[0].text))
        if len(result.findall('tasks')) != 1 or len(result.findall('tasks')[0].findall('include')) != 1:
            raise ValueError('Expect a single task with a single included file')

        # Collect source files
        source_files = []
        for item in result.findall('tasks')[0].findall('include'):
            if item.text.endswith('.yml'):
                file = os.path.join(work_dir, item.text)
                with open(file, 'r', encoding="utf-8") as stream:
                    data = yaml.safe_load(stream)
                    input_files = data.get('input_files')
                    if input_files:
                        source_files.append(os.path.abspath(os.path.join(work_dir, input_files)))
            else:
                source_files.append(os.path.abspath(os.path.join(work_dir, item.text)))

        self.sourcefiles = source_files

    @staticmethod
    def user_pwd(user, password):
        """
        Provide a user and a password in the format expected by VerifierCloud adapter library.

        :param user: String
        :param password: String.
        :return: String.
        """
        return "{}:{}".format(user, password)


class VerifierCloud(runners.Runner):
    """
    Implement scheduler which is based on VerifierCloud web-interface. The scheduler forwards task to the remote
    VerifierCloud and fetch results from there.
    """

    wi = None
    accept_jobs = False
    accept_tag = 'VerifierCloud'

    def __init__(self, conf, logger, work_dir, server):
        """Do VerifierCloud specific initialization"""
        super(VerifierCloud, self).__init__(conf, logger, work_dir, server)
        self.wi = None
        self.__tasks = None
        self.__credentials_cache = dict()
        self.init()

    def init(self):
        """
        Initialize scheduler completely. This method should be called both at constructing stage and scheduler
        reinitialization. Thus, all object attribute should be cleaned up and set as it is a newly created object.
        """
        super(VerifierCloud, self).init()

        # Perform sanity checks before initializing scheduler
        if "web-interface address" not in self.conf["scheduler"] or not self.conf["scheduler"]["web-interface address"]:
            raise KeyError("Provide VerifierCloud address within configuration property "
                           "'scheduler''Web-interface address'")

        web_client_location = os.path.join(self.conf["scheduler"]["web client location"])
        self.logger.debug("Add to PATH web client location {0}".format(web_client_location))
        sys.path.append(web_client_location)
        from webclient import WebInterface
        self.wi = WebInterface(self.conf["scheduler"]["web-interface address"], None)

        self.__tasks = dict()

    @staticmethod
    def scheduler_type():
        """Return type of the scheduler: 'VerifierCloud' or 'Klever'."""
        return "VerifierCloud"

    def schedule(self, pending_tasks, pending_jobs):
        """
        Get a list of new tasks which can be launched during current scheduler iteration. All pending jobs and tasks
        should be sorted reducing the priority to the end. Each task and job in arguments are dictionaries with full
        configuration or description.

        :param pending_tasks: List with all pending tasks.
        :param pending_jobs: List with all pending jobs.
        :return: List with identifiers of pending tasks to launch and list with identifiers of jobs to launch.
        """
        return [pending_tasks["id"] for pending_tasks in pending_tasks], []

    def flush(self):
        """Start solution explicitly of all recently submitted tasks."""
        self.wi.flush_runs()

    def terminate(self):
        """
        Abort solution of all running tasks and any other actions before termination.
        """
        self.logger.info("Terminate all runs")
        # This is not reliable library as it is developed separately of Schedulers
        try:
            self.wi.shutdown()
        except Exception:
            self.logger.warning("Web interface wrapper raised an exception: \n{}".
                                format(traceback.format_exc().rstrip()))

    def update_nodes(self, wait_controller=False):
        """
        Update statuses and configurations of available nodes and push them to the server.

        :param wait_controller: Ignore KV fails until it become working.
        :return: Return True if nothing has changes.
        """
        return super(VerifierCloud, self).update_nodes()

    def update_tools(self):
        """
        Generate a dictionary with available verification tools and push it to the server.
        """
        # TODO: Implement proper revisions sending
        return

    def _prepare_task(self, identifier, description):
        """
        Prepare a working directory before starting the solution.

        :param identifier: Verification task identifier.
        :param description: Dictionary with task description.
        :raise SchedulerException: If a task cannot be scheduled or preparation failed.
        """
        # Prepare working directory
        task_work_dir = os.path.join(self.work_dir, "tasks", identifier)
        task_data_dir = os.path.join(task_work_dir, "data")
        job_id = description['job id']

        self.logger.debug("Make directory for the task to solve {!r}".format(task_data_dir))
        os.makedirs(task_data_dir.encode("utf-8"), exist_ok=True)

        # This method can be called several times to adjust resource limitations but we should avoid extra downloads
        # from the server
        if identifier not in self.__tasks:
            archive = os.path.join(task_work_dir, "task.zip")
            self.logger.debug("Pull from the verification gateway archive {!r}".format(archive))
            ret = self.server.pull_task(identifier, archive)
            if not ret:
                self.logger.info("Seems that the task data cannot be downloaded because of a respected reason, "
                                 "so we have nothing to do there")
                os._exit(1)
            self.logger.debug("Unpack archive {!r} to {!r}".format(archive, task_data_dir))
            shutil.unpack_archive(archive, task_data_dir)

            # Update description
            description.update(self.__get_credentials(job_id))

        # TODO: Add more exceptions handling to make code more reliable
        with open(os.path.join(os.path.join(self.work_dir, "tasks", identifier), "task.json"), "w",
                  encoding="utf-8") as fp:
            json.dump(description, fp, ensure_ascii=False, sort_keys=True, indent=4)

        # Prepare command to submit
        self.logger.debug("Prepare arguments of the task {!r}".format(identifier))
        task_data_dir = os.path.join(self.work_dir, "tasks", identifier, "data")
        try:
            assert description["priority"] in ["LOW", "IDLE"]
            run = Run(task_data_dir, description)
        except Exception as err:
            raise schedulers.SchedulerException('Cannot prepare task description on base of given benchmark.xml: {}'.
                                                format(err))

        self.__track_task(job_id, run, identifier)
        return True

    def _prepare_job(self, identifier, configuration):
        """
        Prepare a working directory before starting the solution.

        :param identifier: Verification task identifier.
        :param configuration: Job configuration.
        :raise SchedulerException: If a job cannot be scheduled or preparation failed.
        """
        # Cannot be called
        raise NotImplementedError("VerifierCloud cannot handle jobs.")

    def _solve_task(self, identifier, description, user, password):
        """
        Solve given verification task.

        :param identifier: Verification task identifier.
        :param description: Verification task description dictionary.
        :param user: User name.
        :param password: Password.
        :return: Return Future object.
        """
        # Submit command
        self.logger.info("Submit the task {0}".format(identifier))
        task = self.__tasks[identifier]
        try:
            return self.wi.submit(run=task.run,
                                  limits=task.run.limits,
                                  cpu_model=task.run.cpu_model,
                                  result_files_pattern='output/**',
                                  priority=task.run.priority,
                                  user_pwd=task.run.user_pwd(user, password),
                                  revision=task.run.branch + ':' + task.run.revision,
                                  meta_information=json.dumps({'Verification tasks produced by Klever': None}))
        except Exception as err:
            raise schedulers.SchedulerException(str(err))

    def _solve_job(self, identifier, configuration):
        """
        Solve given verification job.

        :param identifier: Job identifier.
        :param configuration: Job configuration.
        :return: Return Future object.
        """
        raise NotImplementedError('VerifierCloud cannot start jobs.')

    def _process_task_result(self, identifier, future, description):
        """
        Process result and send results to the server.

        :param identifier: Task identifier string.
        :param future: Future object.
        :return: status of the task after solution: FINISHED.
        :raise SchedulerException: in case of ERROR status.
        """
        run = self.__tasks[identifier]
        self.__drop_task(identifier)

        task_work_dir = os.path.join(self.work_dir, "tasks", identifier)
        solution_file = os.path.join(task_work_dir, "solution.zip")
        self.logger.debug("Save solution to the disk as {}".format(solution_file))
        try:
            result = future.result()
        except Exception as err:
            error_msg = "Task {} has been finished but no data has been received: {}".format(identifier, err)
            self.logger.warning(error_msg)
            raise schedulers.SchedulerException(error_msg)

        # Save result
        with open(solution_file, 'wb') as sa:
            sa.write(result)

        # Unpack results
        task_solution_dir = os.path.join(task_work_dir, "solution")
        self.logger.debug("Make directory for the solution to extract {0}".format(task_solution_dir))
        os.makedirs(task_solution_dir.encode("utf-8"), exist_ok=True)
        self.logger.debug("Extract results from {} to {}".format(solution_file, task_solution_dir))
        shutil.unpack_archive(solution_file, task_solution_dir)
        # Process results and convert RunExec output to result description
        # TODO: what will happen if there will be several input files?
        # Simulate BenchExec behaviour when one input file is provided.
        os.makedirs(os.path.join(task_solution_dir, "output", "benchmark.logfiles").encode("utf-8"), exist_ok=True)
        shutil.move(os.path.join(task_solution_dir, 'output.log'),
                    os.path.join(task_solution_dir, "output", "benchmark.logfiles",
                                 "{}.log".format(os.path.basename(run.run.sourcefiles[0]))))

        try:
            solution_identifier, solution_description = self.__extract_description(task_solution_dir)
            self.logger.debug("Successfully extracted solution {} for task {}".format(solution_identifier, identifier))
        except Exception as err:
            self.logger.warning("Cannot extract results from a solution: {}".format(err))
            raise err

        # Make fake BenchExec XML report
        self.__make_fake_benchexec(solution_description, os.path.join(task_work_dir, 'solution', 'output',
                                   "benchmark.results.xml"))

        # Add actual restrictions
        solution_description['resource limits'] = description["resource limits"]

        # Make archive
        solution_archive = os.path.join(task_work_dir, "solution")
        self.logger.debug("Make archive {} with a solution of the task {}.zip".format(solution_archive, identifier))
        shutil.make_archive(solution_archive, 'zip', task_solution_dir)
        solution_archive += ".zip"

        # Push result
        self.logger.debug("Upload solution archive {} of the task {} to the verification gateway".
                          format(solution_archive, identifier))
        try:
            utils.submit_task_results(self.logger, self.server, self.scheduler_type(), identifier, solution_description,
                                      os.path.join(task_work_dir, "solution"))
        except Exception as err:
            error_msg = "Cannot submit solution results of task {}: {}".format(identifier, err)
            self.logger.warning(error_msg)
            raise schedulers.SchedulerException(error_msg)

        if "keep working directory" not in self.conf["scheduler"] or \
                not self.conf["scheduler"]["keep working directory"]:
            self.logger.debug("Clean task working directory {} for {}".format(task_work_dir, identifier))
            shutil.rmtree(task_work_dir)

        self.logger.debug("Task {} has been processed successfully".format(identifier))
        return "FINISHED"

    def _process_job_result(self, identifier, future):
        """
        Process future object status and send results to the server.

        :param identifier: Job identifier string.
        :param future: Future object.
        :return: status of the job after solution: FINISHED.
        :raise SchedulerException: in case of ERROR status.
        """
        raise NotImplementedError('There cannot be any running jobs in VerifierCloud')

    def _cancel_job(self, identifier, future):
        """
        Stop the job solution.

        :param identifier: Verification task ID.
        :param future: Future object.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: In case of exception occurred in future task.
        """
        raise NotImplementedError('VerifierCloud cannot have running jobs, so they cannot be cancelled')

    def _cancel_task(self, identifier, future):
        """
        Stop the task solution.

        :param identifier: Verification task ID.
        :param future: Future object.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: In case of exception occurred in future task.
        """
        self.logger.debug("Cancel task {}".format(identifier))
        # todo: Implement proper task cancellation
        super(VerifierCloud, self)._cancel_task(identifier, future)
        task_work_dir = os.path.join(self.work_dir, "tasks", identifier)
        shutil.rmtree(task_work_dir)
        self.__drop_task(identifier)

    def __get_credentials(self, job_id):
        """
        Get user credentials from either the server or cache.

        :param job_id: Job identifier.
        """
        if job_id in self.__credentials_cache:
            cred = self.__credentials_cache[job_id]
        else:
            cred = self.server.get_user_credentials(job_id)
            self.__credentials_cache[job_id] = cred
        return cred

    def __extract_description(self, solution_dir):
        """
        Get directory with BenchExec output and extract results from there saving them to JSON file according to
        provided path.

        :param solution_dir: Path with BenchExec output.
        :return: Identifier string of the solution.
        """
        identifier = str(uuid.uuid4())
        description = {
            "id": identifier,
            "resources": {},
            "comp": {}
        }

        # Import description
        desc_file = os.path.join(solution_dir, "runDescription.txt")
        self.logger.debug("Import description from the file {}".format(desc_file))
        description["desc"] = ""
        if os.path.isfile(desc_file):
            with open(desc_file, encoding="utf-8") as di:
                for line in di:
                    key, value = line.strip().split("=")
                    if key == "tool":
                        description["desc"] += value
                    elif key == "revision":
                        description["desc"] += " {}".format(value)
        else:
            raise FileNotFoundError("There is no solution file {}".format(desc_file))

        # Import general information
        general_file = os.path.join(solution_dir, "runInformation.txt")
        self.logger.debug("Import general information from the file {}".format(general_file))
        termination_reason = None
        number = re.compile(r'(\d.*\d)')
        if os.path.isfile(general_file):
            with open(general_file, encoding="utf-8") as gi:
                for line in gi:
                    key, value = line.strip().split("=", maxsplit=1)
                    if key == "terminationreason":
                        termination_reason = value
                    elif key == "command":
                        description["comp"]["command"] = value
                    elif key == "exitsignal":
                        description["signal num"] = int(value)
                    elif key == "exitcode" or key == "returnvalue":
                        description["return value"] = int(value)
                    elif key == "walltime":
                        sec = number.match(value).group(1)
                        if sec:
                            description["resources"]["wall time"] = int(float(sec) * 1000)
                        else:
                            self.logger.warning("Cannot properly extract wall time from {}".format(general_file))
                    elif key == "cputime":
                        sec = number.match(value).group(1)
                        if sec:
                            description["resources"]["CPU time"] = int(float(sec) * 1000)
                        else:
                            self.logger.warning("Cannot properly extract CPU time from {}".format(general_file))
                    elif key == "memory":
                        mem_bytes = number.match(value).group(1)
                        if mem_bytes:
                            description["resources"]["memory size"] = int(mem_bytes)
                        else:
                            self.logger.warning("Cannot properly extract exhausted memory from {}".format(general_file))
                    elif key == "coreLimit":
                        cores = int(value)
                        description["resources"]["coreLimit"] = cores
        else:
            raise FileNotFoundError("There is no solution file {}".format(general_file))

        # Set final status
        if termination_reason:
            if termination_reason == "cputime":
                description["status"] = "TIMEOUT"
            elif termination_reason == "memory":
                description["status"] = 'OUT OF MEMORY'
            else:
                raise ValueError("Unsupported termination reason {}".format(termination_reason))
        elif "signal num" in description:
            description["status"] = "killed by signal"
        elif "return value" in description:
            if description["return value"] == 0:
                if glob.glob(os.path.join(solution_dir, "output", "witness.*.graphml")):
                    description["status"] = "false"
                else:
                    # Check that soft limit has not activated
                    failed = self.__check_verifiers_log(
                        glob.glob(os.path.join(os.path.abspath(os.path.join(solution_dir, 'output',
                                                                            'benchmark.logfiles', '*.log')))))
                    if failed:
                        description["status"] = "unknown"
                    else:
                        description["status"] = "true"
            else:
                description["status"] = "unknown"
        else:
            raise ValueError("Cannot determine termination reason according to the file {}".format(general_file))

        # Import Host information
        host_file = os.path.join(solution_dir, "hostInformation.txt")
        self.logger.debug("Import host information from the file {}".format(host_file))
        lv_re = re.compile(r'Linux\s(\d.*)')
        if os.path.isfile(host_file):
            with open(host_file, encoding="utf-8") as hi:
                for line in hi:
                    key, value = line.strip().split("=", maxsplit=1)
                    if key == "name":
                        description["comp"]["node name"] = value
                    elif key == "os":
                        version = lv_re.match(value).group(1)
                        if version:
                            description["comp"]["Linux kernel version"] = version
                        else:
                            self.logger.warning("Cannot properly extract Linux kernel version from {}".
                                                format(host_file))
                    elif key == "memory":
                        description["comp"]["mem size"] = value
                    elif key == "cpuModel":
                        description["comp"]["CPU model"] = value
                    elif key == "cores":
                        description["comp"]["number of CPU cores"] = value
        else:
            raise FileNotFoundError("There is no solution file {}".format(host_file))

        return identifier, description

    def __check_verifiers_log(self, logs):
        for file in logs:
            with open(file, 'r', encoding='utf-8') as stream:
                for line in stream.readlines():
                    if re.search(r'Verification result: UNKNOWN', line):
                        return True
        else:
            return False

    def __track_task(self, job_id, run, task_id):
        """
        Start tracking a new task.

        :param job_id: Job identifier
        :param run: Run object
        :param task_id: Task identifier
        """
        Task = collections.namedtuple('Task', ('job', 'run'))
        self.__tasks[task_id] = Task(job_id, run)

    def __drop_task(self, task_id):
        """
        Stop tracking task if it is finished, cancelled or failed.

        :param task_id: task identifier.
        """
        if task_id in self.__tasks:
            job_id = self.__tasks[task_id].job
            del self.__tasks[task_id]

            if not any(t for t in self.__tasks.values() if t.job == job_id):
                # There is no more tasks with the same job identifier and we can try to drop user credentials
                del self.__credentials_cache[job_id]

    @staticmethod
    def __make_fake_benchexec(description, path):
        """
        Save a fake BenchExec report. If you need to add an additional information to the XML file then add it here.

        :param description: Description dictionary extracted from VerifierCloud TXT files.
        :return: None
        """
        result = ET.Element("result", {
            "benchmarkname": "benchmark"
        })
        run = ET.SubElement(result, "run")
        ET.SubElement(run, "column", {
            'title': 'status',
            'value': str(description['status'])
        })
        ET.SubElement(run, "column", {
            'title': 'exitcode',
            'value': str(description['return value']) if 'return value' in description else None
        })

        with open(path, "w", encoding="utf-8") as fp:
            fp.write(minidom.parseString(ET.tostring(result)).toprettyxml(indent="    "))
