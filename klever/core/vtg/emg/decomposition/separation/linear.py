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

import copy
import logging
import collections

from klever.core.vtg.emg.decomposition.scenario import Scenario
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy, ScenarioExtractor
from klever.core.vtg.emg.common.process.actions import Choice, Actions, Operator, Concatenation, BaseAction, Action, \
    Savepoint, Behaviour, Subprocess, Parentheses


class LinearExtractor(ScenarioExtractor):
    """
    This class implements a factory that generates Scenario instances that do not have choices. Instead the factory
    provides more scenarios that should cover all alternatives from the provided process.
    """

    def _new_scenarios(self, paths, action=None):
        if not action:
            for path in paths:
                nsc = Scenario(None)
                nsc.initial_action = Concatenation()
                for step in path:
                    nsc.add_action_copy(step, nsc.initial_action)
                yield nsc
        else:
            suffixes = []
            check = set()
            for path in [p for p in paths if str(action) in {str(a) for a in p}]:
                index = [str(a) for a in p].index(str(action))
                new_path = [index:]
                str_path = '++'.join([str(a) for a in new_path])
                if str_path not in check:
                    check.add(str_path)
                    suffixes.append(new_path)

            for sp in action.description.savepoints:
                for path in suffixes:
                    nsc = Scenario(sp)
                    nsc.initial_action = Concatenation()
                    for step in path:
                        nsc.add_action_copy(step, nsc.initial_action)
                    yield nsc

    def _get_scenarios_for_root_savepoints(self, root: Action):
        paths = self.__determine_paths()

        self.logger.debug('Generate main scenarios')
        yield from self._new_scenarios(paths)
        for action in (a for a in self._actions.values() if a.savepoints):
            self.logger.debug(f'Generate scenarios with savepoints for action {str(action)}')
            yield from _new_scenarios(paths, action)

    def __determine_paths(self):
        subp_to_paths = dict()
        # Collect subprocesses and possible different paths
        for subprocess_desc in self._actions.filter(include=Subprocess):
            subp_to_paths[str(subprocess_desc)] = self.__choose_subprocess_paths(subprocess_desc.action, [])
        # Add the main path
        initial_paths = self.__choose_subprocess_paths(self._actions.initial_action, [])

        while self.__path_dependencies(initial_paths):
            for dependency in self.__path_dependencies(initial_paths):
                # First, do substitutions
                for subprocess, paths in list(subp_to_paths.items()):
                    new_paths = []
                    for path in paths:
                        if str(p[-1]) == dependency:
                            suffixes = [p for p in subp_to_paths[dependency] if str(p[-1]) != dependency and \
                                        str(p[-1]) != subprocess)]
                            if suffixes:
                                newly_created = __do_substitution(path, suffixes)
                                new_paths.extend(newly_created)
                            else:
                                new_paths.append(path)
                        else:
                            new_paths.append(path)
                    
                    # Now save new paths
                    subp_to_paths[subprocess] = new_paths
                
                    # Check that the dependecy is not terminated and self-dependent only
                    new_deps = self.__path_dependencies(subp_to_paths[subprocess])
                    if len(new_deps) == 0 or (len(new_deps) == 1 and subprocess in new_deps):
                        # Determine terminal paths and do substitution removing the recursion
                        recursion_paths = []
                        terminal_paths = []
                        
                        for path in subp_to_paths[subprocess]:
                            if str(path[-1]) == subprocess:
                                recursion_paths.append(path)
                            else:
                                assert not path[-1].kind is Subprocess:
                                terminal_paths.append(path)
                        
                        new_paths = []
                        for recursive_path in recursion_paths:
                            new_paths.extend(self.__do_substitution(recursive_path, terminal_paths))

                        subp_to_paths[subprocess] = new_paths + terminal_paths

            new_initial_paths = []
            for path in initial_paths:
                if path[-1].kind is Subprocess and not self.__path_dependencies(subp_to_paths[str(path[-1])]):
                    new_initial_paths.extend(self.__do_substitution(path, subp_to_paths[str(path[-1])]))
                else:
                    new_initial_paths.append(path)

            initial_paths = new_initial_paths

        return initial_paths
            

    @staticmethod
    def __do_substitution(self, origin, suffixes):
        assert suffixes
        return [origin[:-1] + suffix for suffix in suffixes]

    @staticmethod
    def __path_dependencies(self, paths):
        return {str(path[-1]) for path in paths if path[-1].kind is Subprocess}

    def __choose_subprocess_paths(self, action: Behaviour, paths: list):
        """
        Collect unique paths till to jumps to subprocesses. Example:
        p := <a>.(<b>.{c} | {d}) | <f> 
        The function should return the following paths:
        [a, b, c], [a, d], [f]
        """
        paths = list(paths)

        if isinstance(action, Operator):
            if isinstance(action, Choice):
                new_paths = []
                for child in action:
                    child_paths = self.__choose_subprocess_paths(self, child, paths)
                    new_paths.extend(child_paths)
                paths = new_paths
            else:
                for child in action:
                    paths = self.__choose_subprocess_paths(self, child, paths)
        elif isinstance(action, Behaviour):
            if paths:
                previous = paths[-1]
                paths[-1] = previous.append(action.name)
            else:
                paths.append([action.name])
        else:
            raise NotImplementedError

        return paths


class LinearStrategy(SeparationStrategy):

    strategy = LinearExtractor
