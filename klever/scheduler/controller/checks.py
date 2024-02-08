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

import os
import time
import json
import logging
import subprocess
import sys

from klever.scheduler.utils import consul, bridge


def set_data(consul_client, conf):
    try:
        consul_client.kv_put("states/{}".format(conf["node configuration"]["node name"]),
                             json.dumps(conf["node configuration"], ensure_ascii=False, sort_keys=True, indent=4))
    except (AttributeError, KeyError):
        print("Key-value storage is inaccessible")


def set_status(logger, st, conf):
    session = bridge.Session(logger, conf["Klever Bridge"]["name"], conf["Klever Bridge"]["user"],
                             conf["Klever Bridge"]["password"])
    logging.info("Consul set status")
    for scheduler, status in st.items():
        session.json_exchange("service/scheduler/{0}/".format(scheduler), data={'status': status}, method='PATCH')


def get_schedulers_status():
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

    return status


def local_scheduler_checks(conf):
    old_status = {
        "VerifierCloud": "DISCONNECTED",
        "Klever": "DISCONNECTED"
    }

    while True:
        status = get_schedulers_status()

        if status != old_status:
            # Update scheduler status
            set_status(logging, status, conf)
            old_status = status

        time.sleep(5)


def schedulers_checks(conf):
    # Sign in
    consul_client = consul.Session()
    # Update scheduler status
    status = get_schedulers_status()
    logging.info("Consul scheduler checks")

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


def resources_checks(node_conf, expect_file):
    # Check content
    consul_client = consul.Session()
    data = consul_client.kv_get("states/{}".format(node_conf["node configuration"]["node name"]))
    if data:
        # Check last modification data
        secs_since_diff = int(time.time() - os.path.getmtime(expect_file))

        if secs_since_diff < 30:
            set_data(consul_client, node_conf)
    else:
        set_data(consul_client, node_conf)

    return True


def main():
    expect_file = os.environ["CONTROLLER_NODE_CONFIG"]
    logging.info("Configuration file: %s", expect_file)

    if not os.path.isfile(expect_file):
        sys.exit(2)

    # Read node configuration
    with open(expect_file, encoding="utf-8") as fh:
        conf = json.load(fh)

    resources_checks(conf, expect_file)
    schedulers_checks(conf)

    sys.exit(0)


if __name__ == "__main__":
    main()
