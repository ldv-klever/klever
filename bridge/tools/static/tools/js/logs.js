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

function activate_result() {
    $('.func_name').click(function (event) {
        event.preventDefault();
        $.post(
            '/tools/ajax/call_stat/',
            {
                action: 'between',
                name: $(this).text()
            },
            function (data) {
                $('#statistic_result').html(data);
                $('#statistic_modal').modal('show');
            }
        );
    });
}

$(document).ready(function () {
    var borders_type_input = $('#borders_type');
    $('#date1').calendar();
    $('#date2').calendar();
    $('#statistic_modal').modal({transition: 'fade in', autofocus: false});
    $('#list_type').dropdown();
    borders_type_input.dropdown();
    borders_type_input.change(function () {
        if ($(this).val() == '0') {
            $('#interval_field').hide();
            $('#date2_field').show();
            $('#fname_field').show();
        }
        else {
            $('#date2_field').hide();
            $('#fname_field').hide();
            $('#interval_field').show();
        }
    });
    $('#get_table').click(function () {
        var list_type = $('#list_type').val(),
            borders_type = $('#borders_type').val(),
            date1 = $('#date1').calendar('get date'),
            args = {}, url, func_name = $('#func_name').val();

        if (list_type == '0') {
            url = '/tools/ajax/call_list/';
        }
        else {
            url = '/tools/ajax/call_stat/';
        }
        if (borders_type == '0') {
            args['action'] = 'between';
            if (date1) {
                args['date1'] = date1.getTime() / 1000;
            }
            var date2 = $('#date2').calendar('get date');
            if (date2) {
                args['date2'] = date2.getTime() / 1000;
            }
            if (func_name.length) {
                args['name'] = func_name;
            }
        }
        else {
            args['action'] = 'around';
            if (!date1) {
                err_notify('The date is required');
                return false;
            }
            args['date'] = date1.getTime() / 1000;
            var interval = $('#time_interval').val();
            if (interval) {
                args['interval'] = parseInt(interval, 10);
            }
        }
        $.post(
            url, args,
            function (data) {
                if (list_type == '0') {
                    $('#result').html(data);
                    activate_result();
                }
                else {
                    $('#statistic_result').html(data);
                    $('#statistic_modal').modal('show');
                }

            }
        );
    });
});
