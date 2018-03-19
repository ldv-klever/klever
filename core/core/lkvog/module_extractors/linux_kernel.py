import os
import json
import shutil


class LinuxKernel:
    def __init__(self, logger, conf):
        self.logger = logger
        self.clade_dir = conf #conf['clade']
        self.model_cc_opts = None

    def divide(self, build_graph):
        modules = {}

        for id, desc in build_graph.items():
            if desc['type'] == 'LD':
                full_desc = self._get_full_desc(id, desc['type'])
                if full_desc['out'].endswith('.ko'):
                    modules.update(self._create_module(id, build_graph))
            elif desc['type'] == 'CC':
                full_desc = self._get_full_desc(id, desc['type'])
                if full_desc['in'] and full_desc['in'][0] == 'scripts/mod/empty.c':
                    self.model_cc_opts = full_desc['opts']
                    self.model_cc_opts = [cc_opt for cc_opt in self.model_cc_opts if cc_opt != '-mpreferred-stack-boundary=3']
                    self._copy_deps(full_desc)

        return modules

    def get_cc_opts(self):
        return self.model_cc_opts

    def _copy_deps(self, full_desc):
        cwd = full_desc['cwd']
        for dep in full_desc['deps']:
            if os.path.isabs(dep) and not dep.startswith(cwd):
                continue
            if os.path.isabs(dep):
                dep = os.path.relpath(dep, cwd)
            os.makedirs(os.path.dirname(dep).encode('utf8'), exist_ok=True)

            #TODO: Get src file from clade interface
            shutil.copy2(os.path.join(cwd, dep), dep)

    def _create_module(self, id, build_graph):
        desc = self._get_full_desc(id, build_graph[id]['type'])
        module_id = desc['out']
        desc_files = []
        process = build_graph[id]['using'][:]
        while process:
            current = process.pop(0)
            current_type = build_graph[current]['type']

            if current_type == 'CC':
                desc = self._get_full_desc(current, current_type)
                if not desc['in'][0].endswith('.S'):
                    desc_files.append(self._get_desc_path(current, current_type))
            process.extend(build_graph[current]['using'])

        return {module_id: desc_files}

    def _get_desc_path(self, id, type_desc):
        return os.path.join(self.clade_dir, type_desc, '{0}.json'.format(id))

    def _get_full_desc(self, id, type_desc):
        with open(self._get_desc_path(id, type_desc)) as fp:
            return json.load(fp)

