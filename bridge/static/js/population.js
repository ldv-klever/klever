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
    var manager_input = $('#manager_username'), service_input = $('#service_username');
    function check_usernames() {
        if (service_input.length && manager_input.length) {
            if (manager_input.val().length == 0 || service_input.val().length == 0) {
                $('#populate_button').addClass('disabled');
                $('#usernames_required_err').show();
                return false;
            }
            else {
                $('#usernames_required_err').hide();
            }
            if (manager_input.val().length && manager_input.val() == service_input.val()) {
                $('#populate_button').addClass('disabled');
                $('#usernames_err').show();
            }
            else {
                $('#populate_button').removeClass('disabled');
                $('#usernames_err').hide();
            }
        }
    }
    manager_input.on('input', function () {
        check_usernames();
    });
    service_input.on('input', function () {
        check_usernames();
    });
    check_usernames();
    $('#populate_button').click(function () {
        $(this).addClass('disabled');
    });
});
