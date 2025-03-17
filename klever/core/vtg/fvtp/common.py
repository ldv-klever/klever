#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

import os
import re
import zipfile
import json
import sortedcontainers
import klever.core.utils


def merge_files(logger, conf, abstract_task_desc):
    """
    Merge several given C files into single one using CIL.

    :param logger: Logger object.
    :param conf: Configuration dictionary.
    :param abstract_task_desc: Abstract verification task description dictionary.
    :return: A file name of the newly created file.
    """
    if os.path.isfile('cil.i'):
        logger.info('CIL file exists, we do not need to run CIL again')
    else:
        logger.info('Merge source files by means of CIL')

        ordered_c_files = sortedcontainers.SortedSet()
        for extra_c_file in abstract_task_desc['extra C files']:
            if 'C file' in extra_c_file:
                ordered_c_files.add(os.path.join(conf['main working directory'], extra_c_file['C file']))

        with open('input files', 'w', encoding='utf-8') as fp:
            for c_file in ordered_c_files:
                fp.write(c_file + '\n')

        args = ['toplevel.opt'] + \
            conf.get('CIL additional opts', []) + \
            [
                # This disables searching for add-ons enabled by default. One still is able to load plugins manually.
                '-no-autoload-plugins', '-no-findlib',
                # Copy user or internal errors to "problem desc.txt" explicitly since CIL does not output them to STDERR.
                '-kernel-log', 'e:problem desc.txt',
                '-machdep', conf['CIL']['machine'],
                # Compatibility with C11 (ISO/IEC 9899:2011).
                '-c11',
                # In our mode this is the only warning resulting to errors by default.
                '-kernel-warn-key', 'CERT:MSC:38=active',
                # Removing unused functions helps to reduce CPAchecker computational resources consumption very-very
                # considerably.
                '-remove-unused-inline-functions', '-remove-unused-static-functions',
                # This helps to reduce considerable memory consumption by CIL itself since input files are processed more
                # sequentially.
                '-no-annot',
                # This allows to avoid temporary variables to hold return values for all functions and returns at the end of
                # functions even when returning in the middle.
                '-no-single-return',
                # Avoid temporary variables as much as possible since witnesses will refer them otherwise.
                '-fold-temp-vars',
                # Remove redundant zero initializers of global variables that are specified in original sources (rarely) or
                # added by CIL itself.
                '-shrink-initializers',
                # Rest options.
                '-keep-logical-operators',
                '-aggressive-merging',
                '-print', '-print-lines', '-no-print-annot',
                '-ocode', 'cil.i',
                '-more-files', 'input files'
            ]

        klever.core.utils.execute(logger, args=args, enforce_limitations=True,
                                  cpu_time_limit=conf["resource limits"]["CPU time for executed commands"],
                                  memory_limit=conf["resource limits"]["memory size for executed commands"])
        # There will be empty file if CIL succeeded. Remove it to avoid unknown reports of whole FVTP later.
        if os.path.isfile('problem desc.txt'):
            os.unlink('problem desc.txt')

        logger.debug('Merged source files was outputted to "cil.i"')

    return 'cil.i'


def get_verifier_opts_and_safe_prps(logger, resource_limits, conf):
    """
    Collect verifier options from a user provided description, template and profile and prepare a final list of
    options. Each option is represented as a small dictionary with an option name given as a key and value provided
    as a value. The value can be None. Priority of options is the following: options given by a user
    (the most important), options provided by a profile and options from the template.

    :param logger: Logger.
    :param resource_limits: Dictionary with resource limitations of the task.
    :param conf: Configuration dictionary.
    :return: List with options.
    """
    def merge(desc1, desc2):
        if "add options" not in desc1:
            desc1["add options"] = []

        if "safety properties" not in desc1:
            desc1["safety properties"] = []

        if "exclude options" in desc2:
            remove = []
            # For each excluded option
            for e in desc2["exclude options"]:
                name = list(e.keys())[0]
                value = e[name]

                # Match corresponding
                for c in desc1["add options"]:
                    if name in c and (not value or c[name] == value):
                        remove.append(c)
                        break

            # Remove objects finally
            for e in remove:
                desc1["add options"].remove(e)

        if "add options" in desc2:
            append = []
            # Match already existing options
            for e in desc2["add options"]:
                name = list(e.keys())[0]
                value = e[name]

                # Check that there is no such option
                found = False
                for c in desc1["add options"]:
                    if name in c and (not value or c[name] == value):
                        found = True

                if not found:
                    append.append(e)

            # Add new
            desc1["add options"].extend(append)

        if "safety properties" in desc2:
            desc1["safety properties"].extend(desc2["safety properties"])

        if "version" in desc2:
            # rewrite in any case
            desc1["version"] = desc2["version"]

        if "name" in desc2:
            desc1["name"] = desc2["name"]

        return desc1

    logger.debug("Import verifier profiles base")
    try:
        verifier_profile_db = conf["verifier profiles base"]
    except KeyError as e:
        raise KeyError('Set "verifier profiles base" configuration option and provide corresponding file with '
                       'verifiers profiles containing options') from e
    try:
        verifier_profile_db = klever.core.utils.find_file_or_dir(logger, conf["main working directory"], verifier_profile_db)
        with open(verifier_profile_db, 'r', encoding='utf-8') as fp:
            profiles = json.loads(fp.read())
    except FileNotFoundError as e:
        raise FileNotFoundError("There is no verifier profiles base file: {!r}".format(verifier_profile_db)) from e

    logger.debug("Determine profile for the given verifier and its version")
    profile = conf['verifier profile']
    if profile not in profiles:
        raise KeyError("Verifier profile {} is not found".format(profile))
    profile_opts = profiles[profile]

    logger.debug("Determine inheritance of profiles and templates")
    sets = [profile_opts]
    while 'inherit' in sets[-1]:
        if sets[-1]['inherit'] not in profiles:
            raise KeyError("Verifier profile template does not exist: {}".format(sets[-1]['inherit']))
        sets.append(profiles[sets[-1]['inherit']])

    logger.debug("Prepare final opts description")
    last = None
    while sets:
        if not last:
            # We know that there are at least two elements in the list
            last = sets.pop()
        new = sets.pop()
        if last.get('architecture dependant options'):
            arch_options = last['architecture dependant options'].get(conf['architecture'], {})
            last = merge(last, arch_options)
        if new.get('architecture dependant options'):
            arch_options = new['architecture dependant options'].get(conf['architecture'], {})
            new = merge(new, arch_options)
        last = merge(last, new)

    # Then get verification profile directly from user if it is set
    if conf.get('verifier profile description'):
        last = merge(last, conf['verifier profile description'])

    # Update configuration
    conf['verifier'] = {}
    conf['verifier']['name'] = last['name']
    conf['verifier']['version'] = last['version']

    # Process given options according to ldv patterns
    matcher = re.compile(r"\%ldv\:([\w|\s]+)\:(\d+\.\d+)\:(\w+)\%")

    def processor(v):
        """Replace patterns in options by values"""
        if matcher.search(v):
            name, modifier, units = matcher.search(v).groups()
            if '' in (name, modifier, value):
                raise ValueError("Expect an option pattern in the form %ldv:Name in tasks.json:float modifier:units% "
                                 "but got: {!r}".format(matcher.search(v).group(0)))
            if name not in resource_limits:
                raise KeyError("There is no limitation {!r} set but it is required for configuration option "
                               "pattern {!r}".format(name, matcher.search(v).group(0)))
            modifier = float(modifier)
            if name in ("memory size", "disk memory size"):
                i = klever.core.utils.memory_units_converter(resource_limits[name], units)[0]
            elif name in ("wall time", "CPU time"):
                i = klever.core.utils.time_units_converter(resource_limits[name], units)[0]
            else:
                i = resource_limits[name]
            i = i * modifier
            if isinstance(resource_limits[name], int):
                i = int(round(i, 0))
            elif isinstance(resource_limits[name], float):
                i = float(round(i, 2))
            i = str(i)
            v = v.replace(matcher.search(v).group(0), i)

        return v

    for index in range(len(last['add options'])):
        option = list(last['add options'][index].keys())[0]
        value = list(last['add options'][index].values())[0]
        last['add options'][index] = {processor(option): processor(value)}

    return last['add options'], last['safety properties']


def prepare_verification_task_files_archive(files):
    """
    Generate archive for verification task files in the current directory. The archive name should be 'task files.zip'.

    :param files: A list of files.
    :return: None
    """
    with open('task files.zip', mode='w+b', buffering=0) as fp:
        with zipfile.ZipFile(fp, mode='w', compression=zipfile.ZIP_DEFLATED) as zfp:
            for file in files:
                zfp.write(file)
            os.fsync(zfp.fp)
