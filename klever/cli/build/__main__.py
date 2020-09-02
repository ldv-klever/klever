# Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import importlib
import json
import os
import pathlib
import sys


from klever.cli.utils import get_logger
from klever.cli.descs import common_target_program_descs, gcc46_clade_cif_opts
from klever.cli.build.program import Program


def get_descs_dir():
    return os.path.join(os.path.dirname(__file__), '..', 'descs')


def get_desc_paths(desc_name_pattern=None):
    desc_paths = []

    for desc_path in pathlib.Path.rglob(pathlib.Path(get_descs_dir()), "desc.json"):
        desc_paths.append(str(desc_path))

    if desc_name_pattern:
        desc_paths = [x for x in desc_paths if desc_name_pattern in os.path.relpath(x, get_descs_dir())]

    return desc_paths


def get_desc_name(desc_path):
    return os.path.dirname(os.path.relpath(desc_path, start=get_descs_dir()))


def get_all_desc_names():
    # Get names of all json files with target program descriptions (without .json extension)
    desc_names = []

    for desc_path in get_desc_paths():
        desc_names.append(get_desc_name(desc_path))

    return desc_names


def get_all_subclasses(cls):
    """Get all subclasses of Program class."""

    for subclass in cls.__subclasses__():
        yield subclass
        yield from get_all_subclasses(subclass)


def get_program_class(class_name):
    """Find a subclass of Programm class."""
    for program_class in get_all_subclasses(Program):
        if class_name == program_class.__name__:
            return program_class
    else:
        raise NotImplementedError(f'Can not find "{class_name}" class')


def import_build_modules():
    # Dynamically import all Python modules in the current directory
    for path in pathlib.Path(os.path.dirname(__file__)).glob('*.py'):
        module_name = '.' + os.path.splitext(os.path.basename(path))[0]
        importlib.import_module(module_name, 'klever.cli.build')


def parse_args(args, logger):
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-o',
        '--output',
        help='path to the directory where build bases will be stored. Default: {!r}'.format('build bases'),
        default='build bases',
        metavar='PATH'
    )

    parser.add_argument(
        '-r',
        '--repositories',
        help='path to the directory that contains all required git repositorues (linux-stable, userspace)',
        default='.',
        metavar='PATH'
    )

    parser.add_argument(
        '-l',
        '--list',
        help='show the list of available target program descriptions and exit',
        action='store_true'
    )

    parser.add_argument(
        dest='descriptions',
        nargs=argparse.REMAINDER,
        help='list of descriptions to use',
    )

    args = parser.parse_args(args)

    if args.list:
        logger.info('Available target program descriptions:\n{}'.format(
            '\n'.join(sorted(get_all_desc_names()))
        ))
        sys.exit()

    if not args.descriptions:
        logger.error('You need to specify at least one target program description')
        sys.exit(-1)

    return args


def main(args=sys.argv[1:]):
    logger = get_logger(__name__)
    args = parse_args(args, logger)
    all_desc_paths = []

    for desc_name_pattern in args.descriptions:
        desc_paths = get_desc_paths(desc_name_pattern)
        all_desc_paths.extend(desc_paths)

        if not desc_paths:
            logger.error(f'There are no jsons corresponding to the specified description pattern {desc_name_pattern}')
            logger.error(f'Target program descriptions are stored in the {get_descs_dir()} directory')
            sys.exit(-1)

    import_build_modules()

    for desc_path in all_desc_paths:
        with open(desc_path, 'r', encoding='utf-8') as fp:
            descs = json.load(fp)

        logger.info(f'Use "{get_desc_name(desc_path)}" description')
        for desc in descs:
            desc['description directory'] = os.path.dirname(desc_path)
            desc['build base'] = os.path.abspath(os.path.join(args.output, desc['build base']))

            if "GCC 4.6 Clade CIF options" in desc:
                desc.update(gcc46_clade_cif_opts)

            logger.info('Prepare build base "{}"'.format(desc['build base']))

            common_desc = dict(common_target_program_descs[desc['name']])
            common_desc.update(desc)
            common_desc['source code'] = os.path.abspath(os.path.join(args.repositories, common_desc['source code']))

            ProgramClass = get_program_class(desc['name'])
            ProgramObj = ProgramClass(logger, common_desc)
            ProgramObj.build()

            logger.info('Build base "{}" was successfully prepared'.format(desc['build base']))


if __name__ == '__main__':
    main()
