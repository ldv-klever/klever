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

import os
import glob

from klever.core.utils import make_relative_path
from klever.core.pfg.abstractions.files_repr import File
from klever.core.pfg.abstractions.fragments_repr import Fragment


class Program:

    def __init__(self, logger, clade, source_paths, memory_efficient_mode=False, skip_missing_files=False):
        """
        The class that represents a program as different data structures: graphs of files or units. Also, it provides
        common methods to extract, modify or delete fragments and other information.

        :param logger: Logger object.
        :param clade: Clade object.
        :param source_paths: Iterable with paths to source code.
        :param memory_efficient_mode: Can we build a call graph?
        :param skip_missing_files: Tolerate errors when a CC input file is missing.
        """
        self.logger = logger
        self.clade = clade
        self.source_paths = source_paths
        self._files = {}
        self._fragments = {}
        self.__divide(skip_missing_files)
        if not memory_efficient_mode:
            self.logger.info("Extract dependencies between files from the program callgraph")
            # This is very memory inefficient operation, so for Linux this is an optional step to prevent consuming
            # gigabytes of memory
            self.__establish_dependencies()

    def create_fragment(self, name, files, add=False):
        """
        Create a fragment and if necessary add it to the extracted program fragments collection.

        :param name: Name string.
        :param files: Files objects.
        :param add: Add to the collection.
        :return: Fragment object.
        """
        if not all(isinstance(f, File) for f in files):
            raise ValueError('Provide File objects but not paths')

        fragment = Fragment(name)
        fragment.files.update(files)

        if add:
            self.add_fragment(fragment)
        return fragment

    def add_fragment(self, fragment):
        if fragment.name not in self._fragments:
            self._fragments[fragment.name] = fragment
        else:
            if not self._fragments[fragment.name].files.symmetric_difference(fragment.files):
                self.logger.warning("There are several equal fragments {!r} extracted, keep only one".
                                    format(fragment.name))
            else:
                raise ValueError("Cannot create a duplicate fragment {!r}".format(fragment.name))

    def collect_files_from_commands(self, cmd_type, cmds, parent_dir=None):
        """
        Create a fragment from the linker command. It adds to the fragment all files from commands of specified type
        that finally provide sources to this linking command.

        :param cmd_type: Type of the compiling command.
        :param cmds: command descriptions.
        :param parent_dir: Ignore files that placed in other directories than given.

        :return: A set of files (paths).
        """
        files = set()
        for desc in cmds:
            for in_file in desc['in']:
                if not in_file.endswith('.c'):
                    self.logger.warning("You should implement more strict filters to reject {!r} commands with such "
                                        "input files as {!r}".format(cmd_type, in_file))
                    continue
                if in_file not in self._files:
                    self.logger.warning(f"File {in_file} was not imported")
                    continue

                if not parent_dir or (parent_dir and os.path.dirname(in_file) == parent_dir):
                    file = self._files[in_file]
                    files.add(file)

        if len(files) == 0:
            self.logger.warning("Cannot find C files for {} commands".format(cmd_type))

        return files

    def create_fragment_from_linker_cmds(self, identifier, fragmentation_set_conf, name, sep_nestd=False, add=False,
                                         cmd_type='CC'):
        """
        Create a fragment from the linker command. It adds to the fragment all files from commands of specified type
        that finally provide sources to this linking command.

        :param identifier: Linker command identifier.
        :param fragmentation_set_conf: Dictionary with configuration.
        :param name: Name of the fragment.
        :param sep_nestd: Ignore files that placed in other directories than directory of the out file of the command.
        :param add: Add the fragment to the collection.
        :param cmd_type: Type of the compiling command.
        :return: Fragment object.
        """
        cmds = self.clade.get_root_cmds_by_type(identifier, cmd_type)
        files = self.collect_files_from_commands(cmd_type, map(self.clade.get_cmd, cmds),
                                                 os.path.dirname(fragmentation_set_conf['out'][0]) if sep_nestd
                                                 else None)
        if not files:
            self.logger.warning('Cannot find C files for linker command {!r}'.format(name))
        fragment = self.create_fragment(name, files, add=add)
        return fragment

    def cmnds_recursive_tree_traversing(self, compilation_kind, root_kinds):
        # Build a dict out -> cmd
        roots = {kind: {desc['out'][0]: desc for desc in self.clade.get_all_cmds_by_type(kind) if desc['out']}
                 for kind in root_kinds}

        # Go over roots
        result = {}
        for root_kind in root_kinds:
            for root_id, root_desc in roots[root_kind].items():
                leaves = set()
                non_leaves = [root_desc]
                self.logger.debug(f'Get {root_kind} command {root_desc["id"]}')

                # Search for leaves traversing commands
                while non_leaves:
                    desc = non_leaves.pop()

                    using = self.clade.get_root_cmds(desc['id'])
                    if using:
                        self.logger.debug(f'Cmd {desc["out"][0]} has {len(using)} children')
                        non_leaves.extend([self.clade.get_cmd(identifier) for identifier in using])
                    else:
                        # This is likely a compilation out
                        self.logger.debug(f'No children {desc["out"][0]}')
                        files = self.collect_files_from_commands(compilation_kind, (desc,))
                        leaves.update(files)

                # Save the result
                result[root_id] = leaves

        return result

    def remove_fragment(self, fragment):
        """
        Remove the fragment from the collection.

        :param fragment: Fragment object or fragment name.
        """
        if isinstance(fragment, Fragment):
            name = fragment.name
        else:
            name = fragment

        if name not in self._fragments:
            raise ValueError("Cannot remove already missing fragment {!r}".format(fragment.name))

        del self._fragments[name]

    @property
    def files(self):
        """Return an iterator over File objects."""
        return self._files.values()

    @property
    def fragments(self):
        """Return an iterator over Fragment objects."""
        return self._fragments.values()

    @property
    def target_fragments(self):
        """
        Return a set of only target fragments.

        :return: Set of Fragment objects.
        """
        return {f for f in self.fragments if f.target}

    def get_fragment_successors(self, fragment):
        """
        Successors of the fragment collected on the base of the program callgraph.

        :param fragment: Fragment object.
        :return: A set of Fragment objects.
        """
        successors = set()
        for file in fragment.files:
            successors.update(file.successors)
        successors = self.get_fragments_with_files(successors)
        return successors.difference({fragment})

    def get_fragment_predecessors(self, fragment):
        """
        Predecessors of the fragment collected on the base of the program callgraph.

        :param fragment: Fragment object.
        :return: Set of Fragment objects.
        """
        predecessors = set()
        for file in fragment.files:
            predecessors.update(file.predecessors)
        predecessors = self.get_fragments_with_files(predecessors)
        return predecessors.difference({fragment})

    def get_files_for_expressions(self, expressions):
        """
        Get files matched by the given expressions. These expressions can contain function names, file names, file or
        patterns and names of units.

        :param expressions: Strings.
        :return: Set of File objects, set of matched expressions.
        """
        # Copy to avoid modifying external data
        files = set()
        rest = set(expressions)
        frags, matched = self.get_fragments(rest)
        rest.difference_update(matched)
        for fragment in frags:
            files_to_add = fragment.unique_files if fragment.unique_files else fragment.files
            files.update(files_to_add)
        new_files, matched = self.get_files_by_expressions(rest)
        files.update(new_files)
        rest.difference_update(matched)

        return files, expressions.difference(rest)

    def get_files_by_expressions(self, expressions):
        """
        Find files by expressions. Matches files by names of files, directories, glob expressions or function names.

        :param expressions: Strings.
        :return: Set of Files objects, set of matched expressions.
        """
        # Matched expressions
        matched = set()
        # Found files
        suitable_files = set()
        # Optimizations: collect in advance absolute file paths
        convert = self.clade.get_storage_path
        reversed_paths = {f.abs_path: f for f in self.files}
        all_abs_files = set(reversed_paths.keys())
        all_abs_dirs = {}
        for file in all_abs_files:
            dirname = os.path.dirname(file)
            if dirname not in all_abs_dirs:
                all_abs_dirs[dirname] = set()
            all_abs_dirs[dirname].add(file)
        matched_abs_files = set()

        # First try globes
        for path in self.source_paths + ['']:
            for expr in expressions:
                suits = False
                expr_path = os.path.join(path, expr)
                abs_expr_path = convert(expr_path)
                files = set(glob.glob(abs_expr_path, recursive=True))
                dirs = {f for f in files if os.path.isdir(f)}
                files = {f for f in files if os.path.isfile(f)}

                for file in files:
                    if file in matched_abs_files:
                        continue

                    if file in all_abs_files:
                        matched_abs_files.add(file)
                        suitable_files.add(reversed_paths[file])
                        if not suits:
                            matched.add(expr)
                            suits = True
                for directory in dirs:
                    if directory in all_abs_dirs:
                        for file in all_abs_dirs[directory]:
                            if file in matched_abs_files:
                                continue
                            matched_abs_files.add(file)
                            suitable_files.add(reversed_paths[file])
                            if not suits:
                                matched.add(expr)
                                suits = True

        # Check function names
        rest = expressions.difference(matched)
        if rest:
            for file in (f for f in self.files if f not in suitable_files):
                matched_funcs = set(file.export_functions.keys()).intersection(rest)
                if matched_funcs:
                    suitable_files.add(file)
                    matched.update(matched_funcs)

        return suitable_files, matched

    def get_fragment(self, name):
        """
        Find a fragment if it is exist.

        :param name: Name of the Fragment.
        :return: Fragment or None.
        """
        return self._fragments.get(name)

    def get_fragments(self, names):
        """
        Find particular fragments matched by name.

        :param names: Names of Fragment objects.
        :return: Set of Fragment objects, set of matched names.
        """
        frags = set()
        matched = set()
        for name in names:
            if name in self._fragments:
                frags.add(self._fragments[name])
                matched.add(name)
        return frags, matched

    def get_fragments_with_files(self, files):
        """
        Find fragments that contain given files.


        :param files: File names or File objects.
        :return: Set of Fragment objects.
        """
        frags = set()
        files = {f if isinstance(f, str) else f.name for f in files}
        if files:
            for frag in self.fragments:
                if {f.name for f in frag.files}.intersection(files):
                    frags.add(frag)
        return frags

    def get_files_calling_functions(self, functions):
        """
        Get files that call global functions provided as an argument.

        :param functions: Function names.
        :return: File objects.
        """
        files = set()
        if functions:
            for file in self.files:
                if set(file.import_functions.keys()).intersection(functions):
                    files.add(file)
        return files

    def collect_dependencies(self, files, filter_func=lambda x: True, depth=None, max_files=None):
        """
        Function recursively searched files that provide functions to the given files.

        :param files: File objects.
        :param filter_func: Function that can filter files if necessary.
        :param depth: Max number of edges from one of the given file to a file that can be included. Or None.
        :param max_files: Max number of files that can be added.
        :return: A set of files with the given ones.
        """
        layer = files
        deps = set()
        while layer and (depth is None or depth > 0) and (max_files is None or max_files > 0):
            new_layer = set()
            for file in layer:
                deps.add(file)
                if max_files:
                    max_files -= 1
                if max_files is not None and max_files == 0:
                    break

                for dep in file.successors:
                    if dep not in deps and dep not in new_layer and dep not in layer and filter_func(dep):
                        new_layer.add(dep)

            layer = new_layer
            if depth is not None:
                depth -= 1

        return deps

    def __divide(self, skip_missing_files=False):
        """Analyze CC commands and add all found .c files for further program decomposition."""
        # Out file is used just to get an identifier for the fragment, thus it is Ok to use a random first. Later we
        # check that all fragments have unique names
        convert = self.clade.get_storage_path
        for desc in (d for d in self.clade.compilation_cmds if d.get('out') and len(d.get('out')) > 0):
            identifier = desc['id']
            for name in desc.get('in'):
                if name not in self._files:
                    file = File(name)
                    for path in self.source_paths:
                        abs_file = convert(file.name)
                        if os.path.isfile(abs_file):
                            file.abs_path = abs_file
                            break
                        abs_file = convert(os.path.join(path, file.name))
                        if os.path.isfile(abs_file):
                            file.abs_path = abs_file
                            break
                    else:
                        msg = 'Cannot calculate path to existing file {!r}'.format(file.name)
                        if skip_missing_files:
                            self.logger.warning(msg)
                            continue

                        raise RuntimeError(msg)

                    file.cmd_id = identifier
                    file.cmd_type = desc['type']
                    try:
                        file.size = self.clade.get_file_size(name)
                    except (KeyError, IndexError):
                        file.size = 0
                    self._files[name] = file

    def __establish_dependencies(self):
        """
        Analyze the callgraph of the program and add to each File object function names that are exported and function
        names that are imported with links to File objects that export these functions. This function requires an
        extremely huge amount of memory if the program is very big. This is because the callgraph itself can be quite
        large.
        """
        cg = self.clade.callgraph
        fs = self.clade.functions_by_file

        # Fulfil callgraph dependencies
        for path, functions in ((p, f) for p, f in cg.items() if p in self._files):
            file_repr = self._files[path]
            for func, func_desc in functions.items():
                tp = func_desc.get('type', 'static')
                if tp != 'static':
                    file_repr.add_export_function(func)

                for called_definition_scope, called_functions in \
                        ((s, d) for s, d in func_desc.get('calls', {}).items()
                         if s != path and s != 'unknown' and s in self._files):
                    called_definition_file = self._files[called_definition_scope]
                    # Beware of such bugs in callgraph
                    for called_function in (c for c in called_functions
                                            if fs.get(called_definition_scope, {}).get(c, {}).
                                            get('type', 'static') != 'static'):
                        match_score = list(called_functions[called_function].values())[0]["match_type"]
                        file_repr.add_import_function(called_function, called_definition_file, match_score)

        # Add rest global functions
        for path, functions in ((p, f) for p, f in fs.items() if p in self._files):
            file_repr = self._files[path]
            for func, func_desc in functions.items():
                tp = func_desc.get('type', 'static')
                if tp != 'static':
                    file_repr.add_export_function(func)
