#!/usr/bin/python3

from core.components import Component


class Strategy(Component):
    long_name = None

    def execute(self):
        self.logger.error('Function "execute" must be overridden in a strategy')
        exit(1)

    def main(self):
        self.logger.info("Using strategy {0} ({1})".format(self.name, self.long_name))
        self.execute()
        self.logger.info("Strategy has solved verification task")

    def process_single_verdict(self, assertion, verdict):
        # TODO: remove this (for backward compatibility with tests only).
        self.rule_specification = assertion
        self.verification_status = verdict
