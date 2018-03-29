import os
from core.lkvog.module_extractors import util


class Breadth():
    def __init__(self, logger, clade, conf):
        self.logger = logger
        self.clade = clade
        self._cluster_size = conf.get('module size', 3)
        self._cc_modules = {}
        self._dependencies = {}
        self._cc_modules = util.extract_cc(self.clade)
        self._dependencies, self._root_files = util.build_dependencies(self.clade)

    def divide(self):
        process = list(sorted(self._root_files))
        processed = set()
        new_process = []
        modules = {}
        current_module_desc_files = set()
        current_module_in_files = set()

        while process:
            cur = process.pop(0)
            if cur in processed:
                continue

            processed.add(cur)

            if cur in self._cc_modules:
                current_module_desc_files.add(self._cc_modules[cur]['id'])
                current_module_in_files.update(self._cc_modules[cur]['in'])
                if len(current_module_in_files) == self._cluster_size:
                    modules.update(util.create_module(current_module_desc_files, current_module_in_files))
                    self.logger.debug('Create module with {0} in files'.format(list(current_module_in_files)))

            new_process.extend(self._dependencies[cur])

        if current_module_in_files:
                modules.update(util.create_module(current_module_desc_files, current_module_in_files))
                self.logger.debug('Create module with {0} in files'.format(list(current_module_in_files)))

        return modules

