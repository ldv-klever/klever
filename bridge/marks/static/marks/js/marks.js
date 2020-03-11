/*
 * Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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
    $('table').tablesort();

    function get_selected_marks() {
        let marks_ids = [];
        $('.mark-checkbox:checked').each(function () {
            marks_ids.push($(this).val())
        });
        return  marks_ids;
    }

    let download_marks_btn = $('#download_selected_marks_btn'),
        remove_selected_marks_btn = $('#remove_marks_modal_show');
    $('.mark-checkbox').parent().checkbox({
        onChange: function () {
            let sel_marks = get_selected_marks();
            update_action_button(download_marks_btn, !sel_marks.length);
            update_action_button(remove_selected_marks_btn, !sel_marks.length);
        }
    });

    // Remove marks action
    let rm_marks_modal = $('#remove_marks_modal');
    rm_marks_modal.modal({transition: 'fly up', autofocus: false, closable: false});
    rm_marks_modal.find('.modal-cancel').click(function () { rm_marks_modal.modal('hide') });
    rm_marks_modal.find('.modal-confirm').click(function () {
        let ids_for_del = get_selected_marks();
        if (!ids_for_del.length) {
            rm_marks_modal.modal('hide');
            err_notify($('#no_marks_selected').text());
        }
        else {
            $('#dimmer_of_page').addClass('active');
            $.ajax({
                url: '/marks/api/remove-' + $('#marks_type').val() + '-marks/',
                method: 'DELETE',
                data: {ids: JSON.stringify(ids_for_del)},
                success: function () { window.location.replace('') },
                error: function () { $('#dimmer_of_page').removeClass('active') }
            });
        }
    });
    remove_selected_marks_btn.click(function () {
        let ids_for_del = get_selected_marks();
        if (ids_for_del.length) rm_marks_modal.modal('show');
        else err_notify($('#no_marks_selected').text());
    });

    // Download selected marks
    download_marks_btn.click(function () {
        let sel_marks = get_selected_marks();
        if (!sel_marks.length) return err_notify($('#no_marks_selected').text());
        let marks_data = {};
        marks_data[$('#marks_type').val()] = sel_marks;
        window.location.href = $('#download_marks_url').text() + '?marks=' + encodeURIComponent(JSON.stringify(marks_data));
    });
});
