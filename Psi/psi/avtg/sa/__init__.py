import psi.components
import psi.utils


class SA(psi.components.Component):
    def analyze_sources(self):
        self.logger.info("Start source analyzer instance {}".format(self.id))

        self.logger.debug("Receive abstract verification task")
        avt = self.mqs['abstract task description'].get()
        self.logger.info("Analyze source code of an abstract verification task {}".format(avt["id"]))

        # TODO: Put logic here

        self.mqs['abstract task description'].put(avt)

        return

    main = analyze_sources

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
