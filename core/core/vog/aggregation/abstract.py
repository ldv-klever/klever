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
import graphviz
import ujson


class Abstract:

    DESC_FILE = 'agregations description.json'

    def __init__(self, logger, conf, divider):
        self.logger = logger
        self.conf = conf
        self.divider = divider

        self._max_size = self.conf['Aggregation strategy'].get('maximum verification object size')
        self.dynamic_excluded_clean = list()

    @property
    def attributes(self):
        return [{
            'name': 'Aggregation strategy',
            'value': [{'name': 'name', 'value': self.conf['Aggregation strategy']['name']}]
        }], []

    def generate_verification_objects(self):
        for aggregation in self._aggregate():
            if not self._max_size or aggregation.size <= self._max_size:
                if self.conf['Aggregation strategy'].get('draw aggregations'):
                    self.draw_aggregation(aggregation)
                yield self.__describe_verification_object(aggregation)
            else:
                self.logger.debug('verification object {!r} is rejected since it exceeds maximum size {}'.
                                  format(aggregation.name, aggregation.size()))

    def _aggregate(self):
        raise NotImplementedError

    def __describe_verification_object(self, aggregation):
        self.logger.info('Generate verification object description for aggregation {!r}'.format(aggregation.name))
        vo_desc = dict()
        vo_desc['id'] = aggregation.name
        vo_desc['grps'] = list()
        vo_desc['deps'] = dict()
        for frag in aggregation.fragments:
            vo_desc['grps'].append({'id': frag.name, 'CCs': frag.ccs})
            vo_desc['deps'][frag.name] = [pred.name for pred in frag.predecessors if pred in aggregation.fragments]
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

