from core.lkvog.module_extractors import util


class Simple:
    def __init__(self, logger, clade, conf):
        self._logger = logger
        self._clade = clade
        self._conf = conf

    def divide(self):
        dependencies = util.build_dependencies(self._clade)[0]
        modules = {}
        for file in dependencies.keys():
            try:
                desc = self._clade.get_cc().load_json_by_in(file)
            except FileNotFoundError:
                continue
            modules.update(util.create_module([desc['id']], [file]))

        return modules
