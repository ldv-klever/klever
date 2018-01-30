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

    var src_code_content = $("#CoverageSRCContent"),
        src_data_content = $('#CoverageDataContent'),
        with_data = $('#with_data').val(),
        cov_stat_table = $('#CoverageTable'),
        data_stat_table = $('#DataStatisticTable'),
        cov_attr_table = $('#CoverageAttrTable');

    function show_src_code(filename) {
        src_code_content.empty();
        $.ajax({
            method: 'post',
            url: '/reports/get-coverage-src/' + $('#cov_arch_id').val() + '/',
            dataType: 'json',
            data: {filename: filename, with_data: with_data},
            success: function(data) {
                if (data.error) {
                    err_notify(data.error);
                    return false;
                }
                $('#selected_file_name').text(filename);
                src_code_content.html(data['content']).scrollTop(0);
                if ($(with_data === '1')) {
                    src_data_content.html(data['data']).find('.item').tab();
                }
                $('#div_for_legend').html(data['legend']);
            }
        });
    }
    function init_stat_tree(table) {
        var elems = table.find('.tg-expanded');
        elems.each(function () {
            var curr_id = $(this).data('tg-id');
            table.find('tr[data-tg-parent="' + curr_id + '"]').show();
        });

        table.on('click', '.tg-expander', function (event, with_shift, rec) {
            var tr = $(this).closest('tr'), tr_id = tr.data('tg-id');
            if (tr.hasClass('tg-expanded')) {
                table.find('tr.tg-expanded[data-tg-parent="' + tr_id + '"]').find('i.tg-expander').trigger("click", [false, true]);
                table.find('tr[data-tg-parent="' + tr_id + '"]').hide();
                $(this).removeClass('open');
                tr.removeClass('tg-expanded');
            }
            else {
                table.find('tr[data-tg-parent="' + tr_id + '"]').show();
                $(this).addClass('open');
                tr.addClass('tg-expanded');
                if (event.shiftKey || with_shift) {
                    table.find('tr[data-tg-parent="' + tr_id + '"]').find('i.tg-expander').trigger("click", [event.shiftKey || with_shift, true]);
                }
            }
            if (!rec) {
                update_colors(table);
            }
        });
        table.on('click', '.tree-file-link', function (event) {
            event.preventDefault();
            show_src_code($(this).data('path'));
            $('html, body').stop().animate({ scrollTop: 0 }, "slow");
        });
        cov_stat_table.show();
        update_colors(table);
    }

    init_stat_tree(cov_stat_table.find('table'));

    src_code_content.on('scroll', function () {
        $(this).find('.COVStatic').css('left', $(this).scrollLeft());
    });
    src_code_content.on("click", ".COVLineLink", function(event) {
        event.preventDefault();
        // Clear old selection
        src_code_content.find('.COVLineSelected').removeClass('COVLineSelected');
        var line_container = $(this).closest('.COVLine');

        // If full-weight then show data
        if (with_data === '1') {
            var visible_data = src_data_content.find('div[id^="COVDataLine_"]:visible');
            if (visible_data.length) {
                visible_data.hide();
                visible_data.find('div.segment').empty();
            }

            var line_num = line_container.data('line');
            if (line_num) {
                var new_data = src_data_content.find('#COVDataLine_' + line_num);
                new_data.find('.segment').each(function () {
                    $(this).html($('#' + $(this).data('data-id')).html());
                });
                new_data.find('.menu.item').tab();
                new_data.show();
            }
        }
        line_container.addClass('COVLineSelected');
    });
    src_code_content.on('mouseenter', '.COVLine[data-number]', function () {
        $(this).append($('<span>', {'class': 'CovNumberPopup', text: $(this).data('number')}));
    });
    src_code_content.on('mouseleave', '.COVLine[data-number]', function () {
        $(this).find('.CovNumberPopup').remove();
    });
    src_code_content.on('mouseenter', '.COVIsFC[data-number]', function () {
        $(this).append($('<span>', {'class': 'CovNumberPopup', text: $(this).data('number')}));
    });
    src_code_content.on('mouseleave', '.COVIsFC[data-number]', function () {
        $(this).find('.CovNumberPopup').remove();
    });

    src_code_content.on('mouseenter', '.COVCode[data-number]', function () {
        $(this).siblings('.COVStatic').find('.COVLine').append($('<span>', {'class': 'CovNumberPopup', text: $(this).data('number')}));
    });
    src_code_content.on('mouseleave', '.COVCode[data-number]', function () {
        $(this).siblings('.COVStatic').find('.CovNumberPopup').remove();
    });

    $('#show_cov_attributes').click(function () {
        if (cov_attr_table.is(':visible')) {
            cov_attr_table.hide();
        }
        else {
            cov_stat_table.hide();
            data_stat_table.hide();
            cov_attr_table.show();
        }
    });
    $('#get_coverage_table').click(function () {
        if (cov_stat_table.is(':visible')) {
            cov_stat_table.hide();
        }
        else {
            cov_attr_table.hide();
            data_stat_table.hide();
            cov_stat_table.show();
        }
    });

    if (with_data === '1') {
        data_stat_table.find('.item').tab();
        $('#get_data_statistic').click(function () {
            cov_attr_table.hide();
            cov_stat_table.hide();
            data_stat_table.show();
        });
    }
    $('#identifier_selector').change(function () {
        if (with_data === '1') {
            window.location.href = '/reports/coverage/' + $('#report_id').val() + '?archive=' + $(this).val();
        }
        else {
            window.location.href = '/reports/coverage-light/' + $('#report_id').val() + '?archive=' + $(this).val();
        }
    });

    $('#next_cov_btn').click(function () {
        var selected_line = $('.selected-funcline'), next_span;
        if (selected_line.length) {
            selected_line.removeClass('selected-funcline');
            selected_line.find('.COVLine').removeClass('COVLineSelected');
            next_span = selected_line.nextAll('.func-covered').first();
        }
        if (!next_span || !next_span.length) {
            next_span = src_code_content.children('.func-covered').first();
        }
        if (next_span.length) {
            next_span.addClass('selected-funcline');
            next_span.find('.COVLine').addClass('COVLineSelected');
            src_code_content.scrollTop(src_code_content.scrollTop() + next_span.position().top - src_code_content.height() * 0.3);
        }
    });

    $('#prev_cov_btn').click(function () {
        var selected_line = $('.selected-funcline'), prev_span;
        if (selected_line.length) {
            selected_line.removeClass('selected-funcline');
            selected_line.find('.COVLine').removeClass('COVLineSelected');
            prev_span = selected_line.prevAll('.func-covered').first();
        }
        if (!prev_span || !prev_span.length) {
            prev_span = src_code_content.children('.func-covered').last();
        }
        if (prev_span.length) {
            prev_span.addClass('selected-funcline');
            prev_span.find('.COVLine').addClass('COVLineSelected');
            src_code_content.scrollTop(src_code_content.scrollTop() + prev_span.position().top - src_code_content.height() * 0.3);
        }
    });

    $('#next_uncov_btn').click(function () {
        var selected_line = $('.selected-funcline'), next_span;
        if (selected_line.length) {
            selected_line.removeClass('selected-funcline');
            selected_line.find('.COVLine').removeClass('COVLineSelected');
            next_span = selected_line.nextAll('.func-uncovered').first();
        }
        if (!next_span || !next_span.length) {
            next_span = src_code_content.children('.func-uncovered').first();
        }
        if (next_span.length) {
            next_span.addClass('selected-funcline');
            next_span.find('.COVLine').addClass('COVLineSelected');
            src_code_content.scrollTop(src_code_content.scrollTop() + next_span.position().top - src_code_content.height() * 0.3);
        }
    });

    $('#prev_uncov_btn').click(function () {
        var selected_line = $('.selected-funcline'), prev_span;
        if (selected_line.length) {
            selected_line.removeClass('selected-funcline');
            selected_line.find('.COVLine').removeClass('COVLineSelected');
            prev_span = selected_line.prevAll('.func-uncovered').first();
        }
        if (!prev_span || !prev_span.length) {
            prev_span = src_code_content.children('.func-uncovered').last();
        }
        if (prev_span.length) {
            prev_span.addClass('selected-funcline');
            prev_span.find('.COVLine').addClass('COVLineSelected');
            src_code_content.scrollTop(src_code_content.scrollTop() + prev_span.position().top - src_code_content.height() * 0.3);
        }
    });

    function sortByNumOfCalls(a, b) {
        var n1 = parseInt($(a).find('.COVIsFC').data('number'), 10),
            n2 = parseInt($(b).find('.COVIsFC').data('number'), 10);
        return (n1 < n2) ? -1 : (n1 > n2) ? 1 : 0;
    }
    function getElemIndex(array) {
        for (var i = 0; i < array.length; i++) {
            if ($(array.get(i)).hasClass('selected-funcline')) {
                return i;
            }
        }
        return -1;
    }

    $('#next_srt_btn').click(function () {
        var selected_line = $('.selected-funcline'), next_span;
        var sorted_elements = src_code_content.children('.func-covered').sort(sortByNumOfCalls);

        if (selected_line.length && sorted_elements.length) {
            var selected_index = getElemIndex(sorted_elements);
            selected_line.removeClass('selected-funcline');
            selected_line.find('.COVLine').removeClass('COVLineSelected');

            if (sorted_elements.length == selected_index + 1) {
                next_span = sorted_elements.get(0);
            }
            else {
                next_span = sorted_elements.get(selected_index + 1);
            }
        }
        else if (sorted_elements.length) {
            next_span = sorted_elements.get(0);
        }
        if (next_span) {
            next_span = $(next_span);
            next_span.addClass('selected-funcline');
            next_span.find('.COVLine').addClass('COVLineSelected');
            src_code_content.scrollTop(src_code_content.scrollTop() + next_span.position().top - src_code_content.height() * 0.3);
        }
    });

    $('#prev_srt_btn').click(function () {
        var selected_line = $('.selected-funcline'), prev_span;
        var sorted_elements = src_code_content.children('.func-covered').sort(sortByNumOfCalls);

        if (selected_line.length && sorted_elements.length) {
            var selected_index = getElemIndex(sorted_elements);
            selected_line.removeClass('selected-funcline');
            selected_line.find('.COVLine').removeClass('COVLineSelected');

            if (selected_index == 0) {
                prev_span = sorted_elements.get(sorted_elements.length - 1);
            }
            else {
                prev_span = sorted_elements.get(selected_index - 1);
            }
        }
        else if (sorted_elements.length) {
            prev_span = sorted_elements.get(sorted_elements.length - 1);
        }
        if (prev_span) {
            prev_span = $(prev_span);
            prev_span.addClass('selected-funcline');
            prev_span.find('.COVLine').addClass('COVLineSelected');
            src_code_content.scrollTop(src_code_content.scrollTop() + prev_span.position().top - src_code_content.height() * 0.3);
        }
    });
});
