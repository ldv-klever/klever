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
    $('.normal-popup').popup({position: 'bottom left'});
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
                    var title_place = $('#ETVSourceTitle');
                    title_place.text(data.name);
                    $('#ETVSourceTitleFull').text(data['fullname']);
                    title_place.popup();
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
                if (event.shiftKey) {
                    if (!next_line.hasClass('func_collapsed') && next_line.find('a[class="ETV_HideLink"]').length > 0) {
                        next_line.addClass('func_collapsed');
                        next_line.find('i[class="' + expanded + '"]').attr('class', collapsed);
                    }
                }
                next_line = next_line.next('span');
            }
            last_selector.hide();
        }
        else {
            $(this).children('i').first().attr('class', expanded);
            whole_line.removeClass('func_collapsed');
            while (!next_line.is(last_selector) && !next_line.is(etv_main_parent.find('.ETV_End_of_trace').first())) {
                if (!(next_line.hasClass('commented') && (next_line.hasClass('func_collapsed') || next_line.find('a[class="ETV_HideLink"]').length == 0))) {
                    next_line.show();
                }
                if (next_line.hasClass('func_collapsed')) {
                    if (event.shiftKey) {
                        next_line.show();
                        next_line.removeClass('func_collapsed');
                        next_line.find('i[class="' + collapsed + '"]').attr('class', expanded);
                        next_line = next_line.next('span');
                    }
                    else {
                        next_line = etv_main_parent.find(
                            '.' + next_line.find('a[class="ETV_HideLink"]').first().attr('id')
                        ).last().next('span');
                    }
                }
                else {
                    if (event.shiftKey) {
                        next_line.show();
                    }
                    next_line = next_line.next('span');
                }

            }
            last_selector.show();
        }
    });

    $('.ETV_La').click(function (event) {
        event.preventDefault();
        $('.ETVSelectedLine').removeClass('ETVSelectedLine');
        if ($(this).next('span.ETV_File').length) {
            get_source_code(parseInt($(this).text()), $(this).next('span.ETV_File').text());
        }
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
    $('.ETV_ShowCommentCode').click(function () {
        var next_code = $(this).parent().next('span');
        if (next_code.length > 0) {
            if (next_code.is(':hidden')) {
                next_code.show();
                if (next_code.find('.ETV_HideLink').find('i').hasClass('right')) {
                    next_code.find('.ETV_HideLink').click();
                }
            }
            else {
                if (next_code.find('.ETV_HideLink').find('i').hasClass('down')) {
                    next_code.find('.ETV_HideLink').click();
                }
                next_code.hide();
            }
        }
    });

    function select_next_line() {
        var selected_line = $('div[id^="etv-trace"]').find('span.ETVSelectedLine').first();
        if (selected_line.length) {
            var next_line = selected_line.next(),
                next_line_link;
            while (next_line.length) {
                if (next_line.find('a.ETV_La').length && next_line.is(':visible')) {
                    next_line_link = next_line.find('a.ETV_La');
                    if (next_line_link.length) {
                        next_line_link.click();
                        return true;
                    }
                }
                next_line = next_line.next()
            }
        }
        return false;
    }
    function select_prev_line() {
        var selected_line = $('div[id^="etv-trace"]').find('span.ETVSelectedLine').first();
        if (selected_line.length) {
            var prev_line = selected_line.prev(),
                prev_line_link;
            while (prev_line.length) {
                if (prev_line.find('a.ETV_La').length && prev_line.is(':visible')) {
                    prev_line_link = prev_line.find('a.ETV_La');
                    if (prev_line_link.length) {
                        prev_line_link.click();
                        return true;
                    }
                }
                prev_line = prev_line.prev()
            }
        }
        return false;
    }
    $('#etv_next_step').click(select_next_line);
    $('#etv_prev_step').click(select_prev_line);

    var interval;
    function play_etv_forward() {
        var selected_line = $('div[id^="etv-trace"]').find('span.ETVSelectedLine').first();
        if (!selected_line.length) {
            err_notify($('#error___no_selected_line').text());
            clearInterval(interval);
            return false;
        }
        if ($.active > 0) {
            return false;
        }
        var etv_window = selected_line.closest('.ETV_error_trace');
        etv_window.scrollTop(etv_window.scrollTop() + selected_line.position().top - etv_window.height() * 3/10);
        if (!select_next_line()) {
            clearInterval(interval);
            success_notify($('#play_finished').text());
            return false;
        }
        return false;
    }
    function play_etv_backward() {
        var selected_line = $('div[id^="etv-trace"]').find('span.ETVSelectedLine').first();
        if (!selected_line.length) {
            err_notify($('#error___no_selected_line').text());
            clearInterval(interval);
            return false;
        }
        if ($.active > 0) {
            return false;
        }
        var etv_window = selected_line.closest('.ETV_error_trace');
        etv_window.scrollTop(etv_window.scrollTop() + selected_line.position().top - etv_window.height() * 7/10);
        if (!select_prev_line()) {
            clearInterval(interval);
            success_notify($('#play_finished').text());
            return false;
        }
        return false;
    }

    $('#etv_play_forward').click(function () {
        clearInterval(interval);
        var speed = parseInt($('#select_speed').val());
        interval = setInterval(play_etv_forward, speed * 1000);
    });
    $('#etv_play_backward').click(function () {
        clearInterval(interval);
        var speed = parseInt($('#select_speed').val());
        interval = setInterval(play_etv_backward, speed * 1000);
    });
    $('#etv_pause_play').click(function () {
        clearInterval(interval);
    });
});