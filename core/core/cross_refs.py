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

import core.utils
from core.highlight import Highlight


class CrossRefs:
    INDEX_DATA_FORMAT_VERSION = 1

    def __init__(self, conf, logger, clade, file_name, new_file_name, common_dirs, common_prefix=''):
        self.conf = conf
        self.logger = logger
        self.clade = clade
        self.file_name = file_name
        self.new_file_name = new_file_name
        self.common_dirs = common_dirs
        self.common_prefix = common_prefix

    def get_cross_refs(self):
        with open(self.new_file_name) as fp:
            try:
                src = fp.read()
            # Source files with non UTF-8 encoding will not be analyzed. There should not be many such source files.
            except UnicodeDecodeError:
                return

        highlight = Highlight(self.logger, src)
        highlight.highlight()

        # Get raw references to/from for a given source file. There is the only key-value pair in dictionaries
        # returned by Clade where keys are always source file names.
        raw_refs_to = {
            'decl_func': [],
            'def_func': [],
            'def_macro': []
        }
        clade_refs_to = self.clade.get_ref_to([self.file_name])
        if clade_refs_to:
            raw_refs_to.update(list(clade_refs_to.values())[0])

        raw_refs_from = {
            'call': [],
            'expand': []
        }
        clade_refs_from = self.clade.get_ref_from([self.file_name])
        if clade_refs_from:
            raw_refs_from.update(list(clade_refs_from.values())[0])

        # Get full list of referred source file names.
        ref_src_files = set()
        for ref_to_kind in ('decl_func', 'def_func', 'def_macro'):
            for raw_ref_to in raw_refs_to[ref_to_kind]:
                ref_src_files.add(raw_ref_to[1][0])
        for ref_from_kind in ('call', 'expand'):
            for raw_ref_from in raw_refs_from[ref_from_kind]:
                ref_src_files.add(raw_ref_from[1][0])
        # Remove considered file from list - there is a special reference to it (Null).
        if self.file_name in ref_src_files:
            ref_src_files.remove(self.file_name)
        ref_src_files = sorted(list(ref_src_files))

        # This dictionary will allow to get indexes in source files list easily.
        ref_src_files_dict = {ref_src_file: i for i, ref_src_file in enumerate(ref_src_files)}
        ref_src_files_dict[self.file_name] = None

        # Convert references to.
        refs_to_func_defs = []
        refs_to_func_decls = []
        refs_to_macro_defs = []
        for ref_to_kind in ('def_macro', 'def_func', 'decl_func'):
            refs_to = refs_to_func_defs if ref_to_kind == 'def_func' else refs_to_func_decls \
                if ref_to_kind == 'decl_func' else refs_to_macro_defs
            for raw_ref_to in raw_refs_to[ref_to_kind]:
                # Do not add references to function definitions/declarations if there are already references to macro
                # definitions at the same places.
                if ref_to_kind != 'def_macro':
                    is_exist = False
                    for ref_to_macro_def in refs_to_macro_defs:
                        if ref_to_macro_def[0] == raw_ref_to[0]:
                            is_exist = True
                            break
                    if is_exist:
                        continue

                # Do not add references to function declarations if there are already references to function definitions
                # at the same places.
                if ref_to_kind == 'decl_func':
                    is_exist = False
                    for ref_to_func_def in refs_to_func_defs:
                        if ref_to_func_def[0] == raw_ref_to[0]:
                            is_exist = True
                            break
                    if is_exist:
                        continue

                # TODO: will it work if there will be multiple declarations of the same entity in the same source file?
                refs_to.append([
                    # Take location of entity usage as is.
                    raw_ref_to[0],
                    [
                        # Convert referred source file name to index in source files list.
                        ref_src_files_dict[raw_ref_to[1][0]],
                        # Take line number of entity definition as is.
                        raw_ref_to[1][1] if ref_to_kind != 'decl_func' else [raw_ref_to[1][1]]
                    ]
                ])

        # Convert references from.
        refs_from_func_calls = []
        refs_from_macro_expansions = []
        cur_entity_location = None
        for ref_from_kind in ('call', 'expand'):
            refs_from = refs_from_func_calls if ref_from_kind == 'call' else refs_from_macro_expansions
            for raw_ref_from in raw_refs_from[ref_from_kind]:
                ref_from = [
                    # Convert referring source file name to index in source files list.
                    ref_src_files_dict[raw_ref_from[1][0]],
                    # Take line number(s) of entity usage(s) as is. Note that Clade merges references to the same entity
                    # from the same source file together itself, so below this is a list of one or more elements.
                    raw_ref_from[1][1]
                ]

                # Join references to the same entity together. We assume that all references to the same entity
                # are provided by Clade continuously.
                if raw_ref_from[0] == cur_entity_location:
                    refs_from[-1].append(ref_from)
                else:
                    cur_entity_location = raw_ref_from[0]
                    refs_from.append([
                        # Take location of entity definition as is.
                        raw_ref_from[0],
                        ref_from
                    ])

        short_ref_src_files = []
        for ref_src_file in ref_src_files:
            tmp = core.utils.make_relative_path(self.common_dirs, ref_src_file)

            if tmp != ref_src_file:
                if self.common_prefix:
                    short_ref_src_files.append(os.path.join(self.common_prefix, tmp))
                else:
                    # Like in core.vtg.weaver.Weaver#weave.
                    if tmp.startswith('specifications'):
                        short_ref_src_files.append(tmp)
                    else:
                        tmp = os.path.join('generated models', tmp)
                        short_ref_src_files.append(tmp)
            else:
                short_ref_src_files.append(ref_src_file)

        # Add special highlighting for non heuristically known entity references and referenced entities.
        highlight.extra_highlight([['FuncDefRefTo', *r[0]] for r in refs_to_func_defs])

        # There may be several references to declarations of the same function. Add highlights for them just ones.
        cur_func_loc = None
        for r in refs_to_func_decls:
            if r[0] == cur_func_loc:
                continue

            cur_func_loc = r[0]
            highlight.extra_highlight([['FuncDeclRefTo', *r[0]]])

        highlight.extra_highlight([['MacroDefRefTo', *r[0]] for r in refs_to_macro_defs])
        highlight.extra_highlight([['FuncCallRefFrom', *r[0]] for r in refs_from_func_calls])
        highlight.extra_highlight([['MacroExpansionRefFrom', *r[0]] for r in refs_from_macro_expansions])

        cross_ref = {
            'format': self.INDEX_DATA_FORMAT_VERSION,
            'source files': short_ref_src_files,
            'referencesto': refs_to_func_defs + refs_to_macro_defs,
            'referencestodeclarations': refs_to_func_decls,
            'referencesfrom': refs_from_func_calls + refs_from_macro_expansions,
            'highlight': highlight.highlights
        }

        with open(os.path.join(self.new_file_name + '.idx.json'), 'w') as fp:
            core.utils.json_dump(cross_ref, fp, self.conf['keep intermediate files'])
