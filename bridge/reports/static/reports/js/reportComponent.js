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
    $('.ui.dropdown').dropdown();
    $('.parent-popup').popup({inline:true});

    $('#resources-note').popup();
    $('#component_name_tr').popup({
        popup: $('#timeinfo_popup'),
        position: 'right center',
        hoverable: true,
        delay: {show: 100, hide: 300}
    });
    $('#computer_description_tr').popup({
        popup: $('#computer_info_popup'),
        position: 'right center',
        hoverable: true,
        delay: {show: 100, hide: 300}
    });
    $('.report-data-popup').each(function () {
        $(this).popup({
            html: $(this).attr('data-content'),
            position: 'right center',
            hoverable: $(this).hasClass('hoverable')
        });
    });

    $('#file_content_modal').modal('setting', 'transition', 'fade');
    $('#show_component_log').click(function () {
        var report_id = $('#report_pk').val();
        $.get('/reports/logcontent/' + report_id + '/', {}, function (resp) {
            if (resp.error) {
                err_notify(resp.error);
                return false;
            }
            $('#file_content').text(resp.content);
            $('#download_file_href').attr('href', '/reports/log/' + report_id + '/');
            $('#file_content_modal').modal('show');
            $('#close_file_view').click(function () {
                $('#file_content_modal').modal('hide');
                $('#file_content').empty();
                $('#download_file_href').attr('href', '#');
            });
        });
    });

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