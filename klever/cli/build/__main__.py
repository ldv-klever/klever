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
import configparser
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
        desc_paths = [x for x in desc_paths if desc_name_pattern + '/' in os.path.relpath(x, get_descs_dir())]

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
    """Find a subclass of Program class."""
    for program_class in get_all_subclasses(Program):
        if class_name == program_class.__name__:
            return program_class
    raise NotImplementedError(f'Can not find "{class_name}" class')


def import_build_modules():
    # Dynamically import all Python modules in the current directory
    for path in pathlib.Path(os.path.dirname(__file__)).glob('*.py'):
        module_name = '.' + os.path.splitext(os.path.basename(path))[0]
        importlib.import_module(module_name, 'klever.cli.build')


def add_cif_and_cross_build_tools_to_path(logger):
    # klever-build (Clade) requires CIF and cross CIFs. Besides, it has sense to use corresponding cross build tools for
    # normal build processes. So, add everything required to PATH.
    # Here we rely on the Klever installation and make some assumptions regarding it as well as regarding arrangement of
    # CIF binaries. Correspondingly, let's try to mitigate various issues that can happen with this.

    def_warn_msg = 'you should provide necessary CIF, cross CIFs and cross build tools via PATH yourself'

    # Try to get Klever deployment directory.
    if not os.path.isfile('/etc/default/klever'):
        logger.warning('Klever deployment settings file "/etc/default/klever" does not exist ({0})'
                       .format(def_warn_msg))
        return

    klever_deploy_settings = configparser.ConfigParser()
    with open('/etc/default/klever') as fp:
        # Add stub section to look like normal INI file.
        klever_deploy_settings.read_string('[root]\n' + fp.read())

    if 'KLEVER_DEPLOYMENT_DIRECTORY' not in klever_deploy_settings['root']:
        logger.warning('Could not determine Klever deployment directory ({0})'.format(def_warn_msg))
        return

    # Truncate double quotes around the setting value.
    klever_deploy_dir = klever_deploy_settings['root']['KLEVER_DEPLOYMENT_DIRECTORY'][1:-1]
    logger.info('Klever deployment directory is "{0}"'.format(klever_deploy_dir))

    klever_deploy_conf_file = os.path.join(klever_deploy_dir, 'klever.json')
    if not os.path.isfile(klever_deploy_conf_file):
        logger.warning('Klever deployment configuration file "{0}" does not exist ({1})'
                       .format(klever_deploy_conf_file, def_warn_msg))
        return

    with open(klever_deploy_conf_file) as fp:
        klever_deploy_conf = json.load(fp)

    if 'Klever Addons' not in klever_deploy_conf:
        logger.warning('Klever deployment configuration file "{0}" does not describe any Klever addon ({1})'
                       .format(klever_deploy_conf_file, def_warn_msg))
        return

    klever_addons = klever_deploy_conf['Klever Addons']
    dirs_to_path = []
    for name, desc in klever_addons.items():
        if 'version' in desc:
            dirs_to_path.append(os.path.join(klever_deploy_dir, 'klever-addons', name,
                                             desc['executable path'] if 'executable path' in desc else ''))

    if not dirs_to_path:
        logger.warning('Klever deployment configuration file "{0}" does not describe Klever addons at top level ({1})'
                       .format(klever_deploy_conf_file, def_warn_msg))
        return

    # Determine directories of cross build tools to be added to PATH as real directories of Aspectator (GCC) binaries.
    # Don't consider non-cross build tools since various versions of GCC are necessary to build all testing and
    # validation build bases (in this case Aspectator binary does not have any prefix - it is exactly "aspectator").
    cross_build_tool_dirs = []
    for dir_to_path in dirs_to_path:
        for dirpath, _, filenames in os.walk(dir_to_path):
            for filename in filenames:
                if filename.endswith('-aspectator') and os.path.islink(os.path.join(dirpath, filename)):
                    cross_build_tool_dirs.append(os.path.dirname(os.path.realpath(os.path.join(dirpath, filename))))

    logger.info('Add following directories to PATH:\n{0}'
                .format('\n'.join(['  {0}'.format(d) for d in dirs_to_path + cross_build_tool_dirs])))

    for d in dirs_to_path + cross_build_tool_dirs:
        os.environ["PATH"] = "{}:{}".format(d, os.environ["PATH"])


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
        help='path to the directory that contains all required git repositories (linux-stable, userspace)',
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


def main(args=sys.argv[1:]): # pylint: disable=dangerous-default-value
    logger = get_logger(__name__)
    args = parse_args(args, logger)
    all_desc_paths = []

    for desc_name_pattern in args.descriptions:
        desc_paths = get_desc_paths(desc_name_pattern)
        all_desc_paths.extend(desc_paths)

        if not desc_paths:
            logger.error('There are no JSONs corresponding to the specified description pattern %s', desc_name_pattern)
            logger.error('Target program descriptions are stored in the %s directory', get_descs_dir())
            sys.exit(-1)

    import_build_modules()
    add_cif_and_cross_build_tools_to_path(logger)

    for desc_path in all_desc_paths:
        with open(desc_path, 'r', encoding='utf-8') as fp:
            descs = json.load(fp)

        logger.info('Use "%s" description', get_desc_name(desc_path))
        for desc in descs:
            desc['description directory'] = os.path.dirname(desc_path)
            desc['build base'] = os.path.abspath(os.path.join(args.output, desc['build base']))

            if "GCC 4.6 Clade CIF options" in desc:
                desc.update(gcc46_clade_cif_opts)

            logger.info('Prepare build base "%s"', desc['build base'])

            common_desc = dict(common_target_program_descs[desc['name']])
            common_desc.update(desc)
            common_desc['source code'] = os.path.abspath(os.path.join(args.repositories, common_desc['source code']))

            ProgramClass = get_program_class(desc['name'])
            ProgramObj = ProgramClass(logger, common_desc)
            ProgramObj.build()

            logger.info('Build base "%s" was successfully prepared', desc['build base'])


if __name__ == '__main__':
    main()
