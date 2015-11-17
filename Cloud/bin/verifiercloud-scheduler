#!/usr/bin/env python3
import Cloud.schedulers.verifiercloud as verifiercloud
import Cloud.utils as utils

if __name__ == "__main__":
    conf = utils.common_initialization("VerifierCloud scheduler")

    if "scheduler" not in conf:
        raise KeyError("Provide configuration property 'scheduler' as an JSON-object")
    if "Omega" not in conf:
        raise KeyError("Provide configuration property 'scheduler' as an JSON-object")

    scheduler_impl = verifiercloud.Scheduler(conf, conf["common"]["working directory"] + "/scheduler/")
    scheduler_impl.launch()

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'