#!/usr/bin/python3

from core.vtg.sbt import SBT


# This strategy is aimed at creating 1 verification tasks for all
# specified bug types.
class Batch(SBT):

    def perform_sanity_checks(self):
        if 'unite rule specifications' not in self.conf['abstract task desc']['AVTG'] \
                or not self.conf['abstract task desc']['AVTG']['unite rule specifications']:
            raise AttributeError("Current VTG strategy supports only united bug types")

    def print_strategy_information(self):
        self.logger.info('Launch strategy "Batch"')
        self.logger.info('Generate one verification task for all bug types')
