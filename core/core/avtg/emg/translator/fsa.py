import copy

from core.avtg.emg.common.process import Subprocess


class FSA:

    def __init__(self, process):
        self.process = process
        self.initial_states = set()
        self.finite_states = set()
        self.states = set()
        self.__id_cnt = 0

        # Generate AST states
        self.__generate_states(process)

    def __iter__(self):
        self.__todo_set = set(self.initial_states)
        self.__processed_set = set()
        return self

    def __next__(self):
        if len(self.__todo_set) > 0:
            state = self.__todo_set.pop()
            self.__processed_set.add(state)

            for state in state.successors:
                if state not in self.__todo_set and state not in self.__processed_set:
                    self.__todo_set.add(state)

            return state

    def __generate_states(self, process):
        sb_asts = dict()
        sb_processed = set()
        asts = list()

        for name in [name for name in sorted(process.actions.keys()) if type(process.actions[name]) is Subprocess]:
            ast = copy.deepcopy(process.actions[name].process_ast)
            self.__generate_nodes(process, ast)
            sb_asts[name] = ast
        p_ast = copy.deepcopy(process.process_ast)
        self.initial_states = self.__generate_nodes(process, p_ast)
        asts.append([p_ast, None])

        while len(asts) > 0:
            ast, prev = asts.pop()

            if ast['type'] == 'choice':
                for action in ast['actions']:
                    asts.append([action, prev])
            elif ast['type'] == 'concatenation':
                for action in ast['actions']:
                    asts.append([action, prev])
                    prev = action
            elif ast['type'] == 'subprocess':
                pair = "{} {}".format(ast['name'], str(prev))
                if pair not in sb_processed:
                    sb_processed.add(pair)
                    asts.append([sb_asts[ast['name']], prev])
            else:
                for pre_state in self.__resolve_last(prev):
                    ast['node'].predecessors.add(pre_state)
                    pre_state.successors.add(ast['node'])

    def __resolve_last(self, pr_ast):
        if not pr_ast:
            return set()

        asts = [pr_ast]
        last = set()

        while len(asts) > 0:
            ast = asts.pop()

            if ast['type'] == 'choice':
                for action in ast['actions']:
                    asts.append(action)
            elif ast['type'] == 'concatenation':
                asts.append(ast['actions'][-1])
            else:
                last.add(ast['node'])

        return last

    def __generate_nodes(self, process, pr_ast):
        asts = [[pr_ast, True]]
        initial_states = set()

        while len(asts) > 0:
            ast, initflag = asts.pop()

            if ast['type'] == 'choice':
                for action in ast['actions']:
                    asts.append([action, initflag])
            elif ast['type'] == 'concatenation':
                for action in ast['actions']:
                    if initflag:
                        asts.append([action, initflag])
                        initflag = False
                    else:
                        asts.append([action, initflag])
            elif ast['type'] != 'subprocess':
                node = Node(ast, self.__id_cnt)
                self.__id_cnt += 1
                node.action = process.actions[ast['name']]
                self.states.add(node)
                ast['node'] = node

                if initflag:
                    initial_states.add(node)

        return initial_states


class Node:

    def __init__(self, desc, identifier):
        self.identifier = identifier
        self.desc = desc
        self.predecessors = set()
        self.successors = set()
        self.action = None

    def replace_successor(self, old, new):
        self.successors.remove(old)
        self.successors.add(new)

    def replace_predecessor(self, old, new):
        self.predecessors.remove(old)
        self.predecessors.add(new)

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
