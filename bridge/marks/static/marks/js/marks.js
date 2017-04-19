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

function collect_filters_data() {
    var view_values = {columns: []}, filter_values = {},
        order_type = $('input[name=marks_enable_order]:checked').val();
    $('input[id^="marks_filter_checkbox__"]:checked').each(function () {
        view_values['columns'].push($(this).attr('id').replace('marks_filter_checkbox__', ''));
    });
    if (order_type == 'attribute') {
        var order = $('#filter__attr__order').val();
        if (order.length > 0) {
            view_values['order'] = order;
        }
    }
    else if (order_type == 'num_of_links') {
        view_values['order'] = 'num_of_links';
    }

    var attr_val = $('#filter__attr__value').val(),
        attr_attr = $('#filter__attr__attr').val();
    if (attr_val && attr_attr && attr_val.length > 0 && attr_attr.length > 0) {
        filter_values['attr'] = {
            attr: attr_attr,
            type: $('#filter__attr__type').val(),
            value: attr_val
        }
    }
    if ($('#filter__enable__verdict').is(':checked')) {
        filter_values['verdict'] = {
            type: $('#filter__type__verdict').val(),
            value: $('#filter__value__verdict').children(':selected').val()
        }
    }
    if ($('#filter__enable__status').is(':checked')) {
        filter_values['status'] = {
            type: $('#filter__type__status').val(),
            value: $('#filter__value__status').children(':selected').val()
        }
    }
    if ($('#filter__enable__author').is(':checked')) {
        filter_values['author'] = {
            type: 'is',
            value: parseInt($('#filter__value__author').children(':selected').val())
        }
    }
    if ($('#filter__enable__type').is(':checked')) {
        filter_values['type'] = {
            type: $('#filter__type__type').val(),
            value: $('#filter__value__type').val()
        }
    }
    if ($('#filter__enable__component').is(':checked')) {
        var filter_val = $('#filter__value__component').val();
        if (filter_val.length > 0) {
            filter_values['component'] = {
                type: $('#filter__type__component').val(),
                value: filter_val
            }
        }
    }
    view_values['filters'] = filter_values;
    return JSON.stringify(view_values);
}

$(document).ready(function () {
    var view_type_input = $('#view_type');
    if (view_type_input.length) {
        set_actions_for_views(view_type_input.val(), collect_filters_data);
    }
    activate_tags();
    $('.ui.dropdown').each(function () {
        if (!$(this).hasClass('search')) {
            $(this).dropdown();
        }
    });
    $('#remove_mark_popup').modal({transition: 'fly up', autofocus: false, closable: false})
        .modal('attach events', '#show_remove_mark_popup', 'show');
    $('#cancel_remove_mark').click(function () {
        $('#remove_mark_popup').modal('hide');
    });

    $('#remove_marks_popup').modal({transition: 'fly up', autofocus: false, closable: false});
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
    $('#cancel_remove_marks').click(function () {
        $('#remove_marks_popup').modal('hide');
    });
    $('#confirm_remove_marks').click(function () {
        var ids_for_del = [];
        $('input[id^="mark_checkbox__"]').each(function () {
            if ($(this).is(':checked')) {
                ids_for_del.push($(this).attr('id').replace('mark_checkbox__', ''));
            }
        });
        if (ids_for_del.length == 0) {
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

    $('#convert_function').change(function () {
        $.ajax({
            url: marks_ajax_url + 'get_func_description/',
            data: {func_id: $(this).children('option:selected').val(), func_type: 'convert'},
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else if (data.description) {
                    $('#convert_function_description').text(data.description);
                }

            }
        });
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
});
