#!/usr/bin/env python3
import Cloud.utils as utils
import Cloud.schedulers.native as native


if __name__ == "__main__":
    conf = utils.common_initialization("Klever scheduler")

    if "scheduler" not in conf:
        raise KeyError("Provide configuration property 'scheduler' as an JSON-object")
    if "Omega" not in conf:
        raise KeyError("Provide configuration property 'scheduler' as an JSON-object")

    scheduler_impl = native.Scheduler(conf, conf["common"]["work dir"] + "/scheduler/")
    scheduler_impl.launch()

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
