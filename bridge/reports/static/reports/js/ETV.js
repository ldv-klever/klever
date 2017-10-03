/*
 * Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
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
    var ready_for_next_string = false, etv_window = $('#ETV_error_trace'), etv_attrs = $('#etv-attributes');

    if (etv_attrs.length) {
        $('#error_trace_options').popup({
            popup: etv_attrs,
            position: 'right center',
            hoverable: true,
            lastResort: true,
            delay: {
                show: 100,
                hide: 100
            }
        });
    }
    if (!etv_window.length) {
        return false;
    }

    function get_source_code(line, filename) {

        var source_code_window = $('#ETV_source_code');

        function select_src_string() {
            var selected_src_line = $('#ETVSrcL_' + line);
            if (selected_src_line.length) {
                source_code_window.scrollTop(source_code_window.scrollTop() + selected_src_line.position().top - source_code_window.height() * 3/10);
                selected_src_line.parent().addClass('ETVSelectedLine');
            }
            else {
                err_notify($('#error___line_not_found').text());
            }
        }
        if (filename === $('#ETVSourceTitleFull').text()) {
            select_src_string();
        }
        else {
            ready_for_next_string = false;
            $.ajax({
                url: '/reports/ajax/get_source/',
                type: 'POST',
                data: {
                    report_id: $('#report_pk').val(),
                    file_name: filename
                },
                success: function (data) {
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
                        src_filename_trunc();
                        source_code_window.html(data.content);
                        select_src_string();
                        ready_for_next_string = true;
                    }
                }
            });
        }
    }
    $('#ETVSourceTitle').click(function () {
        src_filename_trunc();
    });

    function open_function(hidelink, shift_pressed, change_state) {
        if (change_state) {
            var func_line = hidelink.parent().parent(), collapse_icon = hidelink.find('i').first();
            collapse_icon.removeClass('right');
            collapse_icon.addClass('down');
            func_line.removeClass('func_collapsed');
            func_line.find('.ETV_FuncName').hide();
            func_line.find('.ETV_FuncCode').show();
        }
        $('.' + hidelink.attr('id')).each(function () {
            var inner_hidelink = $(this).find('.ETV_HideLink');
            if (!($(this).hasClass('commented') && ($(this).hasClass('func_collapsed') || inner_hidelink.length == 0))) {
                $(this).show();
            }
            if (inner_hidelink.length == 1) {
                if ($(this).hasClass('func_collapsed')) {
                    if (shift_pressed) {
                        $(this).show();
                        open_function(inner_hidelink, shift_pressed, shift_pressed);
                    }
                    else if (!$(this).hasClass('commented')) {
                        $(this).show();
                    }
                }
                else {
                    $(this).show();
                    open_function(inner_hidelink, shift_pressed, false);
                }
            }
            else if (!$(this).hasClass('commented')) {
                $(this).show();
            }
        });
    }

    function close_function(hidelink, shift_pressed, change_state) {
        if (change_state) {
            var func_line = hidelink.parent().parent(), collapse_icon = hidelink.find('i').first();
            collapse_icon.removeClass('down');
            collapse_icon.addClass('right');
            func_line.addClass('func_collapsed');
            func_line.find('.ETV_FuncCode').hide();
            func_line.find('.ETV_FuncName').show();
        }
        $('.' + hidelink.attr('id')).each(function () {
            $(this).hide();
            var inner_hidelink = $(this).find('.ETV_HideLink');
            if (inner_hidelink.length == 1) {
                close_function(inner_hidelink, shift_pressed, shift_pressed);
            }
        });
    }

    $('.ETV_GlobalExpanderLink').click(function (event) {
        event.preventDefault();
        var global_icon = $(this).find('i').first();
        if (global_icon.hasClass('unhide')) {
            global_icon.removeClass('unhide').addClass('hide');
            etv_window.find('.global:not(.commented)').show();
        }
        else {
            global_icon.removeClass('hide').addClass('unhide');
            etv_window.find('.global:not([data-type="comment"])').hide();
        }
    });

    $('.ETV_HideLink').click(function (event) {
        event.preventDefault();
        if ($(this).find('i').first().hasClass('right')) {
            open_function($(this), event.shiftKey, true);
        }
        else {
            close_function($(this), event.shiftKey, true);
        }
    });
    $('.ETV_DownHideLink').click(function () {
        $('#' + $(this).parent().parent().attr('class')).click();
    });

    $('.ETV_La').click(function (event) {
        event.preventDefault();
        $('.ETVSelectedLine').removeClass('ETVSelectedLine');
        $('.ETV_LN_Note_Selected').removeClass('ETV_LN_Note_Selected');
        $('.ETV_LN_Warning_Selected').removeClass('ETV_LN_Warning_Selected');
        if ($(this).next('span.ETV_File').length) {
            get_source_code(parseInt($(this).text()), $(this).next('span.ETV_File').text());
        }
        var whole_line = $(this).parent().parent();
        whole_line.addClass('ETVSelectedLine');

        var assume_window = $('#ETV_assumes');
        if (assume_window.length) {
            assume_window.empty();
            whole_line.find('span[class="ETV_CurrentAssumptions"]').each(function () {
                var assume_ids = $(this).text().split(';');
                $.each(assume_ids, function (i, v) {
                    var curr_assume = $('#' + v);
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
                    var curr_assume = $('#' + v);
                    if (curr_assume.length) {
                        assume_window.append($('<span>', {
                            text: curr_assume.text()
                        })).append($('<br>'));
                    }
                });
            });
        }
    });
    $('.ETV_ShowCommentCode').click(function () {
        var next_code = $(this).parent().parent().next('span');
        if (next_code.length > 0) {
            if (next_code.is(':hidden')) {
                next_code.show();
                if (next_code.find('.ETV_HideLink').find('i').hasClass('right')) {
                    next_code.find('.ETV_HideLink').click();
                }
                var next_src_link = next_code.find('.ETV_La').first();
                if (next_src_link.length) {
                    next_src_link.click();
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
        var selected_line = etv_window.find('.ETVSelectedLine').first();
        if (selected_line.length) {
            var next_line = selected_line.next(),
                next_line_link;
            while (next_line.length) {
                if (next_line.is(':visible')) {
                    if (next_line.find('a.ETV_La').length) {
                        next_line_link = next_line.find('a.ETV_La');
                        if (next_line_link.length) {
                            next_line_link.click();
                            return true;
                        }
                    }
                    else if (next_line.find('a.ETV_ShowCommentCode').length && !next_line.next('span').is(':visible')) {
                        next_line.next('span').find('.ETV_La').click();
                        next_line.addClass('ETVSelectedLine');
                        return true;
                    }
                }
                next_line = next_line.next()
            }
        }
        return false;
    }
    function select_prev_line() {
        var selected_line = etv_window.find('.ETVSelectedLine').first();
        if (selected_line.length) {
            var prev_line = selected_line.prev(),
                prev_line_link;
            while (prev_line.length) {
                if (prev_line.is(':visible')) {
                    if (prev_line.find('a.ETV_La').length) {
                        prev_line_link = prev_line.find('a.ETV_La');
                        if (prev_line_link.length) {
                            prev_line_link.click();
                            return true;
                        }
                    }
                    else if (prev_line.find('a.ETV_ShowCommentCode').length && !prev_line.next('span').is(':visible')) {
                        prev_line.next('span').find('.ETV_La').click();
                        prev_line.addClass('ETVSelectedLine');
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
        var selected_line = etv_window.find('.ETVSelectedLine').first();
        if (!selected_line.length) {
            err_notify($('#error___no_selected_line').text());
            clearInterval(interval);
            return false;
        }
        if ($.active > 0 || !ready_for_next_string) {
            return false;
        }
        etv_window.scrollTop(etv_window.scrollTop() + selected_line.position().top - etv_window.height() * 3/10);
        if (!select_next_line()) {
            clearInterval(interval);
            success_notify($('#play_finished').text());
            return false;
        }
        return false;
    }
    function play_etv_backward() {
        var selected_line = etv_window.find('.ETVSelectedLine').first();
        if (!selected_line.length) {
            err_notify($('#error___no_selected_line').text());
            clearInterval(interval);
            return false;
        }
        if ($.active > 0 || !ready_for_next_string) {
            return false;
        }
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

    $('.ETV_LN_Note, .ETV_LN_Warning').click(function () {
        var next_src_link = $(this).parent().next('span').find('.ETV_La').first();
        if (next_src_link.length) {
            next_src_link.click();
        }
        if ($(this).hasClass('ETV_LN_Note')) {
            $(this).addClass('ETV_LN_Note_Selected');
        }
        else {
            $(this).addClass('ETV_LN_Warning_Selected');
        }
    });

    etv_window.scroll(function () {
        $(this).find('.ETV_LN').css('left', $(this).scrollLeft());
    });
    $('#ETV_source_code').scroll(function () {
        $(this).find('.ETVSrcL').css('left', $(this).scrollLeft());
    });
    $('#etv_start').click(function () {
        etv_window.children().each(function () {
            if ($(this).is(':visible')) {
                var line_link = $(this).find('a.ETV_La');
                etv_window.scrollTop(etv_window.scrollTop() + $(this).position().top - etv_window.height() * 3/10);
                if (line_link.length) {
                    line_link.click();
                    return false;
                }
            }
        });
        $('#etv_play_forward').click();
    });

    $('#etv_start_backward').click(function () {
        var next_child = etv_window.children().last();
        while (next_child) {
            if (next_child.is(':visible')) {
                var line_link = next_child.find('a.ETV_La');
                if (line_link.length) {
                    etv_window.scrollTop(etv_window.scrollTop() + next_child.position().top - etv_window.height() * 7/10);
                    line_link.click();
                    next_child = null;
                }
            }
            if (next_child) {
                next_child = next_child.prev();
            }
        }
        $('#etv_play_backward').click();
    });
    etv_window.children().each(function () {
        if ($(this).is(':visible')) {
            var line_link = $(this).find('a.ETV_La');
            etv_window.scrollTop(etv_window.scrollTop() + $(this).position().top - etv_window.height() * 3/10);
            if (line_link.length) {
                line_link.click();
                return false;
            }
        }
    });
    $('.ETV_Action').click(function () {
        $(this).parent().find('.ETV_HideLink').click();
        var src_link = $(this).parent().parent().find('.ETV_La').first();
        if (src_link.length) {
            src_link.click();
        }
    });
    $('.ETV_CallbackAction').click(function () {
        $(this).parent().find('.ETV_HideLink').click();
        var src_link = $(this).parent().parent().find('.ETV_La').first();
        if (src_link.length) {
            src_link.click();
        }
    });

    $('.ETV_ShowCode').click(function () {
        var whole_line = $(this).parent().parent(), scope = $(this).attr('id'), showcode_icon = $(this).find('i');
        if (showcode_icon.hasClass('unhide')) {
            showcode_icon.removeClass('unhide').addClass('hide');
            whole_line.find('.ETV_FuncCode').show();
            whole_line.find('.ETV_FuncName').hide();
            $('.' + scope).each(function () {
                var curr_line_type = $(this).attr('data-type');
                if ((curr_line_type == 'normal' || curr_line_type == 'eye-control') && (!$(this).hasClass('commented'))) {
                    $(this).show();
                }
            });
        }
        else {
            showcode_icon.removeClass('hide').addClass('unhide');
            whole_line.find('.ETV_FuncCode').hide();
            whole_line.find('.ETV_FuncName').show();
            $('.' + scope).each(function () {
                var curr_line_type = $(this).attr('data-type'),
                    curr_hidelink = $(this).find('a[class="ETV_HideLink"]');
                if (!($(this).hasClass('func_collapsed') && curr_hidelink.length)) {
                    curr_hidelink.click();
                }
                if (curr_line_type == 'normal' || curr_line_type == 'eye-control') {
                    $(this).hide();
                }
            });
        }
    });
});