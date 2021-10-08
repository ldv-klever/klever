#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


class Abstract:

    DESC_FILE = 'aggregations description.json'

    def __init__(self, logger, conf, tactic, program):
        """
        Simple strategy to add dependencies to each target fragment.

        :param logger: Logger object.
        :param conf: Configuration dictionary.
        :param tactic: Fragmentation set options dictionary.
        :param program: Program object.
        """
        self.logger = logger
        self.conf = conf
        self.tactic = tactic
        self.program = program
        self.__groups = dict()

    def get_groups(self):
        """
        Get final fragments (that contain each several Fragment objects).

        :return: Dict {Fragment name -> set of Fragment objects.}
        """
        if not self.__groups:
            for frag in self.program.target_fragments:
                for name, fragment, fragments in self._generate_groups_for_target(frag):
                    if name in self.__groups:
                        raise ValueError('Cannot add a group with the same name {!r}'.format(name))
                    self.__groups[name] = (fragment, fragments)
        return self.__groups

    def _generate_groups_for_target(self, fragment):
        """
        Simple stub to return the only fragment.

        :param fragment: Fragment object.
        """
        return [(fragment.name, fragment, {fragment})]
