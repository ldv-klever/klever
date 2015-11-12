#!/usr/bin/env python3
import Cloud.scheduler as scheduler
import Cloud.utils as utils

if __name__ == "__main__":
    conf = utils.common_initialization("VerifierCloud scheduler")

    if "scheduler" not in conf:
        raise KeyError("Provide configuration property 'scheduler' as an JSON-object")
    if "Omega" not in conf:
        raise KeyError("Provide configuration property 'scheduler' as an JSON-object")

    session = scheduler.get_gateway(conf, conf["common"]["work dir"] + "/requests/")
    scheduler_impl = scheduler.get_scheduler(conf["scheduler"], conf["common"]["work dir"] + "/scheduler/", session)
    scheduler_impl.launch()

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'