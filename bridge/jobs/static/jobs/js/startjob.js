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
    $('.note-popup').popup();

    function collect_data() {
        let data = {
            priority: $('input[name="priority"]:checked').val(),
            scheduler: $('input[name="scheduler"]:checked').val(),
            job_weight: $('input[name="job_weight"]:checked').val(),
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

        return {mode: 'data', data: JSON.stringify(data)}
    }

    function fill_data(resp) {
        $(`input[name="priority"][value="${resp['priority']}"]`).prop('checked', true);
        $(`input[name="scheduler"][value="${resp['scheduler']}"]`).prop('checked', true);
        $(`input[name="job_weight"][value="${resp['job_weight']}"]`).prop('checked', true);
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

    $('#default_configs').dropdown({
        onChange: function () {
            let conf_name = $('#default_configs').val(),
                file_form = $('#upload_file_conf_form');
            if (conf_name === 'file_conf') file_form.show();
            else {
                file_form.hide();
                $.post($('#api_conf_url').val(), {name: conf_name, job: $('#job_pk').val()}, fill_data);
            }
        }
    });
    $('#file_conf').on('fileselect', function () {
        $('#upload_file_conf_form').submit();
        let data = new FormData();
        data.append('name', 'file');
        data.append('file', $(this)[0].files[0]);
        $.ajax({
            url: $('#api_conf_url').val(),
            type: 'POST',
            data: data,
            dataType: 'json',
            contentType: false,
            processData: false,
            mimeType: 'multipart/form-data',
            xhr: function() { return $.ajaxSettings.xhr() },
            success: fill_data
        });
    });

    $('.normal-dropdown').dropdown();

    $('#start_job_decision').click(function () {
        $.ajax({
            url: $(this).data('url'),
            data: collect_data(),
            type: 'POST',
            success: function (resp) {
                window.location.replace(resp['url']);
            }
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
