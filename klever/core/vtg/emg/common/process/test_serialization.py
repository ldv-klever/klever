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
import json
import pytest
import logging

from klever.core.vtg.emg.common.process.model_for_testing import raw_model_preset, model_preset, source_preset
from klever.core.vtg.emg.common.process import ProcessCollection
from klever.core.vtg.emg.common.process.serialization import CollectionDecoder, CollectionEncoder


@pytest.fixture
def source():
    return source_preset()


@pytest.fixture
def raw_model():
    return raw_model_preset()


@pytest.fixture()
def model(source, raw_model):
    return model_preset()


def test_import_model(raw_model, model):
    raw2 = json.loads(json.dumps(model, cls=CollectionEncoder))
    _compare_models(raw_model, raw2)


def test_imported_names(raw_model, model):
    assert model.name == raw_model['name']
    assert 'entry' == model.entry.name

    for name in raw_model['functions models']:
        assert name in model.models, 'There are models: {}'.format(', '.join(sorted(model.models.keys())))

    for name in raw_model['environment processes']:
        assert name in model.environment, 'There are models: {}'.format(', '.join(sorted(model.environment.keys())))


def test_export_model(source, model):
    raw1 = json.dumps(model, cls=CollectionEncoder)
    new_model = CollectionDecoder(logging, dict()).parse_event_specification(source, json.loads(raw1),
                                                                             ProcessCollection())
    raw2 = json.dumps(new_model, cls=CollectionEncoder)

    raw1 = json.loads(raw1)
    raw2 = json.loads(raw2)
    _compare_models(raw1, raw2)


def test_requirements_field(source, raw_model):
    test_raw_model = copy.deepcopy(raw_model)
    assert 'c1/p1' in test_raw_model['environment processes']['c1/p2']['actions']['register_c1p2']['require']['processes']

    # Incorrect process
    test_raw_model['environment processes']['c1/p2']['actions']['register_c1p2']['require']['processes']['c5/p4'] =\
        dict()
    with pytest.raises(ValueError):
        CollectionDecoder(logging, dict()).parse_event_specification(source, json.loads(json.dumps(test_raw_model)),
                                                                     ProcessCollection())

    # Missing action
    test_raw_model = copy.deepcopy(raw_model)
    test_raw_model['environment processes']['c1/p2']['actions']['register_c1p2']['require']['actions'] = \
        {'c1/p1': ['goaway']}
    with pytest.raises(ValueError):
        CollectionDecoder(logging, dict()).parse_event_specification(source, json.loads(json.dumps(test_raw_model)),
                                                                     ProcessCollection())


def test_savepoint_uniqueness(source, raw_model):
    raw_model = copy.deepcopy(raw_model)

    # Add two savepoints with the same name
    assert 'p2s1' in raw_model['environment processes']['c1/p2']['actions']['register_c1p2']['savepoints']
    new_sp = dict(raw_model["environment processes"]['c1/p2']['actions']['register_c1p2']['savepoints']['p2s1'])
    raw_model['environment processes']['c2/p1']['actions']['register_c2p1']['savepoints']['p2s1'] = new_sp

    # Expect an error
    with pytest.raises(ValueError):
        CollectionDecoder(logging, dict()).parse_event_specification(source, json.loads(json.dumps(raw_model)),
                                                                     ProcessCollection())


def test_failures(source, raw_model):
    # Check for unused labels
    raw_model1 = copy.deepcopy(raw_model)
    raw_model1['environment processes']['c1/p2']['labels']['unused_label'] = {'declaration': 'int x'}
    with pytest.raises(RuntimeError):
        CollectionDecoder(logging, dict()).parse_event_specification(source, json.loads(json.dumps(raw_model1)),
                                                                     ProcessCollection())
    # Check for unused actions
    raw_model2 = copy.deepcopy(raw_model)
    raw_model2['environment processes']['c1/p2']['actions']['new'] = {'comment': 'Test', "statements": []}
    with pytest.raises(RuntimeError):
        CollectionDecoder(logging, dict()).parse_event_specification(source, json.loads(json.dumps(raw_model2)),
                                                                     ProcessCollection())

    # todo: Implement unused recursive subprocess
    raw_model3 = copy.deepcopy(raw_model)
    raw_model3['environment processes']['c1/p2']['actions']['test'] = {
        'comment': 'Test', "process": "(<read> | <read>).{test}"
    }
    with pytest.raises(RuntimeError):
        CollectionDecoder(logging, dict()).parse_event_specification(source, json.loads(json.dumps(raw_model3)),
                                                                     ProcessCollection())

    raw_model4 = copy.deepcopy(raw_model)
    raw_model4['environment processes']['c1/p1']['process'] = '(!register_c1p1).{activate[%unknown_label%]}'
    with pytest.raises(RuntimeError):
        CollectionDecoder(logging, dict()).parse_event_specification(source, json.loads(json.dumps(raw_model4)),
                                                                     ProcessCollection())


def _compare_models(raw1, raw2):
    _compare_process(raw1["main process"], raw2["main process"])
    for attr in ("functions models", "environment processes"):
        collection1 = raw1.get(attr, dict())
        collection2 = raw2.get(attr, dict())
        assert len(collection1) == len(collection2), attr
        for key in collection1:
            assert key in collection2, key
            _compare_process(collection1[key], collection2[key])


def _compare_process(one, two):
    for item in ('comment', 'headers', 'declarations', 'definitions', 'source files'):
        assert str(one.get(item)) == str(two.get(item))

    assert len(one['labels']) == len(two['labels'])
    for label in one['labels']:
        for attr in ('value', 'declaration'):
            assert one['labels'][label].get(attr) == one['labels'][label].get(attr), f"{label}, {attr}"

    _compare_actions_collections(one['actions'], two['actions'])


def _compare_actions_collections(one, two):
    assert len(one) == len(two)
    for action in one:
        _compare_actions(one[action], two[action])
        _compare_savepoints(one[action], two[action])


def _compare_actions(one, two):
    # todo: we do not test attribute 'trace relevant' as it is unnecessary
    for attr in ('comment', 'statements', 'condition', 'parameters',
                 'peers', 'pre-call', 'post-call', 'requirements'):
        assert str(one.get(attr)) == str(two.get(attr)), f"{attr} {str(one)} {str(two)}"

    if 'process' in one:
        assert 'process' in two

    if 'require' in one:
        _compare_requirements(one.get('require'), two.get('require'))


def _compare_savepoints(desc1, desc2):
    if 'savepoints' in desc1:
        assert set(desc1['savepoints'].keys()) == set(desc2['savepoints'].keys())

        for name in desc1['savepoints']:
            assert desc1['savepoints'][name].get('comment') == desc2['savepoints'][name].get('comment')

            for i, line1 in enumerate(desc1['savepoints'][name]['statements']):
                line2 = desc2['savepoints'][name]['statements'][i]
                assert line1 == line2, f"Line '{line1}' does not match '{line2}' at position {i} of savepoint {name}"

            if "require" in desc1['savepoints'][name]:
                _compare_requirements(desc1['savepoints'][name].get('require'),
                                      desc2['savepoints'][name].get('require'))


def _compare_requirements(desc1, desc2):
    assert set(desc1.get('processes', dict()).keys()) == set(desc1.get('processes', dict()).keys())
    assert set(desc1.get('actions', dict()).keys()) == set(desc1.get('actions', dict()).keys())

    for name, flag in desc1.get('processes', dict()).items():
        assert desc2.get('processes', dict())[name] == flag

    for name, actions in desc1.get('actions', dict()).items():
        assert set(desc2.get('actions', dict())[name]) == set(actions)


def test_compare_peers(model):
    def _check_peers(p1, p2, actions):
        assert str(p1) in p2.peers, 'Peers are {}'.format(', ', p2.peers.keys())
        assert str(p2) in p1.peers, 'Peers are {}'.format(', ', p1.peers.keys())
        for action in actions:
            assert action in p1.peers[str(p2)], 'Peer actions are: {}'.format(', '.join(sorted(p1.peers[str(p2)])))
            assert action in p2.peers[str(p1)], 'Peer actions are: {}'.format(', '.join(sorted(p2.peers[str(p1)])))
        assert len(actions) == len(p1.peers[str(p2)]), 'Peers are {}'.format(', '.join(sorted(p2.peers[str(p1)])))
        assert len(actions) == len(p2.peers[str(p1)]), 'Peers are {}'.format(', '.join(sorted(p1.peers[str(p2)])))

        peers1 = model.peers(p1, list(map(str, actions)), [str(p2)])
        assert len(peers1) == len(actions), 'Peer actions are: {}, but got: {}'.\
                                            format(', '.join(sorted(p1.peers[str(p2)])), ', '.join(map(str, peers1)))
        peers2 = model.peers(p2, list(map(str, actions)), [str(p1)])
        assert len(peers2) == len(actions), 'Peer actions are: {}, but got: {}'. \
                                            format(', '.join(sorted(p2.peers[str(p1)])), ', '.join(map(str, peers2)))
            
    def expect_peers(p1, length):
        assert len(p1.peers) == length, 'Peers are {}'.format(', ', p1.peers.keys())
    
    model.establish_peers()
    
    # register_c1, deregister_c1
    _check_peers(model.models['register_c1'], model.environment['c1/p1'], {'register_c1p1'})
    _check_peers(model.models['deregister_c1'], model.environment['c1/p1'], {'deregister_c1p1'})
    expect_peers(model.models['register_c1'], 1)
    expect_peers(model.models['deregister_c1'], 1)
    
    # register_c2, deregister_c2
    _check_peers(model.models['register_c2'], model.environment['c2/p1'], {'register_c2p1'})
    _check_peers(model.models['deregister_c2'], model.environment['c2/p1'], {'deregister_c2p1'})
    expect_peers(model.models['register_c2'], 1)
    expect_peers(model.models['deregister_c2'], 1)
    
    # c1/p1
    _check_peers(model.environment['c1/p1'], model.environment['c1/p2'], {'register_c1p2', 'deregister_c1p2'})
    expect_peers(model.environment['c1/p1'], 3)
    
    # c1/p2
    expect_peers(model.environment['c1/p2'], 1)
    
    # c2/p2
    expect_peers(model.environment['c1/p1'], 3)
    
    # main
    expect_peers(model.entry, 0)
