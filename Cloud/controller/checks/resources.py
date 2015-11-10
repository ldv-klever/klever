#!/usr/bin/python3
import os
import json
import requests


def main():
    expect_file = os.path.join("node configuration.json")
    with open(expect_file) as fh:
        node_conf = json.load(fh)

    # Submit content
    try:
        result = requests.put("http://localhost:8500/v1/kv/states/{}".format(node_conf["node name"]),
                              json.dumps(node_conf))
    except Exception as err:
        print("Catched exception: {}".format(err))
        exit(2)

    if result.status_code == requests.codes.ok:
        exit(0)
    else:
        exit(1)

if __name__ == '__main__':
    main()

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'