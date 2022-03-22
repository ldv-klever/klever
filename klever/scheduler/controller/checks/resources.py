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

import klever.scheduler.utils.consul as consul


def set_data(consul_client, conf):
    try:
        consul_client.kv_put("states/{}".format(conf["node configuration"]["node name"]),
                             json.dumps(conf["node configuration"], ensure_ascii=False, sort_keys=True, indent=4))
    except (AttributeError, KeyError):
        print("Key-value storage is inaccessible")
        exit(2)


def main():
    expect_file = os.environ["CONTROLLER_NODE_CONFIG"]
    logging.info("Configuration file: {}".format(expect_file))

    # Read node configuration
    with open(expect_file, encoding="utf-8") as fh:
        node_conf = json.load(fh)

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

    exit(0)


if __name__ == "__main__":
    main()
