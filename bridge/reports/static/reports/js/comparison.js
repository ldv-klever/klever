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

function draw_connections() {
    var cnt = 1;
    function draw_line(b1, b2, column) {
        var s_x = b1.position().left + parseInt(b1.width() / 2), s_y = b1.position().top + b1.height(),
            e_x = b2.position().left + parseInt(b2.width() / 2), e_y = b2.position().top,
            line_w = parseInt(e_x - s_x), line_h = parseInt(e_y - s_y) - 1,
            canvas_id = 'canvas__' + cnt;
        cnt++;
        if (line_w == 0) {
            line_w = 1;
        }
        line_h -= 7;
        column.append($('<canvas>', {id: canvas_id}));
        var c = $('#' + canvas_id);
        c.attr('width', Math.abs(line_w));
        c.attr('height', line_h);
        if (line_w > 0) {
            c.css({
                position: 'absolute',
                top: s_y + 23,
                left: s_x + column.scrollLeft() + 10
            });
        }
        else {
            c.css({
                position: 'absolute',
                top: s_y + 23,
                left: s_x + line_w + column.scrollLeft() + 10
            });
        }

        var ctx = c[0].getContext("2d");
        if (line_w > 0) {
            ctx.moveTo(0, 0);
            ctx.lineTo(line_w, line_h);
        }
        else {
            ctx.moveTo(-line_w, 0);
            ctx.lineTo(0, line_h);
        }

        ctx.stroke();
    }
    $('.block-parent').each(function () {
        var block = $(this).closest('.comparison-block'), column = $(this).closest('.reports-column'),
            parent_id = $(this).val();
        column.find('.block-id').each(function () {
            if ($(this).val() == parent_id) {
                draw_line($(this).closest('.comparison-block'), block, column);
            }
        });
    });
}

function block_hover_on() {
    var column1 = $(this).closest('.reports-column'), column2, block_class = $(this).find('.block_class').val();
    $('.reports-column').each(function () {
        if (!$(this).is(column1)) {
            column2 = $(this);
        }
    });
    if (column2 && column2.find('.block_class[value="' + block_class + '"]').length > 0) {
        $('.block_class[value="' + block_class + '"]').closest('.comparison-block').addClass('block-hover-normal');
    }
    else {
        $('.block_class[value="' + block_class + '"]').closest('.comparison-block').addClass('block-hover-single');
    }
}

function block_hover_off() {
    $('.comparison-block').removeClass('block-hover-single block-hover-normal');
}

function setup_buttons() {
    $('#fast_backward_btn').click(function () {
        var cur_v_input = $('#current_verdict');
        if (cur_v_input.length) {
            get_comparison(cur_v_input.val(), 1);
        }
        else if ($('#attrs_search_value').length) {
            get_comparison_by_attrs($('#attrs_search_value').val(), 1)
        }

    });
    $('#fast_forward_btn').click(function () {
        var cur_v_input = $('#current_verdict');
        if (cur_v_input.length) {
            get_comparison(cur_v_input.val(), $('#total_pages').val());
        }
        else if ($('#attrs_search_value').length) {
            get_comparison_by_attrs($('#attrs_search_value').val(), $('#total_pages').val())
        }
    });
    $('#backward_btn').click(function () {
        var curr_page = parseInt($('#current_page_num').val()),
            cur_v_input = $('#current_verdict');
        if (curr_page > 1) {
            curr_page--;
        }
        if (cur_v_input.length) {
            get_comparison(cur_v_input.val(), curr_page);
        }
        else if ($('#attrs_search_value').length) {
            get_comparison_by_attrs($('#attrs_search_value').val(), curr_page)
        }
    });
    $('#forward_btn').click(function () {
        var curr_page = parseInt($('#current_page_num').val()),
            max_page_num = parseInt($('#total_pages').val()),
            cur_v_input = $('#current_verdict');
        if (curr_page < max_page_num) {
            curr_page++;
        }
        if (cur_v_input.length) {
            get_comparison(cur_v_input.val(), curr_page);
        }
        else if ($('#attrs_search_value').length) {
            get_comparison_by_attrs($('#attrs_search_value').val(), curr_page)
        }
    });
}

function get_comparison(v_id, page_num) {
    var data = {
        verdict: v_id, page_num: page_num,
        hide_components: $('#show_all_components').is(':checked') ? 0 : 1,
        hide_attrs: $('#show_all_attrs').is(':checked') ? 0 : 1
    };
    $.post('/reports/get_compare_jobs_data/' + $('#compare_info').val() + '/', data, function (data) {
        if (data.error) {
            err_notify(data.error);
            $('#compare_data').empty();
        }
        else {
            $('#compare_data').html(data);
            $('.comparison-block').hover(block_hover_on, block_hover_off);
            draw_connections();
            setup_buttons();
        }
    });
}

function get_comparison_by_attrs(attrs, page_num) {
    var data = {
        attrs: attrs, page_num: page_num,
        hide_components: $('#show_all_components').is(':checked') ? 0 : 1,
        hide_attrs: $('#show_all_attrs').is(':checked') ? 0 : 1
    };
    $.post('/reports/get_compare_jobs_data/' + $('#compare_info').val() + '/', data, function (data) {
        if (data.error) {
            err_notify(data.error);
            $('#compare_data').empty();
        }
        else {
            $('#compare_data').html(data);
            $('.comparison-block').hover(block_hover_on, block_hover_off);
            draw_connections();
            setup_buttons();
        }
    });
}

$(document).ready(function () {
    $('.attrs-dropdown').dropdown();
    $('a[id^="compare_cell_"]').click(function (event) {
        event.preventDefault();
        get_comparison($(this).attr('id').replace('compare_cell_', ''), 1);
    });
    $('#show_all_components').parent().checkbox({
        onChange: function () {
            var curr_page = $('#current_page_num'), verdict = $('#current_verdict');
            if (curr_page.length && verdict.length) {
                get_comparison(verdict.val(), curr_page.val());
            }
            else if (curr_page.length && $('#attrs_search_value').length) {
                get_comparison_by_attrs($('#attrs_search_value').val(), curr_page.val())
            }
        }
    });
    $('#show_all_attrs').parent().checkbox({
        onChange: function () {
            var curr_page = $('#current_page_num'), verdict = $('#current_verdict');
            if (curr_page.length && verdict.length) {
                get_comparison(verdict.val(), curr_page.val());
            }
            else if (curr_page.length && $('#attrs_search_value').length) {
                get_comparison_by_attrs($('#attrs_search_value').val(), curr_page.val())
            }
        }
    });
    $('#search_by_attrs').click(function () {
        var attrs = [];
        $('select[id^="attr_value__"]').each(function () { attrs.push($(this).val()) });
        if (attrs) get_comparison_by_attrs(JSON.stringify(attrs), 1);
    });
});