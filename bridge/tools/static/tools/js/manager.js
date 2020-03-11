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
    $('.api-request-btn').click(function () {
        $('#dimmer_of_page').addClass('active');
        $.ajax({
            url: $(this).data('url'),
            method: $(this).data('method'),
            data: {},
            success: function (resp) {
                $('#dimmer_of_page').removeClass('active');
                success_notify(resp['message']);
            }
        })
    });
    $('#recalc_for_all_decisions_checkbox').checkbox({
        onChecked: function () {
            $('input[name="decision"]').each(function () {
                $(this).prop('checked', true);
                $(this).parent().addClass('disabled');
            });
        },
        onUnchecked: function () {
            $('input[name="decision"]').each(function () {
                $(this).prop('checked', false);
                $(this).parent().removeClass('disabled');
            });
        }
    });

    //=================
    // Upload all marks
    let upload_all_marks_modal = $('#upload_all_marks_modal'),
        uploaded_marks_modal = $('#uploaded_marks_modal');
    upload_all_marks_modal.modal({transition: 'vertical flip'}).modal('attach events', '#upload_all_marks', 'show');
    upload_all_marks_modal.find('.modal-cancel').click(function () {
        upload_all_marks_modal.modal('hide');
    });
    $('#upload_all_marks_file_input').on('fileselect', function () {
        $('#upload_all_marks_filename').text($(this)[0].files[0].name);
    });

    uploaded_marks_modal.modal({transition: 'fade down', closable: false});
    uploaded_marks_modal.find('.modal-cancel').click(function () {
        uploaded_marks_modal.modal('hide');
    });

    upload_all_marks_modal.find('.modal-confirm').click(function () {
        let files = $('#upload_all_marks_file_input')[0].files, data = new FormData();
        if (files.length <= 0) return err_notify($('#error__no_file_chosen').text());

        data.append('file', files[0]);
        if ($('#delete_marks_before_upload').is(':checked')) data.append('delete', '1');

        upload_all_marks_modal.modal('hide');
        $('#dimmer_of_page').addClass('active');
        $.ajax({
            url: $(this).data('url'),
            type: 'POST',
            data: data,
            dataType: 'json',
            contentType: false,
            processData: false,
            mimeType: 'multipart/form-data',
            xhr: function() {
                return $.ajaxSettings.xhr();
            },
            success: function (data) {
                $('#dimmer_of_page').removeClass('active');
                $('#num_uploaded_unsafe_marks').text(data['unsafe'] ? data['unsafe'] : 0);
                $('#num_uploaded_safe_marks').text(data['safe'] ? data['safe'] : 0);
                $('#num_uploaded_unknown_marks').text(data['unknown'] ? data['unknown'] : 0);
                $('#num_uploaded_fail_marks').text(data['fail'] ? data['fail'] : 0);
                uploaded_marks_modal.modal('show');
            }
        });
    });
});
