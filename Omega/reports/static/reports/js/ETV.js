$(document).ready(function () {
    $('#error_trace_options').popup({
        popup: $('#etv-attributes'),
        position: 'right center',
        hoverable: true,
        lastResort: true,
        delay: {
            show: 100,
            hide: 100
        }
    });
    $('.normal-popup').popup();
    function get_source_code(line, filename) {
        $.ajax({
            url: '/reports/ajax/get_source/',
            type: 'POST',
            data: {
                report_id: $('#report_pk').val(),
                file_name: filename
            },
            success: function (data) {
                var source_code_window = $('#ETV_source_code');
                if (data.error) {
                    $('#ETVSourceTitle').empty();
                    source_code_window.empty();
                    err_notify(data.error);
                }
                else if (data.name && data.content) {
                    $('#ETVSourceTitle').text(data.name);
                    source_code_window.html(data.content);
                    var selected_src_line = $('#ETVSrcL_' + line);
                    if (selected_src_line.length) {
                        source_code_window.scrollTop(source_code_window.scrollTop() + selected_src_line.position().top - source_code_window.height() * 3/10);
                        selected_src_line.parent().addClass('ETVSelectedLine');
                    }
                    else {
                        err_notify($('#error___line_not_found').text());
                    }
                }
            },
            error: function (x) {
                $('#ETV_source_code').html(x.responseText);
            }
        });
    }

    $('.ETV_GlobalExpanderLink').click(function (event) {
        event.preventDefault();
        if ($(this).find('i').first().hasClass('empty')) {
            $(this).find('i').first().removeClass('empty');
            $(this).closest('.ETV_error_trace').find('.global').hide();
        }
        else {
            $(this).find('i').first().addClass('empty');
            $(this).closest('.ETV_error_trace').find('.global').show();
        }
    });

    $('.ETV_HideLink').click(function (event) {
        event.preventDefault();
        var whole_line = $(this).parent().parent(),
            etv_main_parent = $(this).closest('div[id^="etv-trace"]'),
            add_id = etv_main_parent.attr('id').replace('etv-trace', ''),
            expanded = 'mini icon violet caret down',
            collapsed = 'mini icon violet caret right',
            last_selector = etv_main_parent.find('.' + $(this).attr('id').replace(add_id, '')).last(),
            next_line = whole_line.next('span');
        if ($(this).children('i').first().attr('class') == expanded) {
            $(this).children('i').first().attr('class', collapsed);
            whole_line.addClass('func_collapsed');
            while (!next_line.is(last_selector) && !next_line.is(etv_main_parent.find('.ETV_End_of_trace').first())) {
                next_line.hide();
                next_line = next_line.next('span');
            }
            last_selector.hide();
        }
        else {
            $(this).children('i').first().attr('class', expanded);
            whole_line.removeClass('func_collapsed');
            while (!next_line.is(last_selector) && !next_line.is(etv_main_parent.find('.ETV_End_of_trace').first())) {
                next_line.show();
                if (next_line.hasClass('func_collapsed')) {
                    next_line = etv_main_parent.find(
                        '.' + next_line.find('a[class="ETV_HideLink"]').first().attr('id')
                    ).last().next('span').next('span');
                }
                else {
                    next_line = next_line.next('span');
                }

            }
            last_selector.show();
        }
    });

    $('.ETV_La').click(function (event) {
        event.preventDefault();
        $('.ETVSelectedLine').removeClass('ETVSelectedLine');
        get_source_code(parseInt($(this).text()), 'default-file.c');
        var whole_line = $(this).parent().parent();
        whole_line.addClass('ETVSelectedLine');

        var assume_window = $('#ETV_assumes'),
            add_id = $(this).closest('div[id^="etv-trace"]').attr('id').replace('etv-trace', '');
        assume_window.empty();
        whole_line.find('span[class="ETV_CurrentAssumptions"]').each(function () {
            var assume_ids = $(this).text().split(';');
            $.each(assume_ids, function (i, v) {
                var curr_assume = $('#' + v + add_id);
                if (curr_assume.length) {
                    assume_window.append($('<span>', {
                        text: curr_assume.text(),
                        style: 'color: red'
                    })).append($('<br>'));
                }
            });
        });
        whole_line.find('span[class="ETV_Assumptions"]').each(function () {
            var assume_ids = $(this).text().split(';');
            $.each(assume_ids, function (i, v) {
                var curr_assume = $('#' + v + add_id);
                if (curr_assume.length) {
                    assume_window.append($('<span>', {
                        text: curr_assume.text()
                    })).append($('<br>'));
                }
            });
        });
    });
});