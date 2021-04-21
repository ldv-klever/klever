#
# Copyright (c) 2021 ISP RAS (http://www.ispras.ru)
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

from klever.core.vtg.emg.decomposition.scenario import Scenario
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy, ScenarioExtractor
from klever.core.vtg.emg.common.process.actions import Choice, Operator, Concatenation, Action, Behaviour, Subprocess


class LinearExtractor(ScenarioExtractor):
    """
    This class implements a factory that generates Scenario instances that do not have choices. Instead the factory
    provides more scenarios that should cover all alternatives from the provided process.
    """

    def _new_scenarios(self, paths, action=None):
        def add_scenario_from_path(processing_path, savepoint=None):
            new_scenario = Scenario(savepoint)
            new_scenario.initial_action = Concatenation()
            for behaviour in processing_path:
                new_scenario.add_action_copy(behaviour, new_scenario.initial_action)
                if behaviour.name not in new_scenario.actions:
                    new_description = copy.copy(self._actions[behaviour.name])
                    new_scenario.actions[behaviour.name] = new_description
            return new_scenario

        if not action or isinstance(action, Subprocess):
            for path in paths:
                sps = list(action.savepoints) if action else [None]
                for sp in sps:
                    yield add_scenario_from_path(path, sp)
        else:
            suffixes = []
            check = set()
            for path in [p for p in paths if str(action) in {a.name for a in p}]:
                index = [a.name for a in path].index(str(action))
                new_path = path[index:]
                str_path = '++'.join([a.name for a in new_path])
                if str_path not in check:
                    check.add(str_path)
                    suffixes.append(new_path)

            for sp in action.savepoints:
                for path in suffixes:
                    yield add_scenario_from_path(path, sp)

    def _get_scenarios_for_root_savepoints(self, root: Action):
        paths, subp_paths = self.__determine_paths()

        self.logger.debug('Generate main scenarios')
        yield from self._new_scenarios(paths)
        for action in (a for a in self._actions.values() if a.savepoints):
            self.logger.debug(f'Generate scenarios with savepoints for action {str(action)}')
            if isinstance(action, Subprocess):
                yield from self._new_scenarios(subp_paths[str(action)], action)
            else:
                yield from self._new_scenarios(paths, action)

    def __determine_paths(self):
        subp_to_paths = dict()
        # Collect subprocesses and possible different paths
        for subprocess_desc in self._actions.filter(include={Subprocess}):
            subp_to_paths[str(subprocess_desc)] = self.__choose_subprocess_paths(subprocess_desc.action, [])
        # Add the main path
        initial_paths = self.__choose_subprocess_paths(self._actions.initial_action, [])

        while self.__path_dependencies(initial_paths):
            for dependency in self.__path_dependencies(initial_paths):
                # First, do substitutions
                for subprocess, paths in list(subp_to_paths.items()):
                    if subprocess != dependency:
                        new_paths = []
                        for path in paths:
                            if path[-1].name == dependency:
                                suffixes = [p for p in subp_to_paths[dependency] if p[-1].name != dependency and
                                            p[-1].name != subprocess]
                                if suffixes:
                                    newly_created = self.__do_substitution(path, suffixes)
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
                            if path[-1].name == subprocess:
                                recursion_paths.append(path)
                            else:
                                assert not path[-1].kind is Subprocess
                                terminal_paths.append(path)
                        
                        new_paths = []
                        for recursive_path in recursion_paths:
                            new_paths.extend(self.__do_substitution(recursive_path, terminal_paths))

                        subp_to_paths[subprocess] = new_paths + terminal_paths

            # Check the rest subprocesses
            for subprocess, paths in subp_to_paths.items():
                new_subp_paths = []
                for path in subp_to_paths[subprocess]:
                    if path[-1].kind is Subprocess and not self.__path_dependencies(subp_to_paths[path[-1].name]):
                        new_subp_paths.extend(self.__do_substitution(path, subp_to_paths[path[-1].name]))
                    else:
                        new_subp_paths.append(path)
                subp_to_paths[subprocess] = new_subp_paths

            new_initial_paths = []
            for path in initial_paths:
                if path[-1].kind is Subprocess and not self.__path_dependencies(subp_to_paths[path[-1].name]):
                    new_initial_paths.extend(self.__do_substitution(path, subp_to_paths[path[-1].name]))
                else:
                    new_initial_paths.append(path)
            initial_paths = new_initial_paths

        return initial_paths, subp_to_paths

    @staticmethod
    def __inclusive_paths(path1, path2):
        if len(path1) > (1 + len(path2)):
            return False

        for index, action in enumerate(path1[:-1]):
            if path2[index].name != action.name:
                return False

        return True

    def __do_substitution(self, origin, suffixes):
        assert suffixes
        return [origin[:-1] + suffix for suffix in suffixes if not self.__inclusive_paths(origin, suffix)]

    @staticmethod
    def __path_dependencies(paths):
        return {path[-1].name for path in paths if path[-1].kind is Subprocess}

    def __choose_subprocess_paths(self, action: Behaviour, prev_paths: list):
        """
        Collect unique paths till to jumps to subprocesses. Example:
        p := <a>.(<b>.{c} | {d}) | <f> 
        The function should return the following paths:
        [a, b, c], [a, d], [f]
        """
        if isinstance(action, Operator):
            if isinstance(action, Choice):
                paths = []
                for child in action:
                    child_paths = self.__choose_subprocess_paths(child, prev_paths)
                    paths.extend(child_paths)
            else:
                # Copy each path!
                paths = [list(p) for p in prev_paths]
                for child in action:
                    paths = self.__choose_subprocess_paths(child, paths)
        elif isinstance(action, Behaviour):
            paths = [list(p) for p in prev_paths]
            if paths:
                paths[-1] += [action]
            else:
                paths.append([action])
        else:
            raise NotImplementedError

        return paths


class LinearStrategy(SeparationStrategy):

    strategy = LinearExtractor