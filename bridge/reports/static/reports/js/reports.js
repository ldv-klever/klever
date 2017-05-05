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

function component_filters_data() {
    var filter_values = {};

    var comp_val = $('#filter__value__attr_component').val();
    if (comp_val.length > 0) {
        filter_values['component'] = {
            type: $('#filter__type__attr_component').val(),
            value: comp_val
        }
    }
    var attr_val = $('#filter__attr__attr_value').val(),
        attr_attr = $('#filter__attr__attr_name').val();
    if (attr_val.length > 0 && attr_attr.length > 0) {
        filter_values['attr'] = {
            attr: attr_attr,
            type: $('#filter__type__attr_attr').val(),
            value: attr_val
        }
    }
    var order_type = $('input[name="order_type"]:checked').val();
    if (order_type === 'attr') {
        order_type = $('#order__attr__name').val();
        if (!order_type.length) {
            order_type = 'component';
        }
    }
    return JSON.stringify({filters: filter_values, order: [order_type, $('input[name="order_value"]:checked').val()]});
}

function unsafe_filters_data() {
    var view_values = {}, filter_values = {};
    var columns = [];
    $('input[id^="list_filter_checkbox__"]').each(function () {
        if ($(this).is(':checked')) {
            columns.push($(this).attr('id').replace('list_filter_checkbox__', ''));
        }
    });
    view_values['columns'] = columns;
    var order = $('#filter__attr__order').val();
    if (order.length > 0) {
        view_values['order'] = [order, $('input[name="order_value"]:checked').val()];
    }
    else {
        view_values['order'] = ['default', $('input[name="order_value"]:checked').val()];
    }

    var attr_val = $('#filter__attr__value').val(),
        attr_attr = $('#filter__attr__attr').val();
    if (attr_val.length > 0 && attr_attr.length > 0) {
        filter_values['attr'] = {
            attr: attr_attr,
            type: $('#filter__attr__type').val(),
            value: attr_val
        }
    }
    view_values['filters'] = filter_values;
    return JSON.stringify(view_values);
}

function safe_filters_data() {
    return unsafe_filters_data();
}

function unknown_filters_data() {
    var view_values = {filters: {}};

    var order = $('#filter__attr__order').val();
    if (order.length > 0) {
        view_values['order'] = [order, $('input[name="order_value"]:checked').val()];
    }
    else {
        view_values['order'] = ['component', $('input[name="order_value"]:checked').val()];
    }

    var comp_val = $('#filter__value__attr_component').val();
    if (comp_val.length > 0) {
        view_values['filters']['component'] = {
            type: $('#filter__type__attr_component').val(),
            value: comp_val
        }
    }
    var attr_val = $('#filter__attr__attr_value').val(),
        attr_attr = $('#filter__attr__attr_name').val();
    if (attr_val.length > 0 && attr_attr.length > 0) {
        view_values['filters']['attr'] = {
            attr: attr_attr,
            type: $('#filter__type__attr_attr').val(),
            value: attr_val
        }
    }
    return JSON.stringify(view_values);
}

$(document).ready(function () {
    $('#resources-note').popup();
    $('#component_name_tr').popup({
        popup: $('#timeinfo_popup'),
        position: 'right center',
        hoverable: true,
        delay: {
            show: 100,
            hide: 300
        }
    });
    $('#computer_description_tr').popup({
        popup: $('#computer_info_popup'),
        position: 'right center',
        hoverable: true,
        delay: {
            show: 100,
            hide: 300
        }
    });

    $('.report-data-popup').each(function () {
        $(this).popup({
            html: $(this).attr('data-content'),
            position: 'right center',
            hoverable: $(this).hasClass('hoverable')
        });
    });

    $('.parent-popup').popup({inline:true});
    $('.ui.dropdown').dropdown();
    $('#order__type__attr').parent().checkbox({
        onChecked: function () {
            $('#order__attr__value_div').show();
        }
    });
    $('#order__type__component').parent().checkbox({
        onChecked: function () {
            $('#order__attr__value_div').hide();
        }
    });
    $('#order__type__date').parent().checkbox({
        onChecked: function () {
            $('#order__attr__value_div').hide();
        }
    });

    $('input[class=buttons-view-type]').each(function () {
        var data_collection;
        switch ($(this).val()) {
            case '3':
                data_collection = component_filters_data;
                break;
            case '4':
                data_collection = unsafe_filters_data;
                break;
            case '5':
                data_collection = safe_filters_data;
                break;
            case '6':
                data_collection = unknown_filters_data;
                break;
            default:
                break;
        }
        if (data_collection) {
            set_actions_for_views($(this).val(), data_collection);
        }
    });

    $('#file_content_modal').modal('setting', 'transition', 'fade');
    $('#show_component_log').click(function () {
        $.ajax({
            url: '/reports/logcontent/' + $('#report_pk').val() + '/',
            type: 'GET',
            success: function (data) {
                $('#file_content').text(data);
                $('#file_content_modal').modal('show');
                $('#close_file_view').click(function () {
                    $('#file_content_modal').modal('hide');
                    $('#file_content').empty();
                });
            }
        });
    });

    function activate_inline_markform(data) {
        var markform = $('#inline_mark_form');
        markform.html(data);
        activate_tags();
        markform.find('.ui.checkbox').checkbox();
        markform.show();
        $('#cancel_create_mark').click(function () {
            $('#inline_mark_form').hide().empty();
        });
        $('#save_inline_mark_btn').click(function () {
            $('#dimmer_of_page').addClass('active');
            var data, mark_id = $('#mark_pk');
            if (mark_id.length) {
                data = {savedata: collect_markdata(), mark_id: mark_id.val()}
            }
            else {
                data = {savedata: collect_new_markdata()}
            }
            $.post(
                marks_ajax_url + 'save_mark/',
                data,
                function (data) {
                    if (data.error) {
                        $('#dimmer_of_page').removeClass('active');
                        err_notify(data.error);
                    }
                    else if ('cache_id' in data) {
                        window.location.href = '/marks/association_changes/' + data['cache_id'] + '/';
                    }
                }
            );
        });
    }

    $('#create_light_mark_btn').click(function () {
        $.post(
            marks_ajax_url + 'inline_mark_form/',
            {
                report_id: $('#report_pk').val(),
                type: $('#report_type').val()
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else if ('data' in data) {
                    activate_inline_markform(data['data']);
                }
            }
        );
    });

    $('button[id^="inline_edit_mark_"]').click(function () {
        $.post(
            marks_ajax_url + 'inline_mark_form/',
            {
                mark_id: $(this).attr('id').replace('inline_edit_mark_', ''),
                type: $('#report_type').val()
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else if ('data' in data) {
                    activate_inline_markform(data['data']);
                }
            }
        );
    });
    $('#show_leaf_attributes').click(function () {
        var attr_table = $('#leaf_attributes');
        if (attr_table.is(':hidden')) {
            attr_table.show();
        }
        else {
            attr_table.hide();
        }
    });
    $('button[id^="unconfirm_association_"]').click(function () {
        $.post(
            marks_ajax_url + 'unconfirm-association/',
            {
                mark_id: $(this).attr('id').replace('unconfirm_association_', ''),
                report_id: $('#report_pk').val()
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    window.location.replace('');
                }
            }
        );
    });
    $('button[id^="confirm_association_"]').click(function () {
        $.post(
            marks_ajax_url + 'confirm-association/',
            {
                mark_id: $(this).attr('id').replace('confirm_association_', ''),
                report_id: $('#report_pk').val()
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    window.location.replace('');
                }
            }
        );
    });
    $('.like-popup').popup({
        hoverable: true,
        position: 'top right'
    });

    $('button[id^="like_association_"]').click(function () {
        $.post(
            marks_ajax_url + 'like-association/',
            {
                mark_id: $(this).attr('id').replace('like_association_', ''),
                report_id: $('#report_pk').val(),
                dislike: false
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    window.location.replace('');
                }
            }
        );
    });
    $('button[id^="dislike_association_"]').click(function () {
        $.post(
            marks_ajax_url + 'like-association/',
            {
                mark_id: $(this).attr('id').replace('dislike_association_', ''),
                report_id: $('#report_pk').val(),
                dislike: true
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    window.location.replace('');
                }
            }
        );
    });
});

