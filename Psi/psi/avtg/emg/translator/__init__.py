import abc

from psi.avtg.emg.interfaces import Signature


class AbstractTranslator(metaclass=abc.ABCMeta):

    def __init__(self, logger, conf, avt, analysis, model):
        self.logger = logger
        self.conf = conf
        self.task = avt
        self.analysis = analysis
        self.model = model

        if "entry point" in self.conf:
            self.entry_point_name = self.conf["entry point"]
        else:
            self.entry_point_name = "main"
        self.logger("Genrate entry point function {}".format(self.entry_point_name))
        self._generate_model()

    @abc.abstractmethod
    def _generate_model(self):
        pass


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
