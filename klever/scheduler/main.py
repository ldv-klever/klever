# Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
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

from klever.scheduler import controller
from klever.scheduler.schedulers import debug
from klever.scheduler.schedulers import native
from klever.scheduler.schedulers import verifiercloud
from klever.scheduler import utils

from klever.scheduler.schedulers import Scheduler
from klever.scheduler.controller.checks import local_scheduler_checks


def client_controller():
    # Parse configuration
    conf, logger = utils.common_initialization("Client controller")

    # Check config
    if "client-controller" not in conf:
        raise KeyError("Provide configuration property 'client-controller' as a JSON-object")
    if "node configuration" not in conf:
        raise KeyError("Provide configuration property 'node configuration' as a JSON-object")

    if conf["client-controller"].get("type", "local") == "local":
        local_scheduler_checks(conf['Klever Bridge'])
    elif conf["client-controller"]["type"] == "consul":
        # Setup consul
        consul_work_dir, consul_config_file = controller.setup_consul(conf, logger)

        # Run consul
        controller.run_consul(conf, logger, consul_work_dir, consul_config_file)
    else:
        raise KeyError("Unknown client controller type: {}".format(conf["client-controller"]["type"]))


def debug_scheduler():
    conf, logger = utils.common_initialization("Klever scheduler")
    scheduler_impl = Scheduler(conf, logger, "scheduler/", debug.Debug)
    scheduler_impl.launch()


def native_scheduler():
    conf, logger = utils.common_initialization("Klever scheduler")
    scheduler_impl = Scheduler(conf, logger, "scheduler/", native.Native)
    scheduler_impl.launch()


def verifiercloud_scheduler():
    conf, logger = utils.common_initialization("VerifierCloud scheduler")
    scheduler_impl = Scheduler(conf, logger, "VerifierCloud scheduler/",
                               verifiercloud.VerifierCloud)
    scheduler_impl.launch()
