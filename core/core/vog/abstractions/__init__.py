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

import os
import glob

from core.vog.abstractions.files_repr import File
from core.vog.abstractions.fragments_repr import Fragment


class Dependencies:

    def __init__(self, logger, clade, source_paths):
        self.logger = logger
        self.clade = clade
        self.source_paths = source_paths
        self.cmdg = self.clade.CommandGraph()
        self.srcg = self.clade.SourceGraph()
        self._files = dict()
        self._fragments = dict()
        self.__divide()
        self.__establish_dependencies()

    def create_fragment(self, name, files, add=False):
        if not all(isinstance(f, File) for f in files):
            raise ValueError('Provide File objects but not paths')

        fragment = Fragment(name)
        fragment.files.update(files)

        if add:
            self.add_fragment(fragment)
        return fragment

    def remove_fragment(self, fragment):
        if isinstance(fragment, Fragment):
            name = fragment.name
        else:
            name = fragment

        if name not in self._fragments:
            raise ValueError("Cannot remove already missing fragment {!r}".format(fragment.name))
        else:
            del self._fragments[name]

    def add_fragment(self, fragment):
        if fragment.name not in self._fragments:
            self._fragments[fragment.name] = fragment
        else:
            raise ValueError("Cannot create a duplicate fragment {!r}".format(fragment.name))

    @property
    def files(self):
        return self._files.values()

    @property
    def fragments(self):
        return self._fragments.values()

    @property
    def target_fragments(self):
        return {f for f in self.fragments if f.target}

    def fragment_successors(self, fragment):
        successors = set()
        for file in fragment.files:
            successors.update(file.successors)
        successors = self.find_fragments_with_files(successors)
        return successors.difference({fragment})

    def fragment_predecessors(self, fragment):
        predecessors = set()
        for file in fragment.files:
            predecessors.update(file.predecessors)
        predecessors = self.find_fragments_with_files(predecessors)
        return predecessors.difference({fragment})

    def find_files_for_expressions(self, expressions):
        # Copy to avoid modifying external data
        files = set()
        rest = set(expressions)
        frags, matched = self.find_fragments_by_expressions(rest)
        rest.difference_update(matched)
        for fragment in frags:
            files.update(fragment.files)
        new_files, matched = self.find_files_by_expressions(rest)
        files.update(new_files)
        rest.difference_update(matched)

        return files, expressions.difference(rest)

    def find_files_by_expressions(self, expressions):
        # First try globes
        suitable_files = set()
        suitable_files_abs = set()
        matched = set()
        for path in self.source_paths + ['']:
            for expr in expressions:
                expr_path = os.path.join(path, expr)
                abs_expr_path = self.clade.FileStorage().convert_path(expr_path)
                files = set(glob.glob(abs_expr_path, recursive=True))
                files.difference_update(suitable_files_abs)
                dirs = {f for f in files if os.path.isdir(f)}
                files = {f for f in files if os.path.isfile(f)}
                if files or dirs:
                    for file in self.files:
                        abs_file = self.clade.FileStorage().convert_path(file.name)
                        if not os.path.isfile(abs_file):
                            abs_file = self.clade.FileStorage().convert_path(os.path.join(path, file.name))
                        if not os.path.isfile(abs_file):
                            self.logger.warning('Cannot calculate path to existing file {!r}'.format(file.name))
                            continue

                        if (abs_file in files or os.path.dirname(abs_file) in dirs) or ():
                            suitable_files_abs.add(abs_file)
                            matched.add(expr)
                            suitable_files.add(file)

        # Check function names
        rest = expressions.difference(matched)
        if rest:
            for file in (f for f in self.files if f not in suitable_files):
                matched_funcs = set(file.export_functions.keys()).intersection(rest)
                if matched_funcs:
                    suitable_files.add(file)
                    matched.update(matched_funcs)

        return suitable_files, matched

    def find_fragments_by_expressions(self, expressions):
        frags = set()
        matched = set()
        for name in expressions:
            if name in self._fragments:
                frags.add(self._fragments[name])
                matched.add(name)
        return frags, matched

    def find_fragments_with_files(self, files):
        frags = set()
        files = {f if isinstance(f, str) else f.name for f in files}
        if files:
            for frag in self.fragments:
                if {f.name for f in frag.files}.intersection(files):
                    frags.add(frag)
        return frags

    def find_files_that_use_functions(self, functions):
        files = set()
        if functions:
            for file in self.files:
                if set(file.import_functions.keys()).intersection(functions):
                    files.add(file)
        return files

    def create_fragment_from_ld(self, identifier, desc, name, cmdg, sep_nestd=False):
        ccs = cmdg.get_ccs_for_ld(identifier)

        files = set()
        for i, d in ccs:
            self.__check_cc(d)
            for in_file in d['in']:
                if not sep_nestd or (sep_nestd and os.path.dirname(in_file) == os.path.dirname(desc['out'][0])):
                    files.add(in_file)
        files_obj, matched = self.find_files_by_expressions(files)
        rest = files.difference(matched)
        if rest:
            raise ValueError('Cannot find files: {}'.format(', '.join(rest)))
        if not files_obj:
            raise ValueError('Cannot find C files for LD command {!r}'.format(name))
        fragment = self.create_fragment(name, files_obj)
        return fragment

    def collect_dependencies(self, files, filter_func=lambda x: True, depth=None, maxfrags=None):
        layer = files
        deps = set()
        while layer and (depth is None or depth > 0) and (maxfrags is None or maxfrags > 0):
            new_layer = set()
            for file in layer:
                deps.add(file)
                if maxfrags:
                    maxfrags -= 1
                if maxfrags is not None and maxfrags == 0:
                    break

                for dep in file.successors:
                    if dep not in deps and dep not in new_layer and dep not in layer and filter_func(dep):
                        new_layer.add(dep)

            layer = new_layer
            if depth is not None:
                depth -= 1

        return deps

    def __divide(self):
        # Out file is used just to get an identifier for the fragment, thus it is Ok to use a random first. Later we
        # check that all fragments have unique names
        for identifier, desc in ((i, d) for i, d in self.cmdg.CCs if d.get('out') and len(d.get('out')) > 0):
            for name in desc.get('in'):
                if name not in self._files:
                    file = File(name)
                    file.cc = str(identifier)
                    try:
                        file.size = list(self.srcg.get_sizes([name]).values())[0]
                    except (KeyError, IndexError):
                        file.size = 0
                    self._files[name] = file

    def __check_cc(self, desc):
        if len(desc['out']) != 1:
            raise NotImplementedError('CC build commands with more than one output file are not supported')

    def __establish_dependencies(self):
        cg = self.clade.CallGraph().graph
        fs = self.clade.FunctionsScopes().scope_to_funcs

        # Fulfil callgraph dependencies
        for path, functions in ((p, f) for p, f in cg.items() if p in self._files):
            file_repr = self._files[path]
            for func, func_desc in functions.items():
                tp = func_desc.get('type', 'static')
                if tp != 'static':
                    file_repr.export_functions.setdefault(func, set())

                for called_definition_scope, called_functions in \
                        ((s, d) for s, d in func_desc.get('calls', dict()).items()
                         if s != path and s != 'unknown' and s in self._files):
                    called = self._files[called_definition_scope]
                    # Beware of such bugs in callgraph
                    for called_function in (c for c in called_functions
                                            if fs.get(called_definition_scope, dict()).get(c, dict()).
                                                       get('type', 'static') != 'static'):
                        if called_function not in file_repr.import_functions:
                            file_repr.import_functions[called_function] = \
                                [called, list(called_functions[called_function].values())[0]["match_type"]]
                        elif file_repr.import_functions[called_function][0] != called:
                            self.logger.warning('Cannot import function {!r} from two places: {!r} and {!r}'.
                                           format(called_function, file_repr.import_functions[called_function],
                                                  called.name))
                            newmatch_type = list(called_functions[called_function].values())[0]["match_type"]
                            if newmatch_type > file_repr.import_functions[called_function][1]:
                                file_repr.import_functions[called_function] = [called, newmatch_type]

                        called.add_predecessor(file_repr)
                        called.export_functions.setdefault(func, set())
                        called.export_functions[func].add(file_repr)

        # Add rest global functions
        for path, functions in ((p, f) for p, f in fs.items() if p in self._files):
            file_repr = self._files[path]
            for func, func_desc in functions.items():
                tp = func_desc.get('type', 'static')
                if tp != 'static':
                    file_repr.export_functions.setdefault(func, set())
