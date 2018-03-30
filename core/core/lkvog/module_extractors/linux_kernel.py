import os
import json
import shutil


class LinuxKernel:
    def __init__(self, logger, clade, conf):
        self.logger = logger
        self.clade = clade

    def divide(self):
        modules = {}

        cmd_graph = self.clade.get_command_graph()
        build_graph = cmd_graph.load()

        for id, desc in build_graph.items():
            if desc['type'] == 'LD':
                full_desc = self._get_full_desc(id, desc['type'])
                if full_desc['out'].endswith('.ko'):
                    modules.update(self._create_module(id, build_graph))

        return modules

    def _create_module(self, id, build_graph):
        desc = self._get_full_desc(id, build_graph[id]['type'])
        module_id = desc['relative_out']
        ccs = []
        process = build_graph[id]['using'][:]
        in_files = []
        while process:
            current = process.pop(0)
            current_type = build_graph[current]['type']

            if current_type == 'CC':
                desc = self._get_full_desc(current, current_type)
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

    def _get_full_desc(self, id, type_desc):
        desc = None
        if type_desc == 'CC':
            desc = self.clade.get_cc()
        elif type_desc == 'LD':
            desc = self.clade.get_ld()
        return desc.load_json_by_id(id)

