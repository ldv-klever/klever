class ComponentBase:
    def __init__(self, conf, logger):
        self.conf = conf
        self.logger = logger

    def get_callbacks(self):
        self.logger.debug('Have not any callbacks yet')

    def launch(self):
        pass
