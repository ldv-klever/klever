#!/usr/bin/python3
import os


def main():
    expect_file = os.path.join("node configuration.json")
    print("Looking for a file {}".format(expect_file))
    if os.path.isfile(expect_file):
        exit(0)
    else:
        exit(2)

if __name__ == '__main__':
    main()

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
