#!/usr/bin/python3
import os
import json
import Cloud.utils as utils
import Cloud.utils.omega as omega


def main():
    expect_file = os.environ["CONTROLLER_NODE_CONFIG"]
    with open(expect_file) as fh:
        conf = json.load(fh)

    # Sign in
    session = omega.Session(conf["Omega"]["name"], conf["Omega"]["user"], conf["Omega"]["password"])

    # Submit scheduler status
    status = {
        "VerifierCloud": "DISCONNECTED",
        "Klever": "DISCONNECTED"
    }

    a = utils.get_output("ps -aux | grep -F \"klever-scheduler.py\" ")
    ks_out = int(utils.get_output("ps -aux | grep -F \"klever-scheduler.py\" -c"))
    if ks_out > 2:
        status["Klever"] = "HEALTHY"
    vc_out = int(utils.get_output("ps -aux | grep -F \"verifiercloud-scheduler.py\" -c"))
    if vc_out > 2:
        status["VerifierCloud"] = "HEALTHY"

    data = {
        "statuses": json.dumps(status)
    }

    session.json_exchange("service/set_schedulers_status/", data)

    # Sign out
    session.sign_out()

if __name__ == '__main__':
    main()

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
