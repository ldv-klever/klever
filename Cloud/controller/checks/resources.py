#!/usr/bin/python3
import os
import json
import consul


def main():
    expect_file = os.path.join("node configuration.json")
    with open(expect_file) as fh:
        node_conf = json.load(fh)

    # Submit content
    c = consul.Consul()
    ret = c.kv.put("states/{}".format(node_conf["node name"]), json.dumps(node_conf))
    if not ret:
        print("Submission failed")
        exit(2)

if __name__ == '__main__':
    main()

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'