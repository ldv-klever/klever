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
    $('.bottom-attached').parent().addClass('with-bottom-attachment');

    $('.parent-popup').popup({inline:true});
    $('.ui.dropdown').dropdown();

    $('#create_light_mark_btn').click(function () {
        get_inline_mark_form($('#inline_mark_form'), $('#report_pk').val(), 'create');
    });

    $('button[id^="inline_edit_mark_"]').click(function () {
        get_inline_mark_form($('#inline_mark_form'), $(this).attr('id').replace('inline_edit_mark_', ''), 'edit');
    });

    $('#show_leaf_attributes').click(function () {
        var attr_table = $('#leaf_attributes');
        attr_table.is(':hidden') ? attr_table.show() : attr_table.hide();
    });

    $('[id*="_association_"]').click(function () {
        var id_arr = $(this).attr('id').split('_'),  // [action, 'association', mark_id]
            url = ['/marks/association', $('#report_type').val(), $('#report_pk').val(), id_arr[2], id_arr[0], ''].join('/');
        $.post(url, {}, function (data) { data.error ? err_notify(data.error) : window.location.replace('') });
    });
    $('.like-popup').popup({hoverable: true, position: 'top right'});

    $('.attr-data-href').click(function (event) {
        event.preventDefault();
        var attr_id = $(this).data('attr-id');
        $.get('/reports/attrdata-content/' + attr_id + '/', {}, function (resp) {
            if (resp.error) {
                err_notify(resp.error);
                return false;
            }
            $('#file_content').text(resp.content);
            $('#download_file_href').attr('href', '/reports/attrdata/' + attr_id + '/');
            $('#file_content_modal').modal('show');
            $('#close_file_view').click(function () {
                $('#file_content_modal').modal('hide');
                $('#file_content').empty();
                $('#download_file_href').attr('href', '#');
            });
        });
    });
});