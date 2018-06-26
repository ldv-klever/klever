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
    $('.note-popup').popup();

    $('#save_notifications').click(function () {
        var notifications = [], self_ntf = false;
        $("input[id^='ntf__']").each(function () {
            var curr_id = $(this).attr('id').replace('ntf__', '');
            if ($(this).is(':checked')) {
                notifications.push(curr_id);
            }
        });
        if ($('#self_ntf').is(':checked')) {
            self_ntf = true;
        }
        $.post(
            '/users/ajax/save_notifications/',
            {self_ntf: self_ntf, notifications: JSON.stringify(notifications)},
            function (data) {
                data.error ? err_notify(data.error) : success_notify(data.message);
            },
            'json'
        );
    });
});