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
    $('.ui.calendar').calendar();
    $('#statistic_modal').modal({transition: 'fade in', autofocus: false});
    $('#data_type').dropdown();
    $('#call_log_action').dropdown({onChange: function () {
        if ($(this).val() === 'between') {
            $('.call-around-field').hide();
            $('.call-between-field').show();
        }
        else {
            $('.call-between-field').hide();
            $('.call-around-field').show();
        }
    }});

    function get_timestamp(calendar_id) {
        let date_value = $(`#${calendar_id}`).calendar('get date');
        return date_value ? date_value.getTime() / 1000 : null;
    }

    $('#get_data_btn').click(function () {
        let data = {'action': $('#call_log_action').val()},
            data_type = $('#data_type').val(),
            url = data_type === 'log' ? $('#log_api_url').val() : $('#statistic_api_url').val();

        if (data['action'] === 'between') {
            data['date1'] = get_timestamp('date1');
            data['date2'] = get_timestamp('date2');
            data['name'] = $('#func_name').val();
        }
        else {
            data['date'] = get_timestamp('date1');
            if (!data['date']) return err_notify('The date is required');

            let interval = $('#time_interval').val();
            if (interval) data['interval'] = parseInt(interval, 10);
        }

        $.post(url, data, function (resp) {
            if (data_type === 'log') {
                let result_container = $('#result_container');
                result_container.html(resp);
                result_container.find('.func_name').click(function (event) {
                    event.preventDefault();
                    $.post($('#statistic_api_url').val(), {
                        action: 'between',
                        name: $(this).data('name')
                    },
                    function (resp) {
                        $('#statistic_result').html(resp);
                        $('#statistic_modal').modal('show');
                    });
                });
            }
            else {
                $('#statistic_result').html(resp);
                $('#statistic_modal').modal('show');
            }
        });
    });
});
