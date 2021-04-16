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

    def __init__(self, logger: logging.Logger, actions: Actions):
        super().__init__(logger, actions)
        # This is a list of lists of choice options that we should chooce to reach some uncovered new choices.
        self.__scenario_choices = []
        self.__children_paths = collections.OrderedDict()
        self.__uncovered = None

        # Collect all choices
        self.__reset_covered()

    def _process_choice(self, scenario: Scenario, beh: BaseAction, operator: Operator = None):
        assert isinstance(beh, Choice), type(beh).__name__

        uncovered_children = [c for c in beh[:] if c in self.__uncovered]
        if uncovered_children:
            # Save paths to uncovered choices
            for unovered_child in uncovered_children[1:]:
                self.__children_paths[unovered_child] = list(self.__scenario_choices)
            new_choice = uncovered_children[0]
            self.__uncovered.remove(new_choice)
            if isinstance(new_choice, Operator):
                roots = self._actions.first_actions(new_choice)
                name = roots.pop()
            else:
                name = new_choice.name

            scenario.name = scenario.name + f'_{name}' if scenario.name else name
            if new_choice in self.__children_paths:
                del self.__children_paths[new_choice]
        else:
            current_target = list(self.__children_paths.keys())[0]
            for item in beh:
                if item in self.__children_paths[current_target]:
                    new_choice = item
                    break
            else:
                raise RuntimeError(f'Unknown choice at path to {current_target}')

        self.__scenario_choices.append(new_choice)

        if isinstance(new_choice, Operator):
            return self._fill_top_down(scenario, new_choice, operator)
        else:
            new_operator = scenario.add_action_copy(Concatenation(), operator)
            return self._fill_top_down(scenario, new_choice, new_operator)

    def _process_subprocess(self, scenario: Scenario, beh: BaseAction, operator: Operator = None):
        assert isinstance(beh, Behaviour)
        assert beh.kind is Subprocess

        new = self._process_leaf_action(scenario, beh, operator)
        if len(scenario.actions.behaviour(new.name)) == 1:
            child = beh.description.action
            new_action = self._fill_top_down(scenario, child)
            new.description.action = new_action
        return new

    def _new_scenario(self, root: Operator, savepoint: Savepoint = None):
        nsc = Scenario(savepoint)
        nsc.initial_action = Concatenation()
        for child in root:
            self._fill_top_down(nsc, child, nsc.initial_action)
        return nsc

    def _get_scenarios_for_root_savepoints(self, root: Action):
        def new_scenarios(rt, svp=None):
            self.__reset_covered()
            while len(self.__uncovered) > 0:
                current = len(self.__uncovered)
                self.__scenario_choices = []
                nsc = self._new_scenario(rt, svp)
                assert len(self.__uncovered) < current, 'Deadlock found'
                assert nsc.name
                self.logger.debug(f'Generate a new scenario {nsc.name}')
                yield nsc

        first_actual = self._actions.first_actions(root)
        assert len(first_actual) == 1, 'Support only the one first action'
        actual = self._actions.behaviour(first_actual.pop())
        assert len(actual) == 1, f'Support only the one first action behaviour'
        actual = actual.pop()

        if actual.description.savepoints:
            self.logger.debug('Generate scenarios for savepoints')
            for savepoint in actual.description.savepoints:
                if self.__uncovered is not None:
                    yield from new_scenarios(self._actions.initial_action, savepoint)
                else:
                    yield new_scenarios(self._actions.initial_action, savepoint)
        if self.__uncovered is not None:
            yield from new_scenarios(self._actions.initial_action)

    def __reset_covered(self):
        # Collect all choices
        choices = filter(lambda x: isinstance(x, Choice), self._actions.behaviour())
        if choices:
            self.__uncovered = list()
            for choice in choices:
                self.__uncovered.extend(choice[:])

    def __process_operator(self, scenario: Scenario, behaviour: Operator, operator: Operator = None):
        assert isinstance(behaviour, Operator), type(behaviour).__name__
        # We assume that any linear scenario has a single operator dot
        assert isinstance(operator, Concatenation)

        for child in behaviour:
            self._fill_top_down(scenario, child, operator)

        return operator

    def __determine_paths(self):
        subp_to_paths = dict()
        # Collect subprocesses and possible different paths
        for subprocess_desc in self._actions.filter(include=Subprocess):
            subp_to_paths[str(subprocess_desc)] = self.__choose_subprocess_paths(subprocess_desc.action, [])
        # Add the main path
        initial_paths = self.__choose_subprocess_paths(self._actions.initial_action, [])

        # Now we resolve terminal paths
        terminal_paths = dict()
        subprocess_names = set(subp_to_paths.keys())
        subprocesses_with_jumps = list(subprocess_names)
        
        while subprocesses_with_jumps:
            subp_name = subprocesses_with_jumps.pop()

            for path in list(subp_to_paths[subp_name]):
                if path[-1].name == subp_name:
                    continue
                elif path[-1].name in subprocess_names and path[-1].name not in subprocesses_with_jumps:
                    new_paths = [path + p for p in terminal_paths[path[-1].name]]
                    terminal_paths.setdefault(subp_name, list())
                    terminal_paths[subp_name].extend(new_paths)

                    # The path is processed                    
                elif path[-1].name in subprocess_names and path[-1].name in subprocesses_with_jumps:
                    continue
                else:
                    # This is a terminal path
                    terminal_paths.setdefault(subp_name, list())
                    terminal_paths[subp_name].append(path)
                    subp_to_paths[subp_name].remove(path)


    def determine_subprocess_dependencies(initial_paths, subp_to_paths):
        deps = dict()
        main_deps = [str(path[-1]) for path in initial_paths if str(path[-1]) in subp_to_paths]
        todo = [main_deps]
        while todo:
            subp_name = todo.pop()
            deps[subp_name] = set()
            deps[subp_name] = {str(path[-1]) for path in subp_to_paths[subp_name] 
                               if str(path[-1]) in subp_to_paths and str(path[-1]) in deps}
            for new in deps[subp_name]:
                if new not in todo:
                    todo.append(new)

        return main_deps, deps


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
