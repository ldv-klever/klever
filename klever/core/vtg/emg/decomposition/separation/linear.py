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

from klever.core.vtg.emg.decomposition.scenario import Scenario, Path
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy, ScenarioExtractor
from klever.core.vtg.emg.common.process.actions import Choice, Operator, Concatenation, Action, Behaviour, Subprocess, \
    Block


class LinearExtractor(ScenarioExtractor):
    """
    This class implements a factory that generates Scenario instances that do not have choices. Instead the factory
    provides more scenarios that should cover all alternatives from the provided process.
    """

    def _new_scenarios(self, paths, action=None):
        def add_scenario_from_path(processing_path, savepoint=None):
            if processing_path.name and savepoint:
                name = f"{str(savepoint)} with {processing_path.name}"
            elif savepoint:
                name = str(savepoint)
            elif processing_path.name:
                name = processing_path.name
            else:
                name = "base"
            self.logger.info(f"Generate '{name}' scenario for path '{repr(processing_path)}'" +
                             (f" and savepoint '{str(savepoint)}'" if savepoint else ''))

            new_scenario = Scenario(self._process, savepoint, name)
            new_scenario.initial_action = Concatenation()
            for behaviour in processing_path:
                new_scenario.add_action_copy(behaviour, new_scenario.initial_action)
                if behaviour.name not in new_scenario.actions:
                    new_description = copy.deepcopy(self._actions[behaviour.name])
                    new_scenario.actions[behaviour.name] = new_description

                    # Transform blocks
                    if isinstance(new_description, Block) and new_description.condition and \
                            (isinstance(behaviour.my_operator, Choice) or
                             (isinstance(behaviour.my_operator, Concatenation)
                              and behaviour.my_operator.index(behaviour) == 0)):
                        self.logger.debug(
                            f"Convert conditions to assumptions in '{behaviour.name}' of '{name}' scenario")
                        for statement in reversed(new_description.condition):
                            new_description.statements.insert(0, f"ldv_assume({statement});")
                        new_description.condition = []
            return new_scenario

        if not action or isinstance(action, Subprocess):
            for path in paths:
                # Skip paths without savepoints and name
                sps = list(action.savepoints) if action else ([None] if path.name else [])
                for sp in sps:
                    yield add_scenario_from_path(path, sp)
        else:
            suffixes = set()
            for path in (p for p in paths if str(action) in {a.name for a in p}):
                index = [a.name for a in path].index(str(action))
                new_path = path[index:]
                new_path.name = path.name
                suffixes.add(new_path)

            for sp in action.savepoints:
                for path in suffixes:
                    yield add_scenario_from_path(path, sp)

    def _get_scenarios_for_root_savepoints(self, root: Action):
        paths, subp_paths = self.__determine_paths()

        self.logger.debug("Generate main scenarios")
        yield from self._new_scenarios(paths)
        for action in (a for a in self._actions.values() if a.savepoints):
            self.logger.debug(f"Generate scenarios with savepoints for action '{str(action)}'")
            if isinstance(action, Subprocess):
                yield from self._new_scenarios(subp_paths[str(action)], action)
            else:
                yield from self._new_scenarios(paths, action)

    def __determine_paths(self):
        subp_to_paths = {}
        # Collect subprocesses and possible different paths
        for subprocess_desc in self._actions.filter(include={Subprocess}):
            subp_to_paths[str(subprocess_desc)] = set(self.__choose_subprocess_paths(subprocess_desc.action, []))
        # Add the main path
        initial_paths = set(self.__choose_subprocess_paths(self._actions.initial_action, []))

        if len(initial_paths) == 1 and not self.__path_dependencies(initial_paths):
            # This is a separate case when there is the only path without subprocesses, we have to give a name to it
            tuple(initial_paths)[-1].add_name_suffix('base')

        while self.__path_dependencies(initial_paths):
            for dependency in self.__path_dependencies(initial_paths):
                # First, do substitutions
                for subprocess, paths in list(subp_to_paths.items()):
                    if subprocess != dependency:
                        new_paths = set()
                        for path in paths:
                            if path[-1].name == dependency:
                                suffixes = {p for p in subp_to_paths[dependency] if p[-1].name not in (dependency, subprocess)}
                                if suffixes:
                                    newly_created = self.__do_substitution(path, suffixes)
                                    new_paths.update(newly_created)
                                else:
                                    new_paths.add(path)
                            else:
                                new_paths.add(path)

                        # Now save new paths
                        subp_to_paths[subprocess] = new_paths

                    # Check that the dependency is not terminated and self-dependent only
                    new_deps = self.__path_dependencies(subp_to_paths[subprocess])
                    if len(new_deps) == 0 or (len(new_deps) == 1 and subprocess in new_deps):
                        # Determine terminal paths and do substitution removing the recursion
                        recursion_paths = set()
                        terminal_paths = set()

                        for path in subp_to_paths[subprocess]:
                            if path[-1].name == subprocess:
                                recursion_paths.add(path)
                            else:
                                assert path.terminal
                                terminal_paths.add(path)

                        new_paths = set()
                        for recursive_path in recursion_paths:
                            new_paths.update(self.__do_substitution(recursive_path, terminal_paths))

                        subp_to_paths[subprocess] = new_paths.union(terminal_paths)

            # Check the rest subprocesses
            for subprocess, paths in subp_to_paths.items():
                new_subp_paths = set()
                for path in paths:
                    if not path.terminal and not self.__path_dependencies(subp_to_paths[path[-1].name]):
                        new_subp_paths.update(self.__do_substitution(path, subp_to_paths[path[-1].name]))
                    else:
                        new_subp_paths.add(path)
                subp_to_paths[subprocess] = new_subp_paths

            new_initial_paths = set()
            for path in initial_paths:
                if not path.terminal and not self.__path_dependencies(subp_to_paths[path[-1].name]):
                    if not path.name and len(subp_to_paths[path[-1].name]) == 1 and \
                            not list(subp_to_paths[path[-1].name])[0].name:
                        single_path = list(subp_to_paths[path[-1].name])[0]
                        single_path.name = path[-1].name
                    new_initial_paths.update(self.__do_substitution(path, subp_to_paths[path[-1].name]))
                else:
                    new_initial_paths.add(path)
            initial_paths = new_initial_paths

        return initial_paths, subp_to_paths

    @staticmethod
    def __do_substitution(origin, suffixes):
        assert suffixes
        return {origin + suffix for suffix in suffixes if not origin.included(suffix)}

    @staticmethod
    def __path_dependencies(paths):
        return {path[-1].name for path in paths if not path.terminal}

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
                    # Determine name
                    first_actions = self._actions.first_actions(child, enter_subprocesses=False)
                    if len(first_actions) == 1:
                        name = first_actions.pop()
                    else:
                        name = None

                    child_paths = self.__choose_subprocess_paths(child, prev_paths)
                    if name:
                        for path in child_paths:
                            path.add_name_suffix(name)
                    paths.extend(child_paths)
            else:
                # Copy each path!
                paths = [Path(p) for p in prev_paths]
                for child in action:
                    paths = self.__choose_subprocess_paths(child, paths)
        elif isinstance(action, Behaviour):
            paths = [Path(p) for p in prev_paths]
            if paths:
                for path in paths:
                    path.append(action)
            else:
                new = Path()
                new.append(action)
                paths.append(new)
        else:
            raise NotImplementedError

        return paths


class LinearStrategy(SeparationStrategy):

    strategy = LinearExtractor
