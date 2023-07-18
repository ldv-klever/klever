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
MIN_CPU_COUNT = 0
MAX_ITERATIONS = 30
temp_prev_val = 0
iterations = 0


def reserve_workers_cpu_cores(val: int):
    global temp_prev_val
    if val == temp_prev_val:
        return
    if val > MAX_CPU_CORES:
        # Do not reserve more cores than physically available.
        val = MAX_CPU_CORES
    elif val <= MIN_CPU_COUNT:
        val = MIN_CPU_COUNT
    temp_prev_val = val
    with open(WORKERS_CPU_CORES_TMP_FILE, "wb") as fd:
        fd.write(struct.pack("b", val))


def get_workers_cpu_cores() -> int:
    global iterations, temp_prev_val
    if iterations:
        iterations += 1
        if iterations == MAX_ITERATIONS:
            iterations = 0
    elif os.path.exists(WORKERS_CPU_CORES_TMP_FILE):
        with open(WORKERS_CPU_CORES_TMP_FILE, "rb") as fd:
            temp_prev_val = struct.unpack('b', fd.read(1))[0]
    else:
        temp_prev_val = 0
    return temp_prev_val


def clear_workers_cpu_cores():
    if os.path.exists(WORKERS_CPU_CORES_TMP_FILE):
        os.unlink(WORKERS_CPU_CORES_TMP_FILE)
