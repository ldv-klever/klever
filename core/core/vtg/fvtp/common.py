#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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
import core.utils


def trimmed_files(logger, conf, abstract_task_desc):
    regex = re.compile('# 40 ".*/arm-unknown-linux-gnueabi/4.6.0/include/stdarg.h"')
    c_files = []

    # CIL doesn't support asm goto (https://forge.ispras.ru/issues/1323).
    logger.debug('Ignore asm goto expressions')
    for extra_c_file in abstract_task_desc['extra C files']:
        if 'C file' not in extra_c_file:
            continue

        trimmed_c_file = '{0}.trimmed.i'.format(os.path.splitext(os.path.basename(extra_c_file['C file']))[0])

        with open(os.path.join(conf['main working directory'], extra_c_file['C file']),
                  encoding='utf8') as fp_in, open(trimmed_c_file, 'w', encoding='utf8') as fp_out:
            trigger = False

            # Specify original location to avoid references to *.trimmed.i files in error traces.
            fp_out.write('# 1 "{0}"\n'.format(extra_c_file['C file']))
            # Each such expression occupies individual line, so just get rid of them.
            for line in fp_in:

                # Asm volatile goto
                l = re.sub(r'asm volatile goto.*;', '', line)

                if not trigger and regex.match(line):
                    trigger = True
                elif trigger:
                    l = line.replace('typedef __va_list __gnuc_va_list;',
                                     'typedef __builtin_va_list __gnuc_va_list;')
                    trigger = False

                fp_out.write(l)

        extra_c_file['new C file'] = trimmed_c_file
        c_files.append(trimmed_c_file)

    return c_files


def merge_files(logger, conf, abstract_task_desc):
    """
    Merge several given C files into single one using CIL.

    :param logger: Logger object.
    :param conf: Configration dictionary.
    :param abstract_task_desc: Abstract verification task description dictionary.
    :return: A file name of the newly created file.
    """
    logger.info('Merge source files by means of CIL')
    c_files = trimmed_files(logger, conf, abstract_task_desc)

    args = [
               'cilly.asm.exe',
               '--printCilAsIs',
               '--domakeCFG',
               '--decil',
               '--noInsertImplicitCasts',
               # Now supported by CPAchecker frontend.
               '--useLogicalOperators',
               '--ignore-merge-conflicts',
               # Don't transform simple function calls to calls-by-pointers.
               '--no-convert-direct-calls',
               # Don't transform s->f to pointer arithmetic.
               '--no-convert-field-offsets',
               # Don't transform structure fields into variables or arrays.
               '--no-split-structs',
               '--rmUnusedInlines',
               '--out', 'cil.i',
           ] + c_files
    core.utils.execute_external_tool(logger, args=args)
    logger.debug('Merged source files was outputted to "cil.i"')

    return 'cil.i'


def get_verifier_opts_and_safe_prps(logger, resource_limits, conf):
    """
    Collect verifier oiptions from a user provided description, template and profile and prepare a final list of
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
            remove = list()
            # For each excuded option
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

        return desc1

    logger.debug("Import verifier profiles DB")
    try:
        verifier_profile_db = conf["verifier profiles DB"]
    except KeyError:
        raise KeyError('Set "verifier profiles DB" configuration option and provide corresponding file with '
                       'verifiers profiles containing options')
    try:
        verifier_profile_db = core.utils.find_file_or_dir(logger, conf["main working directory"], verifier_profile_db)
        with open(verifier_profile_db, 'r', encoding='utf8') as fp:
            profiles = json.loads(fp.read())
    except FileNotFoundError:
        raise FileNotFoundError("There is no verifier profiles DB file: {!r}".format(verifier_profile_db))

    logger.debug("Determine profile for the given verifier and its version")
    try:
        verifier_name = conf['verifier']['name']
        verifier_version = conf['verifier']['version']
        user_opts = conf['verifier']
        profile = conf['verifier profile']
        profile_opts = profiles['profiles'][profile][verifier_name][verifier_version]
    except KeyError as err:
        raise KeyError("To run verification you need to: 1) Provide name, version and profile name of verifer at FVTP"
                       " plugin configuration. 2) Create such verifier profile at verifier profiles base file. The"
                       " following key is actually not found: {!r}".format(err))

    logger.debug("Determine inheritance of profiles and templates")
    sets = [user_opts, profile_opts]
    while 'inherit' in sets[-1]:
        if sets[-1]['inherit'] not in profiles['templates']:
            raise KeyError("Verifier profile template does not exist: {}".format(sets[-1]['inherit']))
        sets.append(profiles['templates'][sets[-1]['inherit']])

    logger.debug("Prepare final opts description")
    last = None
    while len(sets):
        if not last:
            # We know that there are at least two elements in the list
            last = sets.pop()
        new = sets.pop()
        last = merge(last, new)

    # Process given options according to ldv patterns
    matcher = re.compile("\%ldv\:([\w|\s]+)\:(\d+\.\d+)\:(\w+)\%")

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
                i = core.utils.memory_units_converter(resource_limits[name], units)[0]
            elif name in ("wall time", "CPU time"):
                i = core.utils.time_units_converter(resource_limits[name], units)[0]
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


def read_max_resource_limitations(logger, conf):
    """
    Get maximum resource limitations that can be set for a verification task.

    :param logger: Logger.
    :param conf: Configuration dictionary.
    :return: Dictionary.
    """
    # Read max restrictions for tasks
    restrictions_file = core.utils.find_file_or_dir(logger, conf["main working directory"], "tasks.json")
    with open(restrictions_file, 'r', encoding='utf8') as fp:
        restrictions = json.loads(fp.read())

    # Make unit translation
    for mem in (m for m in ("memory size", "disk memory size") if m in restrictions and restrictions[m] is not None):
        restrictions[mem] = core.utils.memory_units_converter(restrictions[mem])[0]
    for t in (t for t in ("wall time", "CPU time") if t in restrictions and restrictions[t] is not None):
        restrictions[t] = core.utils.time_units_converter(restrictions[t])[0]
    return restrictions


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