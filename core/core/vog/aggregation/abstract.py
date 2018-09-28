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

import re
import os
import ujson
import graphviz


class Abstract:

    DESC_FILE = 'agregations description.json'

    def __init__(self, logger, conf, divider):
        self.logger = logger
        self.conf = conf
        self.divider = divider
        self._aggregations = set()

        self._max_size = self.conf['Aggregation strategy'].get('maximum verification object size')
        self.dynamic_excluded_clean = list()

    @property
    def aggregations(self):
        if not self._aggregations:
            self._aggregations = set(self._aggregate())
        return self._aggregations

    @property
    def attributes(self):
        data = dict()
        for a in self.aggregations:
            data[a.name] = {f.name: list(f.in_files) for f in a.fragments}

        with open(self.DESC_FILE, 'w', encoding='utf8') as fp:
            ujson.dump(data, fp, sort_keys=True, indent=4, ensure_ascii=False,
                       escape_forward_slashes=False)

        return [{
            'name': 'Aggregation strategy',
            'value': [{'name': 'name', 'value': self.conf['Aggregation strategy']['name'], 'data': self.DESC_FILE}]
        }], [self.DESC_FILE]

    def generate_verification_objects(self):
        for aggregation in self.aggregations:
            if not self._max_size or aggregation.size <= self._max_size:
                if self.conf['Aggregation strategy'].get('draw aggregations'):
                    self.draw_aggregation(aggregation)
                yield self.__describe_verification_object(aggregation)
            else:
                self.logger.debug('verification object {!r} is rejected since it exceeds maximum size {}'.
                                  format(aggregation.name, aggregation.size()))

    def _aggregate(self):
        raise NotImplementedError

    def _belong(self, fragment, target):
        if re.search(r'\.o$', target):
            # This is an object file
            return fragment.name == target
        elif re.search(r'\.c$', target):
            # This is a C file
            return target in fragment.in_files
        else:
            # This is a dir
            return os.path.dirname(target) == os.path.dirname(fragment.name)

    def _check_filters(self, fragment):
        return True

    def _add_dependencies(self, aggregation, depth=None, maxfrags=None):
        layer = {aggregation.root}
        while layer and (depth is None or depth > 0) and (maxfrags is None or maxfrags > 0):
            new_layer = set()
            for fragment in layer:
                aggregation.fragments.add(fragment)
                if maxfrags:
                    maxfrags -= 1
                if maxfrags is not None and maxfrags == 0:
                    break

                for dep in fragment.successors:
                    if dep not in aggregation.fragments and dep not in new_layer and dep not in layer and \
                            self._check_filters(dep):
                        new_layer.add(dep)

            layer = new_layer
            if depth is not None:
                depth -= 1

    def __describe_verification_object(self, aggregation):
        self.logger.info('Generate verification object description for aggregation {!r}'.format(aggregation.name))
        vo_desc = dict()
        vo_desc['id'] = aggregation.name
        vo_desc['grps'] = list()
        vo_desc['deps'] = dict()
        for frag in aggregation.fragments:
            vo_desc['grps'].append({'id': frag.name, 'CCs': frag.ccs})
            vo_desc['deps'][frag.name] = [succ.name for succ in frag.successors if succ in aggregation.fragments]
        self.logger.debug('verification object dependencies are {}'.format(vo_desc['deps']))

        vo_desc_file = vo_desc['id'] + '.json'
        if os.path.isfile(vo_desc_file):
            raise FileExistsError('verification object description file {!r} already exists'.format(vo_desc_file))
        self.logger.debug('Dump verification object description {!r} to file {!r}'.format(vo_desc['id'], vo_desc_file))
        dir_path = os.path.dirname(vo_desc_file).encode('utf8')
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # Add dir to exlcuded from cleaning by lkvog
        root_dir_id = vo_desc_file.split('/')[0]
        if root_dir_id not in self.dynamic_excluded_clean:
            self.logger.debug("Do not clean dir {!r} on component termination".format(root_dir_id))
            self.dynamic_excluded_clean.append(root_dir_id)

        with open(vo_desc_file, 'w', encoding='utf8') as fp:
            ujson.dump(vo_desc, fp, sort_keys=True, indent=4, ensure_ascii=False, escape_forward_slashes=False)
        return vo_desc_file

    def draw_aggregation(self, aggregation):
        g = graphviz.Digraph(graph_attr={'rankdir': 'LR'}, node_attr={'shape': 'rectangle'})
        for fragment in aggregation.fragments:
            g.node(fragment.name, "{}".format(fragment.name) + (' (target)' if fragment.target else ''))

        for fragment in aggregation.fragments:
            for suc in fragment.successors:
                if suc in aggregation.fragments:
                    g.edge(fragment.name, suc.name)
        if not os.path.exists('aggregations'):
            os.makedirs('aggregations')
        g.render(os.path.join('aggregations', aggregation.name))
