from psi.avtg.emg.translator import AbstractTranslator
from psi.avtg.emg.interfaces import Signature


class Translator(AbstractTranslator):

    def _generate_entry_point(self):
        entry_point_signature = "void {}(void)".format(self.entry_point_name)
        entry = Signature(entry_point_signature)
        self.entry = entry

        if len(self.analysis.inits) == 1:
            label = "init_error"
            file = list(self.analysis.inits.keys())[0]
            module_init = self.analysis.inits[file]
            if file not in self.analysis.exits and len(self.analysis.exits) > 0:
                raise NotImplementedError("Cannot generate environment model if module initialization and exit "
                                          "functions are in different files")
            elif len(self.analysis.exits) == 0:
                raise NotImplementedError("Cannot generate environment model if no exit function in module")
            else:
                module_exit = self.analysis.exits[file]

            ep = self.entry
            body = [
                "int ret;",
                "ret = {}();".format(module_init),
                "if (!ret) {",
                "   goto {};".format(label),
                "}",
                "{}();".format(module_exit),
                "{}:".format(label),
                "return;",
            ]
            ep.body.concatenate(body)

            if file not in self.files:
                self.files[file] = {
                    "functions": {},
                    "variables": {}
                }
            self.files[file]["functions"][ep.function_name] = ep
        elif len(self.analysis.inits) < 1:
            raise RuntimeError("Cannot generate entry point without module initialization function")
        elif len(self.analysis.inits) > 1:
            raise NotImplementedError("Cannot generate entry point more than one module initialization function")

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'