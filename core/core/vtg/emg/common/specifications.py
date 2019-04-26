#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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
#

import re
import os
import glob
import ujson

from core.vtg.utils import find_file_or_dir
from core.vtg.emg.common import get_necessary_conf_property


def get_specs(logger, conf, directory, specification_kinds):
    """
    Get specification kinds descriptions and parse all JSON files separating them on the base of markets in
    specification kinds.

    :param logger:
    :param conf:
    :param directory:
    :param specification_kinds:
    :return:
    """
    logger.info('Search for various EMG generators specifications in {}'.format(directory))
    # Find all json files
    file_candidates = set()
    for root, dirs, files in os.walk(directory):
        # Check only full paths to files
        json_files = glob.glob('{}/*.json'.format(root))
        file_candidates.update(json_files)

    # Filter specifications
    for file in file_candidates:
        with open(file, encoding="utf8") as fh:
            try:
                content = ujson.loads(fh.read())
            except ValueError:
                raise ValueError("Cannot parse EMG specification file {!r}".format(os.path.abspath(file)))

        if isinstance(content, dict):
            __check_file(logger, file, content, specification_kinds)

    # Merge specifications
    for kind in specification_kinds:
        spec = __merge_spec_versions(specification_kinds[kind]['specification'],
                                     get_necessary_conf_property(conf, 'specifications set'))
        specification_kinds[kind]['specification'] = spec
        __save_collection(logger, spec, '{} spec.json'.format(kind))
    return specification_kinds


def __check_file(logger, file, content, specification_kinds):
    for kind in specification_kinds:
        specification_kinds[kind].setdefault('specification', list())
        for tag in specification_kinds[kind].get('tags', []):
            for att in (t for t in content if isinstance(content[t], dict)):
                if tag in content[att]:
                    logger.debug("Specification file {!r} is treated as {!r} specification".format(file, kind))
                    specification_kinds[kind]['specification'].append(content)
                    return


def __merge_spec_versions(collection, user_tag):
    regex = re.compile('\(base\)')

    # Copy data to a final spec
    def import_specification(spec, final_spec):
        for tag in spec:
            if tag not in final_spec:
                final_spec[tag] = spec[tag]
            elif isinstance(spec[tag], dict):
                final_spec[tag].update(spec[tag])
            elif isinstance(spec[tag], list):
                final_spec[tag].extend(spec[tag])

    def match_default_tag(e):
        for tag in e:
            if regex.search(tag):
                return tag

        return None

    final_specification = dict()

    # Import each entry
    for entry in collection:
        if user_tag in entry:
            # Find provided by a user tag
            import_specification(entry[user_tag], final_specification)
        elif not regex.search(user_tag):
            # Search for a default tag
            dt = match_default_tag(entry)
            if dt:
                import_specification(entry[dt], final_specification)

    # Return final specification
    return final_specification


def __save_collection(logger, collection, file):
    logger.info("Print final merged specification to '{}'".format(file))
    with open(file, "w", encoding="utf8") as fh:
        ujson.dump(collection, fh, ensure_ascii=False, sort_keys=True, indent=4, escape_forward_slashes=False)


def __get_path(logger, conf, prop):
    if prop in conf:
        spec_dir = find_file_or_dir(logger, get_necessary_conf_property(conf, "main working directory"),
                                    get_necessary_conf_property(conf, prop))
        return spec_dir
    else:
        return None


def __get_json_content(logger, conf, prop):
    file = __get_path(logger, conf, prop)
    if file:
        with open(file, encoding="utf8") as fh:
            content = ujson.loads(fh.read())
        return content
    else:
        return None
