#
# Copyright (c) 2023 ISP RAS (http://www.ispras.ru)
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

import multiprocessing
import os
import struct

WORKERS_CPU_CORES_TMP_FILE = os.path.join("/", "tmp", ".klever_global_workers_cpu_cores")
MAX_CPU_CORES = multiprocessing.cpu_count()
GLOBAL_LOCK = multiprocessing.Lock()
MIN_CPU_COUNT = 0
MAX_ITERATIONS = 30
current_reserved_cores_in_vtg = 0
current_reserved_cores_in_scheduler = 0
iterations = 0


def reserve_workers_cpu_cores(val: int):
    global current_reserved_cores_in_vtg
    if val == current_reserved_cores_in_vtg:
        return
    if val > MAX_CPU_CORES:
        # Do not reserve more cores than physically available.
        val = MAX_CPU_CORES
    elif val <= MIN_CPU_COUNT:
        val = MIN_CPU_COUNT
    current_reserved_cores_in_vtg = val
    # TODO: replace file based synchronization (see issue #39)
    GLOBAL_LOCK.acquire()
    with open(WORKERS_CPU_CORES_TMP_FILE, "wb") as fd:
        fd.write(struct.pack("b", val))
    GLOBAL_LOCK.release()


def get_workers_cpu_cores() -> int:
    global iterations, current_reserved_cores_in_scheduler
    if iterations > 0:
        # In order to optimize reading of the global file, we reuse previous value for MAX_ITERATIONS.
        iterations += 1
        if iterations == MAX_ITERATIONS:
            iterations = 0
        return current_reserved_cores_in_scheduler
    iterations = 1
    GLOBAL_LOCK.acquire()
    if os.path.exists(WORKERS_CPU_CORES_TMP_FILE):
        try:
            with open(WORKERS_CPU_CORES_TMP_FILE, "rb") as fd:
                current_reserved_cores_in_scheduler = struct.unpack('b', fd.read(1))[0]
        except Exception:  # pylint:disable=broad-exception-caught
            # In case the original file was somehow changed, we still do not except to fail here.
            current_reserved_cores_in_scheduler = 0
    else:
        current_reserved_cores_in_scheduler = 0
    GLOBAL_LOCK.release()
    return current_reserved_cores_in_scheduler


def clear_workers_cpu_cores():
    GLOBAL_LOCK.acquire()
    if os.path.exists(WORKERS_CPU_CORES_TMP_FILE):
        os.unlink(WORKERS_CPU_CORES_TMP_FILE)
    GLOBAL_LOCK.release()
