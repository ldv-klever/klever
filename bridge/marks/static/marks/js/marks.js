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
    $('.ui.dropdown').each(function () { if (!$(this).hasClass('search')) $(this).dropdown() });

    $('#remove_marks_popup').modal({transition: 'fly up', autofocus: false, closable: false});
    $('#cancel_remove_marks').click(function () {$('#remove_marks_popup').modal('hide')});
    $('#show_remove_marks_popup').click(function () {
        var ids_for_del = [];
        $('input[id^="mark_checkbox__"]').each(function () {
            if ($(this).is(':checked')) {
                ids_for_del.push($(this).attr('id').replace('mark_checkbox__', ''));
            }
        });
        if (ids_for_del.length > 0) {
            $('#remove_marks_popup').modal('show');
        }
        else {
            err_notify($('#no_marks_selected').text())
        }
    });
    $('#confirm_remove_marks').click(function () {
        var ids_for_del = [];
        $('input[id^="mark_checkbox__"]').each(function () {
            if ($(this).is(':checked')) {
                ids_for_del.push($(this).attr('id').replace('mark_checkbox__', ''));
            }
        });
        if (!ids_for_del.length) {
            $('#remove_marks_popup').modal('hide');
            err_notify($('#no_marks_selected').text());
        }
        else {
            $.post('/marks/delete/', {'type': $('#marks_type').val(), ids: JSON.stringify(ids_for_del)}, function (data) {
                data.error ? err_notify(data.error) : window.location.replace('');
            });
        }
    });
});
