import core.components


class Plugin(core.components.Component):
    def run(self):
        self.logger.info('Get abstract verification task description')
        self.abstract_task_desc = self.mqs['abstract task description'].get()
        self.logger.info('Process abstract verification task "{0}"'.format(self.abstract_task_desc['id']))
        core.components.Component.run(self)
        self.logger.info('Put abstract verification task description')
        self.mqs['abstract task description'].put(self.abstract_task_desc)
