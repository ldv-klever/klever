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
    $('.ui.dropdown').each(function () {
        if (!$(this).hasClass('search')) {
            $(this).dropdown();
        }
    });

    $('#save_new_mark_btn').click(function () {
        $(this).addClass('disabled');
        $.post(
            marks_ajax_url + 'save_mark/',
            {savedata: collect_new_markdata()},
            function (data) {
                if (data.error) {
                    $('#save_new_mark_btn').removeClass('disabled');
                    err_notify(data.error);
                }
                else if ('cache_id' in data) {
                    window.location.replace('/marks/association_changes/' + data['cache_id'] + '/');
                }
            }
        );
    });

    $('#compare_function').change(set_action_on_func_change);

    $('#test_unknown_mark').click(function () {
        var func = $('#unknown_function').val();
        if (func.length <= 0) {
            err_notify($('#error__function_required').text());
        }
        else {
            $.post(
                marks_ajax_url + 'check-unknown-mark/',
                {
                    report_id: $('#report_pk').val(),
                    function: func,
                    pattern: $('#unknown_problem_pattern').val(),
                    is_regex: $('#is_regexp').is(':checked')
                },
                function (data) {
                    if (data.error) {
                        err_notify(data.error);
                        $('#test_mark_nomatch_div').hide();
                        $('#test_mark_result_div').hide();
                    }
                    else {
                        if (data['matched'] === 1) {
                            $('#test_mark_nomatch_div').hide();
                            $('#test_mark_problem').text(data['problem']);
                            $('#test_mark_result').text(data['result']);
                            $('#test_mark_result_div').show();
                        }
                        else {
                            $('#test_mark_result_div').hide();
                            $('#test_mark_nomatch_div').show();
                            if (data['result'].length > 0) {
                                $('#regexp_err_result').text(data['result']).show();
                            }
                            else {
                                $('#regexp_err_result').text('').hide();
                            }
                        }
                    }
                }
            );
        }
    });
});
