#!/usr/bin/env python3
import json
import argparse

import Cloud.utils as utils
import Cloud.client as client


if __name__ == "__main__":
    # Parse configuration
    parser = argparse.ArgumentParser(description='Start cloud Klever scheduler client according to the provided '
                                                 'configuration.')
    parser.add_argument('mode', metavar="MODE", help='TASK or JOB.')
    parser.add_argument('conf', metavar="CONF", help='JSON string with all necessary configuration.')
    args = parser.parse_args()

    if args.mode == "JOB":
        conf = json.loads(args.conf)
        conf = utils.common_initialization("Client controller", conf)
        client.solve_job(conf)
    elif args.mode == "TASK":
        exit(0)
    else:
        NotImplementedError("Provided mode {} is not supported by the client".format(args.mode))

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
