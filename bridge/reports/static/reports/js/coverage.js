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

function CoverageProcessor(source_processor, data_window, stat_table_selector, on_btn_click) {
    this.source_processor = source_processor;
    this.source_container = source_processor.container;
    this.data_window = $(data_window);
    this.stat_table = $(stat_table_selector).find('table').first();
    this.on_click_callback = on_btn_click;
    this.initialize_statistics_table();
    this.initialize_actions();
    return this;
}

CoverageProcessor.prototype.initialize_statistics_table = function() {
    let instance = this;

    instance.stat_table.on('click', '.tg-expander', function (event, with_shift, rec) {
        let tr = $(this).closest('tr'), tr_id = tr.data('tg-id');
        if (tr.hasClass('tg-expanded')) {
            instance.stat_table.find(`tr.tg-expanded[data-tg-parent="${tr_id}"]`)
                .find('i.tg-expander').trigger("click", [false, true]);
            instance.stat_table.find(`tr[data-tg-parent="${tr_id}"]`).hide();
            $(this).removeClass('open');
            tr.removeClass('tg-expanded');
        }
        else {
            instance.stat_table.find(`tr[data-tg-parent="${tr_id}"]`).show();
            $(this).addClass('open');
            tr.addClass('tg-expanded');
            if (event.shiftKey || with_shift) {
                instance.stat_table.find(`tr[data-tg-parent="${tr_id}"]`).find('i.tg-expander')
                    .trigger("click", [event.shiftKey || with_shift, true]);
            }
        }
        if (!rec) update_colors(instance.stat_table);
    });
    instance.stat_table.on('click', '.tree-file-link', function (event) {
        event.preventDefault();
        instance.data_window.empty();
        if (instance.on_click_callback) instance.on_click_callback();
        instance.source_processor.get_source(1, $(this).data('path'));
    });
    update_colors(instance.stat_table);
};

CoverageProcessor.prototype.open_stat_table = function() {
    // Open directories to first found file
    this.stat_table.find('tbody').children('tr').each(function () {
        let expander_link = $(this).find('.tg-expander');
        if (expander_link.length) {
            expander_link.click();
            return true;
        }
        return false;
    });
};

CoverageProcessor.prototype.open_first_file = function() {
    // Open file from url or first found file in coverage table
    let file_name = getUrlParameter('source'), file_line = getUrlParameter('sourceline');
    if (file_name) {
        this.source_processor.get_source(file_line, file_name, false);
        history.replaceState([file_name, file_line], null, window.location.href);
    }
    else this.stat_table.find('.tree-file-link:visible').first().click();
};

CoverageProcessor.prototype.initialize_actions = function() {
    let instance = this;

    function sortByNumOfCalls(a, b) {
        let n1 = $(a).data('value'), n2 = $(b).data('value');
        return (n1 > n2) ? 1 : (n1 < n2) ? -1 : 0;
    }

    function filterCovered() {
        return $(this).data('value') > 0
    }

    function filterUncovered() {
        return $(this).data('value') === 0
    }

    function getElemIndex(selected_line, array) {
        for (let i = 0; i < array.length; i++) {
            if ($(array.get(i)).is(selected_line)) return i;
        }
        return -1;
    }

    // Function coverage buttons
    $('#next_cov_btn').click(function () {
        instance.data_window.empty();
        if (instance.on_click_callback) instance.on_click_callback();
        let selected_line = instance.source_processor.selected_line, next_span;
        if (selected_line) {
            next_span = selected_line.parent().parent()
                .nextAll('span').find('.SrcFuncCov[data-value]').filter(filterCovered).first();
        }
        if (!next_span || !next_span.length) {
            next_span = instance.source_container.find('.SrcFuncCov[data-value]').filter(filterCovered).first();
        }
        if (next_span.length) instance.source_processor.select_span(next_span.parent());
    });

    $('#prev_cov_btn').click(function () {
        instance.data_window.empty();
        if (instance.on_click_callback) instance.on_click_callback();
        let selected_line = instance.source_processor.selected_line, prev_span;
        if (selected_line) {
            prev_span = selected_line.parent().parent()
                .prevAll('span').find('.SrcFuncCov[data-value]').filter(filterCovered).last();
        }
        if (!prev_span || !prev_span.length) {
            prev_span = instance.source_container.find('.SrcFuncCov[data-value]').filter(filterCovered).last();
        }
        if (prev_span.length) instance.source_processor.select_span(prev_span.parent());
    });

    $('#next_uncov_btn').click(function () {
        instance.data_window.empty();
        if (instance.on_click_callback) instance.on_click_callback();
        let selected_line = instance.source_processor.selected_line, next_span;
        if (selected_line) {
            next_span = selected_line.parent().parent().nextAll('span')
                .find('.SrcFuncCov[data-value]').filter(filterUncovered).first();
        }
        if (!next_span || !next_span.length) {
            next_span = instance.source_container.find('.SrcFuncCov[data-value]').filter(filterUncovered).first();
        }
        if (next_span.length) instance.source_processor.select_span(next_span.parent());
    });

    $('#prev_uncov_btn').click(function () {
        instance.data_window.empty();
        if (instance.on_click_callback) instance.on_click_callback();
        let selected_line = instance.source_processor.selected_line, prev_span;
        if (selected_line) {
            prev_span = selected_line.parent().parent()
                .prevAll('span').find('.SrcFuncCov[data-value]').filter(filterUncovered).last();
        }
        if (!prev_span || !prev_span.length) {
            prev_span = instance.source_container.find('.SrcFuncCov[data-value]').filter(filterUncovered).last();
        }
        if (prev_span.length) instance.source_processor.select_span(prev_span.parent());
    });

    $('#next_srt_btn').click(function () {
        instance.data_window.empty();
        if (instance.on_click_callback) instance.on_click_callback();
        let selected_line = instance.source_processor.selected_line, next_span,
            sorted_elements = instance.source_container.find('.SrcFuncCov[data-value]')
                .filter(filterCovered).sort(sortByNumOfCalls);

        if (selected_line && sorted_elements.length) {
            let selected_index = getElemIndex(selected_line.prev(), sorted_elements),
                new_index = selected_index + 1;
            if (new_index >= sorted_elements.length) new_index = 0;
            next_span = sorted_elements.get(new_index);
        }
        else if (sorted_elements.length) next_span = sorted_elements.get(0);

        if (next_span) instance.source_processor.select_span($(next_span).parent());
    });

    $('#prev_srt_btn').click(function () {
        instance.data_window.empty();
        if (instance.on_click_callback) instance.on_click_callback();
        let selected_line = instance.source_processor.selected_line, prev_span,
            sorted_elements = instance.source_container.find('.SrcFuncCov[data-value]')
                .filter(filterCovered).sort(sortByNumOfCalls);

        if (selected_line && sorted_elements.length) {
            let selected_index = getElemIndex(selected_line.prev(), sorted_elements),
                new_index = selected_index - 1;
            if (new_index < 0) new_index = sorted_elements.length - 1;
            prev_span = sorted_elements.get(new_index);
        }
        else if (sorted_elements.length) prev_span = sorted_elements.get(sorted_elements.length - 1);

        if (prev_span) instance.source_processor.select_span($(prev_span).parent());
    });
};
