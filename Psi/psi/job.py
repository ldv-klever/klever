import os
import tarfile

import psi.components


class Job:
    format = 1
    archive = 'job.tar.gz'
    dir = 'job'
    type = os.path.join(dir, 'class')

    def __init__(self, logger, id):
        self.logger = logger
        self.logger.debug('Support jobs of format "{0}"'.format(self.format))
        self.id = id
        self.logger.debug('Job identifier is "{0}"'.format(id))

    def get_class(self):
        self.logger.info('Get job class')
        with open(self.type) as fp:
            self.type = fp.read()
        self.logger.debug('Job class is "{0}"'.format(self.type))

    def get_components(self):
        self.logger.info('Get components necessary to solve job')

        if self.type not in psi.components.job_class_component_modules:
            raise KeyError('Job class "{0}" is not supported'.format(self.type))

        # Get modules of components specific for job class.
        component_modules = psi.components.job_class_component_modules[self.type]

        # Get modules of common components.
        component_modules.extend(psi.components.job_class_component_modules['Common'])

        # Get components.
        components = [psi.components.Component(component_module) for component_module in component_modules]

        self.logger.debug(
            'Components to be launched: "{0}"'.format(
                ', '.join([component.name for component in components])))

        return components

    def extract_archive(self):
        self.logger.info('Extract job archive "{0}" to directory "{1}"'.format(self.archive, self.dir))
        with tarfile.open(self.archive) as TarFile:
            TarFile.extractall(self.dir)
