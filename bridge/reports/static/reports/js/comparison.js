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
        if (line_w === 0) line_w = 1;
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
    $('.reports-column').each(function () {
        var curr_column = $(this);
        curr_column.find('.comparison-block').each(function () {
            var current_block = $(this),
                parent_id = current_block.data('parent');
            if (parent_id) {
                var parent_block = curr_column.find('.comparison-block[data-id="' + parent_id + '"]').first();
                if (parent_block.length) draw_line(parent_block, current_block, curr_column);
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

function get_comparison(page) {
    var search_verdict = $('#search_verdict').val() || undefined,
        search_attrs = $('#search_attrs').val() || undefined;
    var data = {
        page: page, verdict: search_verdict, attrs: search_attrs,
        hide_components: $('#show_all_components').is(':checked') ? 0 : 1,
        hide_attrs: $('#show_all_attrs').is(':checked') ? 0 : 1
    };
    $.get('/reports/get_compare_jobs_data/' + $('#compare_info').val() + '/', data, function (data) {
        $('#compare_data').html(data);
        $('.comparison-block').hover(block_hover_on, block_hover_off);
        draw_connections();
        setup_buttons();
    });
}

function setup_buttons() {
    $('#fast_backward_btn').click(function () {
        get_comparison(1);
    });
    $('#fast_forward_btn').click(function () {
        get_comparison($('#total_pages').text());
    });
    $('#backward_btn').click(function () {
        var curr_page = parseInt($('#current_page').val());
        if (curr_page > 1) curr_page--;
        get_comparison(curr_page);
    });
    $('#forward_btn').click(function () {
        var curr_page = parseInt($('#current_page').text()),
            max_page_num = parseInt($('#total_pages').text());
        if (curr_page < max_page_num) curr_page++;
        get_comparison(curr_page);
    });
}

function reload_comparison() {
    get_comparison($('#current_page').text());
}

$(document).ready(function () {
    $('.attrs-dropdown').dropdown();
    $('.compare-cell').click(function (event) {
        event.preventDefault();
        $('#search_verdict').val($(this).data('verdict'));
        $('#search_attrs').val('');
        get_comparison(1);
    });
    $('#show_all_components').parent().checkbox({onChange: reload_comparison});
    $('#show_all_attrs').parent().checkbox({onChange: reload_comparison});
    $('#search_by_attrs').click(function () {
        var attrs = [];
        $('select[id^="attr_value__"]').each(function () { attrs.push($(this).val()) });
        if (attrs.length) return;
        $('#search_verdict').val('');
        $('#search_attrs').val(JSON.stringify(attrs));
        get_comparison(1);
    });
});