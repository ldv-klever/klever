import os
from hashlib import md5

def extract_cc(clade):
    cmd_graph = clade.get_command_graph()
    build_graph = cmd_graph.load()

    cc_modules = {}

    for node_id, desc in build_graph.items():
        if desc['type'] == 'CC':
            full_desc = clade.get_cc().load_json_by_id(node_id)
            for in_file in full_desc['in']:
                if not in_file.startswith(full_desc['cwd']):
                    in_file = os.path.join(full_desc['cwd'], in_file)
                cc_modules[in_file] = full_desc

    return cc_modules


def build_dependencies(clade):
    not_root_files = set()
    call_graph = clade.get_callgraph()
    call_graph_dict = call_graph.load_callgraph()

    dependencies = {}
    root_files = set()

    for func in call_graph_dict:
        file = list(call_graph_dict[func].keys())[0]
        if file == 'unknown':
            continue
        for called_func in call_graph_dict[func][file].get('calls', []):
            called_file = list(call_graph_dict[func][file]['calls'][called_func].keys())[0]
            if called_file == 'unknown':
                continue
            if file != called_file:
                dependencies.setdefault(file, {})
                dependencies[file].setdefault(called_file, 0)
                dependencies[file][called_file] += 1
                #dependencies[file].append(called_file)
                not_root_files.add(called_file)
                root_files.add(file)

    root_files.difference_update(not_root_files)

    return dependencies, root_files


def create_module(desc_files, in_files):
    module_id = md5("".join([in_file for in_file in sorted(in_files)]).encode('utf-8')).hexdigest()[:12]
    ret = {
        module_id: {
            'desc files': list(desc_files),
            'in files': list(in_files)
        }
    }
    desc_files.clear()
    in_files.clear()
    return ret


def create_module_by_ld(clade, id, build_graph):
    desc = get_full_desc(clade, id, build_graph[id]['type'])
    module_id = desc['relative_out']
    ccs = []
    process = build_graph[id]['using'][:]
    in_files = []
    while process:
        current = process.pop(0)
        current_type = build_graph[current]['type']

        if current_type == 'CC':
            desc = get_full_desc(clade, current, current_type)
            if not desc['in'][0].endswith('.S'):
                ccs.append(current)
            in_files.extend([os.path.join(desc['cwd'], file) for file in desc['in']])

        process.extend(build_graph[current]['using'])

    return {
        module_id:  {
            'CCs': ccs,
            'in files': in_files
        }
    }


def get_full_desc(clade, id, type_desc):
    desc = None
    if type_desc == 'CC':
        desc = clade.get_cc()
    elif type_desc == 'LD':
        desc = clade.get_ld()
    return desc.load_json_by_id(id)
