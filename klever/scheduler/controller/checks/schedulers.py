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
import json
import subprocess
import logging
import sys

from klever.scheduler.utils import bridge
from klever.scheduler.utils import consul


def set_status(logger, st, conf):
    session = bridge.Session(logger, conf["Klever Bridge"]["name"], conf["Klever Bridge"]["user"],
                             conf["Klever Bridge"]["password"])

    for scheduler, status in st.items():
        session.json_exchange("service/scheduler/{0}/".format(scheduler), data={'status': status}, method='PATCH')


def main():
    expect_file = os.environ["CONTROLLER_NODE_CONFIG"]
    with open(expect_file, encoding="utf-8") as fh:
        conf = json.load(fh)

    # Sign in
    consul_client = consul.Session()

    # Update scheduler status
    status = {
        "VerifierCloud": "DISCONNECTED",
        "Klever": "DISCONNECTED"
    }

    ks_out = subprocess.getoutput('ps -aux | grep [n]ative-scheduler')
    if ks_out and ks_out != '':
        status["Klever"] = "HEALTHY"
    vc_out = subprocess.getoutput('ps -aux | grep [v]erifiercloud-scheduler')
    if vc_out and vc_out != '':
        status["VerifierCloud"] = "HEALTHY"

    # Check the last submit
    schedulers = consul_client.kv_get("schedulers")
    if schedulers:
        schedulers = json.loads(schedulers)
        if schedulers["Klever"] != status["Klever"] or schedulers["VerifierCloud"] != status["VerifierCloud"]:
            set_status(logging, status, conf)
            consul_client.kv_put("schedulers", json.dumps(status, ensure_ascii=False, sort_keys=True, indent=4))
    else:
        try:
            consul_client.kv_put("schedulers", json.dumps(status, ensure_ascii=False, sort_keys=True, indent=4))
        except (AttributeError, KeyError):
            print('Key-value storage is not ready yet')
            sys.exit(1)
        set_status(logging, status, conf)

    # Sign out
    sys.exit(0)


if __name__ == "__main__":
    main()
