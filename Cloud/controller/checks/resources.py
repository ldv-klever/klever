#!/usr/bin/python3
import os
import json
import consulate


def main():
    expect_file = os.path.join("node configuration.json")
    with open(expect_file) as fh:
        node_conf = json.load(fh)

    # Submit content
    session = consulate.Consul()
    session.kv["states/{}".format(node_conf["node name"])] = json.dumps(node_conf)
    exit(0)

if __name__ == '__main__':
    main()

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'