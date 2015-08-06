#!/usr/bin/python3

import os
import tarfile

import psi.utils

conf = None
logger = None


def get_callbacks():
    logger.debug('Have not any callbacks yet')


def launch():
    logger.info('Prepare Linux kernel working source tree "linux"')
    with tarfile.open(psi.utils.find_file(logger, conf['root id'], conf['Linux kernel']['src'])) as TarFile:
        TarFile.extractall(os.path.join(conf['root id'], 'linux'))
