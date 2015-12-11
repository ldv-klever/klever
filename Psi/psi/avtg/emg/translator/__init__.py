import abc
import os

from psi.avtg.emg.interfaces import Signature


class AbstractTranslator(metaclass=abc.ABCMeta):

    def __init__(self, logger, conf, avt, analysis, model):
        self.logger = logger
        self.conf = conf
        self.task = avt
        self.analysis = analysis
        self.model = model
        self.files = {}
        self.aspects = {}

        if "entry point" in self.conf:
            self.entry_point_name = self.conf["entry point"]
        else:
            self.entry_point_name = "main"
        self.logger.info("Genrate entry point function {}".format(self.entry_point_name))

        self._generate_entry_point()
        self._generate_aspects()
        self._add_aspects()
        self._add_entry_points()
        return

    @abc.abstractmethod
    def _generate_entry_point(self):
        pass

    def _import_mapping(self):
        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                if 'plugin aspects' not in cc_extra_full_desc_file:
                    pass

    def _generate_aspects(self):
        for file in self.files:
            aspect_file = []
            aspect_file.append('after: file ("$this")\n')
            aspect_file.append('{\n')
            if "functions" in self.files[file]:
                for function in self.files[file]["functions"]:
                    lines = self.files[file]["functions"][function].get_definition()
                    aspect_file.append("\n")
                    aspect_file.extend(lines)
            aspect_file.append('}\n')

            # TODO: rewrite code below
            name = "single_hardcoded_aspect_file.aspect"
            with open("single_hardcoded_aspect_file.aspect", "w") as fh:
                fh.writelines(aspect_file)

            path = os.path.relpath(os.path.abspath(name), os.path.realpath(self.conf['source tree root']))
            self.logger.info("Add aspect file {}".format(path))
            self.aspects[file] = path

    def _add_aspects(self):
        for grp in self.task['grps']:
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                if cc_extra_full_desc_file["in file"] in self.aspects:
                    if 'plugin aspects' not in cc_extra_full_desc_file:
                        cc_extra_full_desc_file['plugin aspects'] = []
                    cc_extra_full_desc_file['plugin aspects'].append(
                        {
                            "plugin": "EMG",
                            "aspects": [self.aspects[cc_extra_full_desc_file["in file"]]]
                        }
                    )

    def _add_entry_points(self):
        self.task["entry points"] = [self.entry_point_name]

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'


