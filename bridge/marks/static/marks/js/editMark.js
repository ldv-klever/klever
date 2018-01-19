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
    activate_tags();

    $('#compare_function').change(set_action_on_func_change);

    $('#mark_version_selector').change(function () {
        $.ajax({
            url: marks_ajax_url + 'get_mark_version_data/',
            data: {
                version: $(this).val(),
                mark_id: $('#mark_pk').val(),
                type: $('#mark_type').val()
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    var add_data = $('#mark_data_div');
                    add_data.html(data.data);
                    $('#compare_function').change(set_action_on_func_change);
                    activate_tags();
                    add_data.find('.ui.dropdown').each(function () {
                        if (!$(this).hasClass('search')) {
                            $(this).dropdown();
                        }
                    });
                    add_data.find('.ui.checkbox').checkbox();
                    add_data.find('.ui.accordion').accordion();
                }
            }
        });
    });

    $('#save_mark_btn').click(function () {
        $.post(
            marks_ajax_url + 'save_mark/',
            {savedata: collect_markdata()},
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else if ('cache_id' in data) {
                    window.location.replace('/marks/association_changes/' + data['cache_id'] + '/');
                }
            }
        );
    });
});
