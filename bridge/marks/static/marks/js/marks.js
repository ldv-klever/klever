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

    $('#remove_marks_popup').modal({transition: 'fly up', autofocus: false, closable: false});
    $('#cancel_remove_marks').click(function () {$('#remove_marks_popup').modal('hide')});
    $('#show_remove_mark_popup').click(function () {$('#remove_marks_popup').modal('show')});
    $('#show_remove_marks_popup').click(function () {
        var ids_for_del = [];
        $('input[id^="mark_checkbox__"]').each(function () {
            if ($(this).is(':checked')) {
                ids_for_del.push($(this).attr('id').replace('mark_checkbox__', ''));
            }
        });
        if (ids_for_del.length > 0) {
            $('#remove_marks_popup').modal('show');
        }
        else {
            err_notify($('#no_marks_selected').text())
        }
    });

    $('#confirm_remove_marks').click(function () {
        var ids_for_del = [];
        $('input[id^="mark_checkbox__"]').each(function () {
            if ($(this).is(':checked')) {
                ids_for_del.push($(this).attr('id').replace('mark_checkbox__', ''));
            }
        });
        if (!ids_for_del.length) {
            $('#remove_marks_popup').modal('hide');
            err_notify($('#no_marks_selected').text());
        }
        else {
            $.ajax({
                url: marks_ajax_url + 'delete/',
                data: {
                    'type': $('#marks_type').val(),
                    ids: JSON.stringify(ids_for_del)
                },
                type: 'POST',
                success: function (data) {
                    if (data.error) {
                        err_notify(data.error);
                    }
                    else {
                        window.location.replace('');
                    }
                }
            });
        }
    });
    $('#confirm_remove_mark').click(function () {
        var mark_type = $('#mark_type').val();
        $.ajax({
            url: marks_ajax_url + 'delete/',
            data: {
                'type': mark_type,
                ids: JSON.stringify([$('#mark_pk').val()])
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    var report_id = $('#report_id');
                    if (report_id.length) {
                        window.location.replace('/reports/' + mark_type + '/' + report_id.val() + '/');
                    }
                    else {
                        window.location.replace('/marks/' + mark_type + '/');
                    }
                }
            }
        });
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
                    $('#mark_data_div').html(data.data);
                    $('#compare_function').change(set_action_on_func_change);
                    activate_tags();
                    $('.ui.dropdown').each(function () {
                        if (!$(this).hasClass('search')) {
                            $(this).dropdown();
                        }
                    });
                    $('.ui.checkbox').checkbox();
                    $('.ui.accordion').accordion();
                }
            }
        });
    });

    $('#save_mark_btn').click(function () {
        var comment_input = $('#edit_mark_comment');
        if (comment_input.val().length > 0) {
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
        }
        else {
            err_notify($('#error__comment_required').text());
            comment_input.focus();
        }
    });

    $('#edit_mark_versions').click(function () {
        $.post(
            marks_ajax_url + 'getversions/',
            {mark_id: $('#mark_pk').val(), mark_type: $('#mark_type').val()},
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    $('#div_for_version_list').html(data);
                    set_actions_for_mark_versions_delete();
                }
            }
        );
    });

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
