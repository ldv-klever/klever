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
    $('.note-popup').popup();
    $('.normal-dropdown').dropdown();

    function collect_data() {
        let data = {
            priority: $('input[name="priority"]:checked').val(),
            scheduler: $('input[name="scheduler"]:checked').val(),
            weight: $('input[name="weight"]:checked').val(),
            coverage_details: $('input[name="coverage_details"]:checked').val(),
            max_tasks: $('#max_tasks').val(),
            parallelism: [$('#parallelism_0').val(), $('#parallelism_1').val(), $('#parallelism_2').val()],
            memory: $('#memory').val().replace(/,/, '.'),
            cpu_num: $('#cpu_num').val() || null,
            disk_size: $('#disk_size').val().replace(/,/, '.'),
            cpu_model: $('#cpu_model').val(),
            console_level: $('#console_level').val(),
            file_level: $('#file_level').val(),
            console_formatter: $('#console_formatter').val(),
            file_formatter: $('#file_formatter').val()
        };
        $('.boolean-value').each(function () {
            data[$(this).attr('id')] = $(this).is(':checked');
        });

        return {data: JSON.stringify(data), name: $('#decision_name').val().trim()}
    }

    function fill_data(resp) {
        $(`input[name="priority"][value="${resp['priority']}"]`).prop('checked', true);
        $(`input[name="scheduler"][value="${resp['scheduler']}"]`).prop('checked', true);
        $(`input[name="weight"][value="${resp['weight']}"]`).prop('checked', true);
        $(`input[name="coverage_details"][value="${resp['coverage_details']}"]`).prop('checked', true);
        $('#max_tasks').val(resp['max_tasks']);
        $('#parallelism_0').val(resp['parallelism'][0]);
        $('#parallelism_1').val(resp['parallelism'][1]);
        $('#parallelism_2').val(resp['parallelism'][2]);
        $('#memory').val(resp['memory']);
        $('#cpu_num').val(resp['cpu_num'] || '');
        $('#disk_size').val(resp['disk_size']);
        $('#cpu_model').val(resp['cpu_model']);
        $('#console_level').val(resp['console_level']);
        $('#file_level').val(resp['file_level']);
        $('#console_formatter').val(resp['console_formatter']);
        $('#file_formatter').val(resp['file_formatter']);
        $('.boolean-value').each(function () {
            if (resp[$(this).attr('id')]) $(this).prop('checked', true);
            else $(this).prop('checked', false);
        });
    }

    let file_form = $('#upload_file_conf_form'),
        lastconf_form = $('#select_lastconf_form');
    $('#default_configs').dropdown({
        onChange: function () {
            let conf_name = $('#default_configs').val();
            if (conf_name === 'file_conf') {
                lastconf_form.hide();
                file_form.show();
            }
            else if(conf_name === 'lastconf') {
                file_form.hide();
                lastconf_form.show();
            }
            else {
                file_form.hide();
                lastconf_form.hide();
                $.post($('#api_conf_url').val(), {conf_name: conf_name}, fill_data);
            }
        }
    });
    $('#file_conf').on('fileselect', function () {
        let data = new FormData();
        data.append('file_conf', $(this)[0].files[0]);
        api_upload_file(PAGE_URLS.get_conf_url, 'POST', data, fill_data);
    });
    $('#lastconf_select').dropdown({
        onChange: function () {
            $.post($('#api_conf_url').val(), {decision: parseInt($('#lastconf_select').val())}, fill_data);
        }
    });

    $('#start_job_decision').click(function () {
        $.post($(this).data('url'), collect_data(), function (resp) {
            window.location.replace(resp['url'])
        });
    });

    $('.get-attr-value').click(function () {
        $.ajax({
            url: $('#api_values_url').val(),
            type: 'POST',
            data: {
                name: $(this).data('name'),
                value: $(this).data('value')
            },
            success: function (resp) {
                Object.keys(resp).forEach(function(key) {
                    $('#' + key).val(resp[key])
                });
            }
        });
    });
});
