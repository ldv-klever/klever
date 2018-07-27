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

from core.vrp.et.parser import ErrorTraceParser
from core.vrp.et.tmpvars import generic_simplifications

from core.vrp.et.envmodel import envmodel_simplifications


def import_error_trace(logger, witness):
    # Parse witness
    po = ErrorTraceParser(logger, witness)
    trace = po.error_trace

    # Parse comments from sources
    trace.parse_model_comments()

    # Remove ugly code
    generic_simplifications(logger, trace)

    # Find violation
    trace.find_violation_path()

    # Make more difficult transformations
    envmodel_simplifications(logger, trace)

    # Do final checks
    trace.final_checks()

    return trace.serialize()


# This is intended for testing purposes, when one has a witness and would like to debug its transformations.
if __name__ == '__main__':
    import json
    import logging
    import sys

    gl_logger = logging.getLogger()
    gl_logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s (%(filename)s:%(lineno)03d) %(levelname)5s> %(message)s', '%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    gl_logger.addHandler(handler)

    et = import_error_trace(gl_logger, 'witness.0.graphml')

    with open('error trace.json', 'w', encoding='utf8') as fp:
        json.dump(et, fp, ensure_ascii=False, sort_keys=True, indent=4)