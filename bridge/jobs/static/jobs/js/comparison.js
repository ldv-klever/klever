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
    $('#file_content_modal').modal('setting', 'transition', 'fade');

    $('.show_file_content').click(function (event) {
        event.preventDefault();
        var check_sums = [], file_name = $(this).text();
        $(this).siblings('input').each(function () {
            check_sums.push($(this).val());
        });
        $.post(
            job_ajax_url + 'get_file_by_checksum/',
            {
                check_sums: JSON.stringify(check_sums),
                job1_name: $('#job1_name').val(),
                job2_name: $('#job2_name').val()
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error)
                }
                else {
                    $('#file_content_name').text(file_name);
                    $('#file_content').text(data);
                    $('#file_content_modal').modal('show');
                }
            }
        );
    });

    $('#close_file_view').click(function () {
        $('#file_content_modal').modal('hide');
        $('#file_content').empty();
    });
});