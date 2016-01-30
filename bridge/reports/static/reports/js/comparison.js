function style_blocks() {
    var cnt = 0;
    $('.block-parent').each(function () {
        var block = $(this).parent(), parent = null, parent_id = $(this).val(),
            block_id = block.find('.block-id').first().val(), column = $(this).closest('.reports-column');
        column.find('.block-id').each(function () {
            if ($(this).val() == parent_id) {
                parent = $(this).parent();
            }
        });
        if (!parent || !block_id.length) {
            return true;
        }
        var s_x = block.offset().left + parseInt(block.width() / 2), s_y = block.offset().top,
            e_x = parent.offset().left + parseInt(block.width() / 2), e_y = parent.offset().top + parent.height(),
            line_w = parseInt(s_x - e_x), line_h = parseInt(s_y - e_y),
            canvas_id = block_id + '___' + parent_id + '__' + cnt;
        cnt++;
        if (line_w == 0) {
            line_w = 1;
        }
        line_h -= 10;
        $('#compare_data').append($('<canvas>', {id: canvas_id}));
        var c = $('#' + canvas_id);
        c.attr('width', Math.abs(line_w));
        c.attr('height', line_h);
        if (line_w > 0) {
            c.css({
                position: 'absolute',
                top: e_y + 11,
                left: e_x
            });
        }
        else {
            c.css({
                position: 'absolute',
                top: e_y + 11,
                left: e_x + line_w
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
    });

    $('.comparison-block').hover(
        function () {
            var column1 = $(this).closest('.reports-column'), column2, block_class = $(this).find('.block_class').val();
            $('.reports-column').each(function () {
                if (!$(this).is(column1)) {
                    column2 = $(this);
                }
            });
            if (column2.find('.block_class[value="' + block_class + '"]').length > 0) {
                $('.block_class[value="' + block_class + '"]').closest('.comparison-block').addClass('block-hover-normal');
            }
            else {
                $('.block_class[value="' + block_class + '"]').closest('.comparison-block').addClass('block-hover-single');
            }
        },
        function () {
            $('.comparison-block').removeClass('block-hover-single block-hover-normal');
        }
    );
}

function setup_buttons() {
    $('#fast_backward_btn').click(function () {
        get_comparison($('#current_verdict').val(), 1);
    });
    $('#fast_forward_btn').click(function () {
        get_comparison($('#current_verdict').val(), $('#total_pages').val());
    });
    $('#backward_btn').click(function () {
        var curr_page = parseInt($('#current_page_num').val());
        if (curr_page > 1) {
            curr_page--;
        }
        get_comparison($('#current_verdict').val(), curr_page);
    });
    $('#forward_btn').click(function () {
        var curr_page = parseInt($('#current_page_num').val()), max_page_num = parseInt($('#total_pages').val());
        if (curr_page < max_page_num) {
            curr_page++;
        }
        get_comparison($('#current_verdict').val(), curr_page);
    });
}

function get_comparison(v_id, page_num) {
    var data = {
        verdict: v_id,
        info_id: $('#compare_info').val(),
        page_num: page_num
    };
    if (!$('#show_all_components').is(':checked')) {
        data['hide_components'] = 1
    }
    if (!$('#show_all_attrs').is(':checked')) {
        data['hide_attrs'] = 1
    }
    $.post(
        '/reports/ajax/get_compare_jobs_data/',
        data,
        function (data) {
            if (data.error) {
                err_notify(data.error);
                $('#compare_data').empty();
            }
            else {
                $('#compare_data').html(data);
                style_blocks();
                setup_buttons();
            }
        }
    );
}

$(document).ready(function () {
    $('a[id^="compare_cell_"]').click(function (event) {
        event.preventDefault();
        get_comparison($(this).attr('id').replace('compare_cell_', ''), 1);
    });
    $('#show_all_components').parent().checkbox({
        onChange: function () {
            var curr_page = $('#current_page_num'), verdict = $('#current_verdict');
            if (curr_page && verdict) {
                get_comparison(verdict.val(), curr_page.val());
            }
        }
    });
    $('#show_all_attrs').parent().checkbox({
        onChange: function () {
            var curr_page = $('#current_page_num'), verdict = $('#current_verdict');
            if (curr_page && verdict) {
                get_comparison(verdict.val(), curr_page.val());
            }
        }
    });
});