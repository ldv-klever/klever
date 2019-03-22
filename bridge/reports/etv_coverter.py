import argparse
import json

from django.utils.functional import cached_property


def get_error_trace_nodes(data):
    err_path = []
    must_have_thread = False
    curr_node = data['violation nodes'][0]
    if not isinstance(data['nodes'][curr_node][0], int):
        raise ValueError('Error traces with one path are supported')
    while curr_node != data['entry node']:
        if not isinstance(data['nodes'][curr_node][0], int):
            raise ValueError('Error traces with one path are supported')
        curr_in_edge = data['edges'][data['nodes'][curr_node][0]]
        if 'thread' in curr_in_edge:
            must_have_thread = True
        elif must_have_thread:
            raise ValueError("All error trace edges must have thread identifier ('0' or '1')")
        err_path.insert(0, data['nodes'][curr_node][0])
        curr_node = curr_in_edge['source node']
    return err_path


class ConvertTrace:
    def __init__(self, error_trace):
        self.nodes = get_error_trace_nodes(error_trace)
        self.edges = error_trace['edges']
        self.files = error_trace.get('files', [])
        self.actions = error_trace.get('actions', [])
        self.callback_actions = error_trace.get('callback actions', [])
        self.functions = error_trace.get('funcs', [])
        self.curr_file = None
        self.index = 0

        self._data = {'format': 1, 'files': self.files}
        self.pointer = None

    @property
    def data(self):
        self.__parse_trace()
        return self._data

    @cached_property
    def has_global(self):
        for n in self.nodes:
            if self.first_thread == self.edges[n]['thread'] and 'enter' in self.edges[n]:
                return False
        return True

    @cached_property
    def first_thread(self):
        return self.edges[self.nodes[0]]['thread']

    def __fill_globals(self):
        self._data['global'] = []

        if not self.has_global:
            return
        while self.index < len(self.nodes):
            if self.edge['thread'] != self.first_thread:
                # Thread has switched
                return
            if not self.edge.get('source'):
                continue
            line_data = {'line': self.line, 'file': self.file, 'source': self.edge['source']}
            if self.edge.get('assumption'):
                line_data['assumption'] = self.edge['assumption']
            if self.edge.get('warn'):
                line_data['note'] = self.edge['warn']
            elif self.edge.get('note'):
                line_data['note'] = self.edge['note']
            if self.edge.get('entry_point'):
                line_data['display'] = self.edge['entry_point']
            self._data['global'].append(line_data)
            self.index += 1

    @property
    def edge(self):
        return self.edges[self.nodes[self.index]]

    @property
    def file(self):
        if 'file' in self.edge:
            self.curr_file = self.edge['file']
        return self.curr_file

    @property
    def line(self):
        return self.edge.get('start line') if self.file is not None else None

    def __enter_node(self, node):
        node.parent = self.pointer
        if self.pointer:
            self.pointer.children.append(node)
        self.pointer = node

    def __enter_thread(self):
        if self.pointer and self.pointer.thread == self.edge['thread']:
            # We are already in the needed thread
            return
        self.__enter_node(NodeObject('thread', thread=self.edge['thread']))

    def __enter_action(self):
        if self.pointer.action and self.pointer.action == self.actions[self.edge['action']]:
            # We are already in the same action
            return
        self.__enter_node(NodeObject(
            'action', line=self.line, file=self.file,
            display=self.actions[self.edge['action']],
            callback=self.edge['action'] in self.callback_actions
        ))

    def __exit_action(self):
        if self.pointer.parent is None:
            raise ValueError("Can't exit the action")
        self.pointer = self.pointer.parent

    def __enter_function(self):
        self.__enter_node(NodeObject(
            'function', line=self.line, file=self.file, source=self.edge.get('source'),
            display=self.edge.get('entry_point') or self.functions[self.edge['enter']],
            condition=self.edge.get('condition'), assumption=self.edge.get('assumption'),
            note=self.edge.get('warn') or self.edge.get('note'), violation=bool(self.edge.get('warn'))
        ))

    def __exit_function(self):
        parent = self.pointer
        # Exit thread and action if we are inside
        while parent:
            if parent.type == 'function':
                self.pointer = parent.parent
                if parent.double_return:
                    # If we need double return, then return from the current pointer also
                    self.__exit_function()
                return
            parent = parent.parent
        raise ValueError("Can't exit the function")

    def __add_statement(self):
        self.pointer.children.append(NodeObject(
            'statement', line=self.line, file=self.file,
            source=self.edge.get('source'), display=self.edge.get('entry_point'),
            condition=self.edge.get('condition'), assumption=self.edge.get('assumption'),
            note=self.edge.get('warn') or self.edge.get('note'), violation=bool(self.edge.get('warn'))
        ))

    def __go_to_root(self):
        while self.pointer.parent:
            self.pointer = self.pointer.parent

    def __parse_trace(self):
        self.__fill_globals()
        self.__enter_thread()

        while self.index < len(self.nodes):
            if self.edge['thread'] != self.pointer.thread:
                # If thread with this id was not created the pointer will not be changed
                self.pointer = self.pointer.exit_to_thread(self.edge['thread'])
                # if self.pointer.action and 'action' not in self.edge:
                #     # Exit action if we are inside and
                #     self.__exit_action()
                self.__enter_thread()

            if 'action' in self.edge:
                # If we are in the different action scope then return from action first
                if self.pointer.action and self.pointer.action != self.actions[self.edge['action']]:
                    # New action in the same scope
                    self.__exit_action()
                self.__enter_action()

            if 'enter' in self.edge:
                self.__enter_function()
                if 'return' in self.edge:
                    if self.edge['return'] == self.edge['enter']:
                        # Return from the same function
                        self.__exit_function()
                    else:
                        # Double return!
                        self.pointer.double_return = True
            else:
                self.__add_statement()

                # We are in thread/function/action scope
                if 'return' in self.edge:
                    self.__exit_function()

            self.index += 1
        self.__go_to_root()

        print('MAX depth is:', self.pointer.max_depth)

        self._data['trace'] = self.pointer.serialize()


class NodeObject:
    def __init__(self, node_type, **kwargs):
        self.parent = None
        self.children = []
        self.double_return = False

        self.type = node_type
        self._thread = kwargs.get('thread')
        self._line = kwargs.get('line')
        self._file = kwargs.get('file')
        self._source = kwargs.get('source')
        self._display = kwargs.get('display')
        self._condition = kwargs.get('condition')
        self._assumption = kwargs.get('assumption')
        self._note = kwargs.get('note')
        self._violation = kwargs.get('violation')
        self._callback = kwargs.get('callback')

    @cached_property
    def thread(self):
        if self.type == 'thread':
            return self._thread
        return self.parent.thread if self.parent else None

    def exit_to_thread(self, thread_id):
        parent = self.parent
        while parent:
            if parent.thread == thread_id:
                return parent
            parent = parent.parent
        return self

    @cached_property
    def action(self):
        return self._display if self.type == 'action' else None

    @property
    def max_depth(self):
        max_depth = 0
        for child in self.children:
            branch_depth = child.max_depth + 1
            max_depth = max(max_depth, branch_depth)
        return max_depth

    def serialize(self):
        data = {'type': self.type}

        if self.type == 'thread':
            data['thread'] = self._thread
        else:
            data['line'] = self._line
            data['file'] = self._file
            if self._display:
                data['display'] = self._display

        if self.type == 'action' and self._callback:
            data['callback'] = True

        if self.type == 'function' or self.type == 'statement':
            data['source'] = self._source
            if self._condition:
                data['condition'] = self._condition
            if self._assumption:
                data['assumption'] = self._assumption
            if self._note:
                data['note'] = self._note
                if self._violation:
                    data['violation'] = True

        if self.type != 'statement':
            data['children'] = list(child.serialize() for child in self.children)

        return data


HIGHLIGHT = {
    'x': 'ETVx',
    'y': 'ETVy',
    'z': 'ETVz'
}


def replace_positions(source, highlights):
    intervals = []
    repl_info = {}
    for c, k, v in highlights:
        if c in HIGHLIGHT:
            repl_info[k] = (v, HIGHLIGHT.get(c))
        intervals.append((k, v))
    prev_v = None
    for k, v in sorted(intervals):
        if k >= v:
            raise ValueError('Highlight interval is wrong')
        if prev_v is not None and prev_v > k:
            raise ValueError('Highlight intersections are not supported')
        prev_v = v
    for pos in sorted(repl_info.keys(), reverse=True):
        source = source[:pos] + \
                 '<span class="{}">'.format(repl_info[pos][1]) + \
                 source[pos:repl_info[pos][0]] + '</span>' + \
                 source[repl_info[pos][0]:]
    return source


def test_repl():
    source = '    cf_arg_5 = ldv_xmalloc(sizeof(struct ldv_struct_platform_instance_4));'
    print(replace_positions(source, [
        ['x', 27, 33],
        ['z', 34, 40]
    ]))
    print(replace_positions(source, [
        ['x', 27, 33],
        ['z', 33, 40]
    ]))
    print(replace_positions(source, [
        ['x', 40, 33],
        ['z', 31, 40]
    ]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('trace', type=str, help='Path to the error trace json')
    parser.add_argument('--out', type=str, help='Where to save new format')
    args = parser.parse_args()
    with open(args.trace, mode='r', encoding='utf-8') as fp:
        converter = ConvertTrace(json.load(fp))
    filename = args.out or 'new_et.json'
    with open(filename, mode='w', encoding='utf-8') as fp:
        json.dump(converter.data, fp, indent=2, sort_keys=True, ensure_ascii=False)
