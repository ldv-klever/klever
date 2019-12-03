/*
 * Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
 * Ivannikov Institute for System Programming of the Russian Academy of Sciences
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

$(document).ready(function () {
    let source_processor = new SourceProcessor(
        '#CoverageSourceCode', '#CoverageSourceTitle',
        '#sources_history', '#CoverageDataContent',
        '#CoverageLegend'
    );
    source_processor.initialize(null, $('#source_url').val());
    source_processor.errors.line_not_found = $('#error__line_not_found').text();

    let coverage_processor = new CoverageProcessor(
        source_processor, '#CoverageDataContent', '#CoverageStatisticsTable'
    );
    coverage_processor.open_stat_table();
    coverage_processor.open_first_file();
});