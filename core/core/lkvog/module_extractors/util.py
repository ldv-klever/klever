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
from hashlib import md5


def extract_cc(clade):
    cmd_graph = clade.get_command_graph()
    build_graph = cmd_graph.load()

    cc_modules = {}

    for node_id, desc in build_graph.items():
        if desc['type'] == 'CC':
            full_desc = clade.get_cc().load_json_by_id(node_id)
            if full_desc['out'] and not full_desc['out'].endswith('.mod.o'):
                for in_file in full_desc['in']:
                    cc_modules[in_file] = full_desc

    return cc_modules


def build_dependencies(clade):
    not_root_files = set()
    call_graph = clade.get_callgraph()
    call_graph_dict = call_graph.load_callgraph()

    dependencies = {}
    root_files = set()

    for func in sorted(call_graph_dict):
        file = sorted(call_graph_dict[func].keys())[0]
        if file == 'unknown':
            continue
        if not file.endswith('.c'):
            continue
        dependencies.setdefault(file, {})
        for t in ('calls', 'uses'):
            for called_func in sorted(call_graph_dict[func][file].get(t, [])):
                for called_file in sorted(call_graph_dict[func][file][t][called_func].keys()):
                    if called_file == 'unknown':
                        continue
                    if not called_file.endswith('.c'):
                        continue
                    if file != called_file:
                        dependencies.setdefault(file, {})
                        dependencies[file].setdefault(called_file, 0)
                        dependencies[file][called_file] += 1
                        not_root_files.add(called_file)
        root_files.add(file)

    root_files.difference_update(not_root_files)

    # Add circle dependencies files
    root_files.update(set(dependencies.keys()).difference(set(reachable_files(dependencies, root_files))))

    return dependencies, sorted(root_files)


def reachable_files(deps, root_files):
    reachable = set()
    process = list(root_files)
    while process:
        cur = process.pop(0)
        if cur in reachable:
            continue
        reachable.add(cur)
        process.extend(deps.get(cur, []))
    return reachable


def create_module_by_desc(desc_files, in_files):
    module_id = md5("".join([in_file for in_file in sorted(in_files)]).encode('utf-8')).hexdigest()[:12] + ".o"
    ret = {
        module_id: {
            'CCs': [str(desc_file) for desc_file in sorted(desc_files)],
            'in files': sorted(in_files),
            'canon in files': sorted(in_files)
        }
    }
    desc_files.clear()
    in_files.clear()
    return ret


def create_module_by_ld(clade, id, build_graph, module_id=None):
    desc = get_full_desc(clade, id, build_graph[id]['type'])
    if module_id is None:
        if 'relative_out' in desc:
            module_id = desc['relative_out']
        else:
            module_id = desc['out']
    ccs = []
    process = build_graph[id]['using'][:]
    in_files = []
    canon_in_files = []
    while process:
        current = process.pop(0)
        current_type = build_graph[current]['type']

        if current_type == 'CC':
            desc = get_full_desc(clade, current, current_type)
            if not desc['in'][0].endswith('.S'):
                ccs.append(current)
            in_files.extend([os.path.join(desc['cwd'], file) for file in desc['in']])
            canon_in_files.extend(desc['in'])

        process.extend(sorted(build_graph[current]['using']))

    return {
        module_id:  {
            'CCs': ccs,
            'in files': in_files,
            'canon in files': canon_in_files
        }
    }


def create_module_by_cc(clade, id, build_graph, module_id=None):
    desc = get_full_desc(clade, id, build_graph[id]['type'])
    if module_id is None:
        if 'relative_out' in desc:
            module_id = desc['relative_out']
        else:
            module_id = desc['out']
    ccs = []
    process = [id]
    in_files = []
    canon_in_files = []
    while process:
        current = process.pop(0)
        current_type = build_graph[current]['type']

        if current_type == 'CC':
            desc = get_full_desc(clade, current, current_type)
            if not desc['in'][0].endswith('.S'):
                ccs.append(current)
            in_files.extend([os.path.join(desc['cwd'], file) for file in desc['in']])
            canon_in_files.extend(desc['in'])

        process.extend(sorted(build_graph[current]['using']))

    return {
        module_id:  {
            'CCs': ccs,
            'in files': in_files,
            'canon in files': canon_in_files
        }
    }


def create_module(clade, id, build_graph, module_id=None):
    type = build_graph[id]['type']
    if type == 'LD':
        return create_module_by_ld(clade, id, build_graph, module_id)
    else:
        return create_module_by_cc(clade, id, build_graph, module_id)


def get_full_desc(clade, id, type_desc):
    desc = None
    if type_desc == 'CC':
        desc = clade.get_cc()
    elif type_desc == 'LD':
        desc = clade.get_ld()
    elif type_desc == 'MV':
        desc = clade.get_mv()
    else:
        raise Exception("Type {0} is not supported".format(type_desc))
    return desc.load_json_by_id(id)
