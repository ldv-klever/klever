#!/usr/bin/python3
import os
import json
import consulate
import logging


def main():
    expect_file = os.environ["CONTROLLER_NODE_CONFIG"]
    logging.info("Configuration file: {}".format(expect_file))
    with open(expect_file) as fh:
        node_conf = json.load(fh)

    # Submit content
    session = consulate.Consul()
    session.kv["states/{}".format(node_conf["node configuration"]["node name"])] = json.dumps(node_conf)
    exit(0)

if __name__ == '__main__':
    main()

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'