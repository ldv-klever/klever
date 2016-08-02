from core.avtg.emg.translator import AbstractTranslator


class Translator(AbstractTranslator):

    def translate(self, analysis, model):
        self.logger.info("Activate default translator")
        return super(Translator, self).translate(analysis, model)


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
