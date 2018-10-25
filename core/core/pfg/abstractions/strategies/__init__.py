#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

    DESC_FILE = 'agregations description.json'

    def __init__(self, logger, conf, fragmentation_set_conf, program):
        """
        Simple strategy to add dependencies to each target fragment.

        :param logger: Logger object.
        :param conf: Configuration dictionary.
        :param fragmentation_set_conf: Fragmentation set dictionary.
        :param program: Program object.
        """
        self.logger = logger
        self.conf = conf
        self.fragmentation_set_conf = fragmentation_set_conf
        self.program = program
        self._groups = dict()

    def add_group(self, name, fragments):
        """
        Add a group of fragments to the collection of final fragments intended for verification. This group is
        considered everywhere as a single monolithic fragment that consists of several groups of files. But at this
        point, the fragment is composed of several smaller Fragment object. This is done to keep dependencies between
        files in terms of such final fragment. For instance at environment model generation this can be required.

        :param name: A new name of the fragment to be created from given Fragment objects.
        :param fragments: Fragment objects.
        """
        if name in self._groups:
            raise ValueError('Cannot add a group with the same name {!r}'.format(name))
        self._groups[name] = fragments

    def get_groups(self):
        """
        Get final fragments (that contain each several Fragment objects).

        :return: Dict {Fragment name -> set of Fragment objects.}
        """
        self._make_groups()
        return self._groups

    def _make_groups(self):
        """Collect dependencies and create final fragments for each target Fragment object."""
        for frag in self.program.target_fragments:
            self.add_group(frag.name, {frag})
