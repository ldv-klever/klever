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

import json
import sortedcontainers


def get_or_die(conf, name, expected_type=None):
    """
    Return configuration property value and expect it to be set.

    :param conf: Dictionary.
    :param name: Configuration property string.
    :param expected_type: Type object.
    :return: Configuration property value.
    """
    if name not in conf or (expected_type and not isinstance(conf.get(name), expected_type)):
        raise KeyError("EMG requires configuration property {!r} to be set as {!r}".
                       format(name, type(expected_type).__name__))
    return conf[name]


def model_comment(comment_type, text=None, other=None):
    """
    Print model comment in the form accepted by the Klever error trace parser from VRP. This simple comment contains
    short json to parse.

    For example:
    /* EMG_ACTION {"action": "REGISTER", "type": "DISPATCH_BEGIN", "comment": "Register TTY callbacks."} */

    :param comment_type: Comment type string.
    :param text: Sentence string with a comment itself.
    :param other: An existing dictionary to which the comment and type should be added
    :return: Final comment string (look at the example above).
    """
    if other and isinstance(other, dict):
        comment = other
    else:
        comment = {}
    comment = sortedcontainers.SortedDict(comment)

    comment['type'] = comment_type.upper()
    if text:
        comment['comment'] = text

    string = json.dumps(comment)
    return "/* EMG_ACTION {} */".format(string)


def id_generator(start_from=0, cast=str):
    """
    Function-generator to generate numerical identifiers from 1 or zero.

    :return: Infinite sequence of identifiers.
    """
    while True:
        yield cast(start_from)
        start_from += 1
