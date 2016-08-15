import json
import os

import core.components


class Plugin(core.components.Component):
    def run(self):
        in_abstract_task_desc_file = os.path.relpath(
            os.path.join(self.conf['main working directory'], self.conf['in abstract task desc file']))
        self.logger.info(
            'Get abstract verification task description from file "{0}"'.format(in_abstract_task_desc_file))
        with open(in_abstract_task_desc_file, encoding='utf8') as fp:
            self.abstract_task_desc = json.load(fp)

        self.logger.info('Start processing of abstract verification task "{0}"'.format(self.abstract_task_desc['id']))
        core.components.Component.run(self)

        out_abstract_task_desc_file = os.path.relpath(
            os.path.join(self.conf['main working directory'], self.conf['out abstract task desc file']))
        self.logger.info(
            'Put modified abstract verification task description to file "{0}"'.format(out_abstract_task_desc_file))
        with open(out_abstract_task_desc_file, 'w', encoding='utf8') as fp:
            json.dump(self.abstract_task_desc, fp, ensure_ascii=False, sort_keys=True, indent=4)

        self.logger.info('Finish processing of abstract verification task "{0}"'.format(self.abstract_task_desc['id']))
