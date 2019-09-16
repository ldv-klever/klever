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
    $('.parent-popup').popup({inline:true});
    $('.ui.dropdown').dropdown();

    let src_code_content = $("#CoverageSourceCode"),
        cov_attr_table = $('#CoverageAttrTable'),
        data_window = $('#CoverageDataContent');

    let source_processor = new SourceProcessor(
        '#CoverageSourceCode', '#CoverageSourceTitle',
        '#CoverageSourceButtons', '#sources_history',
        '#CoverageDataContent', '#CoverageLegend'
    );
    source_processor.initialize(null, $('#source_url').val());
    source_processor.errors.line_not_found = $('#error__line_not_found').text();

    // Initialize statistics table
    let stat_table = $('#CoverageStatisticsTable').find('table');
    stat_table.find('.tg-expanded').each(function () {
        stat_table.find(`tr[data-tg-parent="${$(this).data('tg-id')}"]`).show();
    });

    stat_table.on('click', '.tg-expander', function (event, with_shift, rec) {
        let tr = $(this).closest('tr'), tr_id = tr.data('tg-id');
        if (tr.hasClass('tg-expanded')) {
            stat_table.find(`tr.tg-expanded[data-tg-parent="${tr_id}"]`)
                .find('i.tg-expander').trigger("click", [false, true]);
            stat_table.find(`tr[data-tg-parent="${tr_id}"]`).hide();
            $(this).removeClass('open');
            tr.removeClass('tg-expanded');
        }
        else {
            stat_table.find(`tr[data-tg-parent="${tr_id}"]`).show();
            $(this).addClass('open');
            tr.addClass('tg-expanded');
            if (event.shiftKey || with_shift) {
                stat_table.find(`tr[data-tg-parent="${tr_id}"]`).find('i.tg-expander')
                    .trigger("click", [event.shiftKey || with_shift, true]);
            }
        }
        if (!rec) update_colors(stat_table);
    });
    stat_table.on('click', '.tree-file-link', function (event) {
        event.preventDefault();
        data_window.empty();
        source_processor.get_source(1, $(this).data('path'));
    });
    update_colors(stat_table);

    // Open directories to first found file
    stat_table.find('tbody').children('tr').each(function () {
        let expander_link = $(this).find('.tg-expander');
        if (expander_link.length) {
            expander_link.click();
            return true;
        }
        return false;
    });

    // Open first found file
    stat_table.find('.tree-file-link:visible').first().click();

    // Report attributes table
    $('#show_cov_attributes').click(function () {
        if (cov_attr_table.is(':visible')) cov_attr_table.hide();
        else cov_attr_table.show();
    });

    // Data statistics modal
    let data_statistics_modal = $('#data_statistics_modal');
    data_statistics_modal.modal();
    data_statistics_modal.find('.item').tab();
    $('#get_data_statistic').click(function () {
        data_statistics_modal.modal('show')
    });

    // Function coverage buttons
    $('#next_cov_btn').click(function () {
        data_window.empty();
        let selected_line = source_processor.selected_line, next_span;
        if (selected_line) {
            next_span = selected_line.parent().parent()
                .nextAll('span').find('.SrcFuncCov[data-value]').filter(function () {
                    return $(this).data('value') > 0
                }).first();
        }
        if (!next_span || !next_span.length) {
            next_span = src_code_content.find('.SrcFuncCov[data-value]').filter(function () {
                return $(this).data('value') > 0
            }).first();
        }
        if (next_span.length) source_processor.select_span(next_span.parent());
    });

    $('#prev_cov_btn').click(function () {
        data_window.empty();
        let selected_line = source_processor.selected_line, prev_span;
        if (selected_line) {
            prev_span = selected_line.parent().parent()
                .prevAll('span').find('.SrcFuncCov[data-value]').filter(function () {
                    return $(this).data('value') > 0
                }).last();
        }
        if (!prev_span || !prev_span.length) {
            prev_span = src_code_content.find('.SrcFuncCov[data-value]').filter(function () {
                return $(this).data('value') > 0
            }).last();
        }
        if (prev_span.length) source_processor.select_span(prev_span.parent());
    });

    $('#next_uncov_btn').click(function () {
        data_window.empty();
        let selected_line = source_processor.selected_line, next_span;
        if (selected_line) {
            next_span = selected_line.parent().parent()
                .nextAll('span').find('.SrcFuncCov[data-value]').filter(function () {
                    return $(this).data('value') === 0
                }).first();
        }
        if (!next_span || !next_span.length) {
            next_span = src_code_content.find('.SrcFuncCov[data-value]').filter(function () {
                return $(this).data('value') === 0
            }).first();
        }
        if (next_span.length) source_processor.select_span(next_span.parent());
    });

    $('#prev_uncov_btn').click(function () {
        data_window.empty();
        let selected_line = source_processor.selected_line, prev_span;
        if (selected_line) {
            prev_span = selected_line.parent().parent()
                .prevAll('span').find('.SrcFuncCov[data-value]').filter(function () {
                    return $(this).data('value') === 0
                }).last();
        }
        if (!prev_span || !prev_span.length) {
            prev_span = src_code_content.find('.SrcFuncCov[data-value]').filter(function () {
                return $(this).data('value') === 0
            }).last();
        }
        if (prev_span.length) source_processor.select_span(prev_span.parent());
    });

    function sortByNumOfCalls(a, b) {
        let n1 = $(a).data('value'), n2 = $(b).data('value');
        return (n1 > n2) ? 1 : (n1 < n2) ? -1 : 0;
    }

    function getElemIndex(selected_line, array) {
        for (let i = 0; i < array.length; i++) {
            if ($(array.get(i)).is(selected_line)) return i;
        }
        return -1;
    }

    $('#next_srt_btn').click(function () {
        data_window.empty();
        let selected_line = source_processor.selected_line, next_span,
            sorted_elements = src_code_content.find('.SrcFuncCov[data-value]').sort(sortByNumOfCalls);

        if (selected_line && sorted_elements.length) {
            let selected_index = getElemIndex(selected_line.prev(), sorted_elements),
                new_index = selected_index + 1;
            if (new_index >= sorted_elements.length) new_index = 0;
            next_span = sorted_elements.get(new_index);
        }
        else if (sorted_elements.length) next_span = sorted_elements.get(0);

        if (next_span) source_processor.select_span($(next_span).parent());
    });

    $('#prev_srt_btn').click(function () {
        data_window.empty();
        let selected_line = source_processor.selected_line, prev_span,
            sorted_elements = src_code_content.find('.SrcFuncCov[data-value]').sort(sortByNumOfCalls);

        if (selected_line && sorted_elements.length) {
            let selected_index = getElemIndex(selected_line.prev(), sorted_elements),
                new_index = selected_index - 1;
            if (new_index < 0) new_index = sorted_elements.length - 1;
            prev_span = sorted_elements.get(new_index);
        }
        else if (sorted_elements.length) prev_span = sorted_elements.get(sorted_elements.length - 1);

        if (prev_span) source_processor.select_span($(prev_span).parent());
    });
});
