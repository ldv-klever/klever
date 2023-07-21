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

from klever.core.vtg.emg.common.c import Variable


class Automaton:
    """
    This is a more abstract representation of FSA. It contains both FSA object generated for the process object and
    process object itself. It also contains variables generated for labels of the process and simplifies work with
    them.
    """

    def __init__(self, process, identifier):
        # Set default values
        self.__label_variables = {}

        # Set given values
        self.process = process
        self.self_parallelism = True

        assert isinstance(identifier, int)
        self._identifier = identifier

        # Generate FSA itself
        self.variables()
        self.code = {}

    def __str__(self):
        return str(self._identifier)

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return type(self) is type(other) and str(self) == str(other)

    def __lt__(self, other):
        return str(self) < str(other)

    @property
    def identifier(self):
        return self._identifier

    def variables(self, only_used=False):
        """
        Generate a variable for each process label or just return an already generated list of variables.

        :return: List with Variable objects.
        """
        variables = []

        # Generate variable for each label
        for label in self.process.labels.values():
            var = self.determine_variable(label, shadow_use=True)
            if var:
                variables.append(self.determine_variable(label, shadow_use=True))

        if only_used:
            variables = [v for v in variables if v.use > 0]
        return variables

    def determine_variable(self, label, shadow_use=False):
        """
        Get Label object and generate a variable for it or just return an existing Variable object. Also increase a
        counter of the variable usages.

        :param label: Label object.
        :param shadow_use: Do not increase the counter of usages of the variable if True.
        :return: Variable object which corresponds to the label.
        """
        if label.name in self.__label_variables and "default" in self.__label_variables[label.name]:
            if not shadow_use:
                self.__label_variables[label.name]["default"].use += 1
            return self.__label_variables[label.name]["default"]

        if label.declaration:
            var = Variable("emg_{}_{}".format(self._identifier, label.name), label.declaration)
            var.value = label.value

            self.__label_variables.setdefault(label.name, {})
            self.__label_variables[label.name]["default"] = var
            if not shadow_use:
                self.__label_variables[label.name]["default"].use += 1
            return self.__label_variables[label.name]["default"]

        return None
