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

import glob
import logging
import uuid
import re
import os
import json
import subprocess
import queue
import threading
import time


class CommandError(ChildProcessError):
    pass


class StreamQueue:
    def __init__(self, stream, stream_name, collect_all_output=False):
        self.stream = stream
        self.stream_name = stream_name
        self.collect_all_output = collect_all_output
        self.queue = queue.Queue()
        self.finished = False
        self.traceback = None
        self.thread = threading.Thread(target=self.__put_lines_from_stream_to_queue)
        self.output = []

    def get(self):
        try:
            return self.queue.get_nowait()
        except queue.Empty:
            return None

    def join(self):
        self.thread.join()

    def start(self):
        self.thread.start()

    def __put_lines_from_stream_to_queue(self):
        try:
            # This will put lines from stream to queue until stream will be closed. For instance it will happen when
            # execution of command will be completed.
            for line in self.stream:
                line = line.decode('utf8').rstrip()
                self.queue.put(line)
                if self.collect_all_output:
                    self.output.append(line)

            # Nothing will be put to queue from now.
            self.finished = True
        except Exception:
            import traceback
            self.traceback = traceback.format_exc().rstrip()


def execute(logger, args, env=None, cwd=None, timeout=0, collect_all_stdout=False):
    cmd = args[0]
    logger.debug('Execute:\n{0}{1}{2}'.format(cmd,
                                              '' if len(args) == 1 else ' ',
                                              ' '.join('"{0}"'.format(arg) for arg in args[1:])))

    p = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)

    out_q, err_q = (StreamQueue(p.stdout, 'STDOUT', collect_all_stdout), StreamQueue(p.stderr, 'STDERR', True))

    for stream_q in (out_q, err_q):
        stream_q.start()

    # Print to logs everything that is printed to STDOUT and STDERR each timeout seconds. Last try is required to
    # print last messages queued before command finishes.
    last_try = True
    while not out_q.finished or not err_q.finished or last_try:
        if out_q.traceback:
            raise RuntimeError('STDOUT reader thread failed with the following traceback:\n{0}'. format(out_q.traceback))
        if err_q.traceback:
            raise RuntimeError('STDERR reader thread failed with the following traceback:\n{0}'. format(err_q.traceback))
        last_try = not out_q.finished or not err_q.finished
        time.sleep(timeout)

        for stream_q in (out_q, err_q):
            output = []
            while True:
                line = stream_q.get()
                if line is None:
                    break
                output.append(line)
            if output:
                m = '"{0}" outputted to {1}:\n{2}'.format(cmd, stream_q.stream_name, '\n'.join(output))
                if stream_q is out_q:
                    logger.debug(m)
                else:
                    logger.warning(m)

    for stream_q in (out_q, err_q):
        stream_q.join()

    if p.poll():
        logger.error('"{0}" exitted with "{1}"'.format(cmd, p.poll()))
        with open('problem desc.txt', 'a', encoding='utf8') as fp:
            fp.write('\n'.join(err_q.output))
        raise CommandError('"{0}" failed'.format(cmd))

    return p.returncode


def extract_description(solution_dir, description_file):
    """
    Get directory with BenchExec output and extract results from there saving them to JSON file according to provided
    path.
    :param solution_dir: Path with BenchExec output.
    :param description_file:  Path to the description JSON file to save.
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
    logging.debug("Import description from the file {}".format(desc_file))
    description["desc"] = ""
    if os.path.isfile(desc_file):
        with open(desc_file, encoding="utf8") as di:
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
    logging.debug("Import general information from the file {}".format(general_file))
    termination_reason = None
    number = re.compile("(\d.*\d)")
    if os.path.isfile(general_file):
        with open(general_file, encoding="utf8") as gi:
            for line in gi:
                key, value = line.strip().split("=", maxsplit=1)
                if key == "terminationreason":
                    termination_reason = value
                elif key == "command":
                    description["comp"]["command"] = value
                elif key == "exitsignal":
                    description["signal num"] = int(value)
                elif key == "returnvalue":
                    description["return value"] = int(value)
                elif key == "walltime":
                    sec = number.match(value).group(1)
                    if sec:
                        description["resources"]["wall time"] = int(float(sec) * 1000)
                    else:
                        logging.warning("Cannot properly extract wall time from {}".format(general_file))
                elif key == "cputime":
                    sec = number.match(value).group(1)
                    if sec:
                        description["resources"]["CPU time"] = int(float(sec) * 1000)
                    else:
                        logging.warning("Cannot properly extract CPU time from {}".format(general_file))
                elif key == "memory":
                    mem_bytes = number.match(value).group(1)
                    if mem_bytes:
                        description["resources"]["memory size"] = int(mem_bytes)
                    else:
                        logging.warning("Cannot properly extract exhausted memory from {}".format(general_file))
    else:
        raise FileNotFoundError("There is no solution file {}".format(general_file))

    # Set final status
    if termination_reason:
        if termination_reason == "cputime":
            description["status"] = "CPU time exhausted"
        elif termination_reason == "memory":
            description["status"] = "memory exhausted"
        else:
            raise ValueError("Unsupported termination reason {}".format(termination_reason))
    elif "signal num" in description:
        description["status"] = "killed by signal"
    elif "return value" in description:
        if description["return value"] == 0:
            if glob.glob(os.path.join(solution_dir, "output", "witness.*.graphml")):
                description["status"] = "unsafe"
            else:
                description["status"] = "safe"
        else:
            description["status"] = "error"
    else:
        raise ValueError("Cannot determine termination reason according to the file {}".format(general_file))

    # Import Host information
    host_file = os.path.join(solution_dir, "hostInformation.txt")
    logging.debug("Import host information from the file {}".format(host_file))
    lv_re = re.compile("Linux\s(\d.*)")
    if os.path.isfile(host_file):
        with open(host_file, encoding="utf8") as hi:
            for line in hi:
                key, value = line.strip().split("=", maxsplit=1)
                if key == "name":
                    description["comp"]["node name"] = value
                elif key == "os":
                    version = lv_re.match(value).group(1)
                    if version:
                        description["comp"]["Linux kernel version"] = version
                    else:
                        logging.warning("Cannot properly extract Linux kernel version from {}".format(host_file))
                elif key == "memory":
                    description["comp"]["mem size"] = value
                elif key == "cpuModel":
                    description["comp"]["CPU model"] = value
                elif key == "cores":
                    description["comp"]["number of CPU cores"] = value
    else:
        raise FileNotFoundError("There is no solution file {}".format(host_file))

    # Save description
    logging.debug("Save solution description to the file {}".format(description_file))
    with open(description_file, "w", encoding="utf8") as df:
        df.write(json.dumps(description, ensure_ascii=False, sort_keys=True, indent=4))

    return identifier, description

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
