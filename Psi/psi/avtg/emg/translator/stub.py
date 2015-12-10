from psi.avtg.emg.translator import AbstractTranslator
from psi.avtg.emg.interfaces import Signature


class Translator(AbstractTranslator):

    def _generate_model(self):
        entry_point_signature = "void {}(void)".format(self.entry_point_name)
        entry = Signature(entry_point_signature)
        return

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'