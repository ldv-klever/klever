#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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


def get_conf_property(conf, name, expected_type=None):
    """
    Check that configuration properties dictionary contains the given configuration property and return its value.

    :param conf: Dictionary.
    :param name: Configuration property string.
    :param expected_type: Check that given value has an expected type.
    :return: Configuration property value.
    """
    if name in conf:
        if expected_type and not isinstance(conf[name], expected_type):
            raise TypeError("Expect configuration property '{}' to be set with a '{}' value but it has type '{}'".
                            format(name, str(expected_type), str(type(conf[name]))))
        return conf[name]
    else:
        return None


def get_necessary_conf_property(conf, name):
    """
    Return configuration property value and expect it to be set.

    :param conf: Dictionary.
    :param name: Configuration property string.
    :return: Configuration property value.
    """
    check_necessary_conf_property(conf, name, None)
    return conf[name]


def check_or_set_conf_property(conf, name, default_value=None, expected_type=None):
    """
    Check that property is set or set its value with a provided value.

    :param conf: Dictionary.
    :param name: Configuration property string.
    :param default_value: Default value to be set.
    :param expected_type: Check that given value has an expected type.
    :return: None
    """
    if name not in conf:
        conf[name] = default_value
    check_necessary_conf_property(conf, name, expected_type)


def check_necessary_conf_property(conf, name, expected_type=None):
    """
    Check that property is set or set its value with a provided value.

    :param conf: Dictionary.
    :param name: Configuration property string.
    :param expected_type: Check that given value has an expected type.
    :return: True
    """
    if name not in conf:
        raise KeyError("Expect configuration property '{}' to be set properly".format(name))
    elif name in conf and expected_type and not isinstance(conf[name], expected_type):
        raise TypeError("Expect configuration property '{}' to be set with a '{}' value but it has type '{}'".
                        format(name, str(expected_type), str(type(conf[name]))))
    return True


def model_comment(comment_type, text, other=None):
    if other and isinstance(other, dict):
        comment = other
    else:
        comment = dict()

    comment['type'] = comment_type.upper()
    if text:
        comment['comment'] = text

    string = json.dumps(comment)
    return "/* LDV {} */".format(string)
