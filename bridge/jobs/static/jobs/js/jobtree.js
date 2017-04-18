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

var do_not_count = [
    'name', 'author', 'date', 'status', '', 'resource', 'format', 'version', 'type', 'identifier', 'progress',
    'parent_id', 'role', 'priority', 'start_date', 'finish_date', 'solution_wall_time', 'operator',
    'average_time', 'local_average_time'
];

function fill_all_values() {
    $("td[id^='all__']").each(function() {
        var cell_id_data = $(this).attr('id').split('__');
        if ($.inArray(cell_id_data[1], do_not_count) == -1) {
            cell_id_data[0] = 'value';
            var sum = 0, have_numbers = false;
            $("td[id^='" + cell_id_data.join('__') + "__']").each(function () {
                var num = parseInt($(this).children().first().text());
                isNaN(num) ? num = 0 : have_numbers = true;
                sum += num;
            });
            if (have_numbers) {
                $(this).text(sum);
            }
        }
    });
}

function fill_checked_values() {
    $("td[id^='checked__']").each(function() {
        var cell_id_data = $(this).attr('id').split('__');
        if ($.inArray(cell_id_data[1], do_not_count) == -1) {
            cell_id_data[0] = 'value';
            var sum = 0, have_numbers = false, is_checked = false;
            $("td[id^='" + cell_id_data.join('__') + "__']").each(function() {
                if ($('#job_checkbox__' + $(this).attr('id').split('__').slice(-1)[0]).is(':checked')) {
                    is_checked = true;
                    var num = parseInt($(this).children().first().text());
                    isNaN(num) ? num = 0 : have_numbers = true;
                    sum += num;
                }
            });
            (have_numbers === true && is_checked === true) ? $(this).text(sum) : $(this).text('-');
        }
    });
}


function add_order_to_available(value, title) {
    var sel = $('#available_orders');
    if (sel.children("option[value='" + value + "']").length === 0) {
        sel.append("<option value='" + value + "'>" + title + "</option>")
    }
    check_order_form()
}

function add_new_order() {
    var available_orders = $('#available_orders'),
        selected_order = available_orders.children('option:selected');

    if (selected_order.length === 1) {
        var sel_title = selected_order.text(),
            sel_value = selected_order.val(),
            selected_orders_div = $('#all_selected_orders');
        if (selected_orders_div.find('div[id=order__' + sel_value + ']').length > 0) {
            return false;
        }
        selected_orders_div.append($('#selected_order_template').html());

        var new_item = selected_orders_div.find('div[id=order__]');
        new_item.attr('id', 'order__' + sel_value);

        var span_obj = new_item.find('span[id=selected_order_title__]');
        span_obj.attr('id', 'selected_order_title__' + sel_value);
        span_obj.text(sel_title);

        var new_button = new_item.find('button[id=remove__order__]');
        new_button.attr('id', 'remove__order__' + sel_value);
        new_button.click(delete_selected_order);
        new_item.find('input').each(function () {
            var old_id = $(this).attr('id');
            $(this).attr('name', sel_value);
            $(this).attr('id', old_id + sel_value);
            new_item.find('label[for="' + old_id + '"]').attr('for', old_id + sel_value);
        });
        available_orders.children('option[value=' + sel_value + ']').remove();
        check_order_form();
    }
    return false;
}

function check_order_form() {
    var available_orders = $('#available_orders');
    if (available_orders.children('option').length > 0) {
        $('#available_orders_form').show();
        available_orders.dropdown('set selected', available_orders.children().first().val());
    }
    else {
        $('#available_orders_form').hide();
    }
}

function check_filters_form() {
    var filters_form = $('#available_filters_form'), available_filters = $('#available_filters');
    if (available_filters.children('option').length > 0) {
        filters_form.show();
        available_filters.dropdown('set selected', available_filters.children().first().val());
        available_filters.next().next().text(available_filters.children().first().text());
    }
    else {
        filters_form.hide();
    }
    $('.ui.checkbox').checkbox();
}

function delete_selected_order() {
    var order_value = $(this).attr('id').split('__').slice(-1)[0];
    add_order_to_available(order_value, $('#selected_order_title__' + order_value).text());
    $('#order__' + order_value).remove();
}

function remove_filter_form() {
    var filter_name = $(this).attr('id').split('__').slice(-1)[0];
    $('#available_filters').append($('<option>', {
        value: filter_name,
        text: $('#filter_title__' + filter_name).text()
    }));
    $('#filter_form__' + filter_name).remove();
    check_filters_form();
}

function getColumns() {
    var columns = [];
    $('#selected_columns').children('option').each(function () {
        columns.push($(this).val());
    });
    return columns
}

function getOrders() {
    var orders = [];
    $('#all_selected_orders').children().each(function() {
        var order_name = $(this).attr('id').replace('order__', '');
        if ($(this).find('input:checked').val() === 'up') {
            order_name = '-' + order_name;
        }
        orders.push(order_name);
    });
    return orders
}

function check_jobs_access(jobs) {
    var status = true;
    $.ajax({
        url: job_ajax_url + 'check_access/',
        type: 'POST',
        dataType: 'json',
        data: {jobs: JSON.stringify(jobs)},
        async: false,
        success: function (res) {
            if (res.error) {
                err_notify(res.message);
                status = false;
            }
        }
    });
    return status;
}

function getFilters() {
    var filters = {};
    $('#selected_filters_list').children().each(function () {
        var filter_name = $(this).attr('id').replace('filter_form__', ''),
            filter_value, filter_data;
        if (filter_name === 'name') {
            filter_value = $('#filter_value__' + filter_name).val();
            if (filter_value.length) {
                filter_data = {
                    type: $('#filter_type__' + filter_name ).children("option:selected").val(),
                    value: filter_value
                };
            }
        }
        else if (filter_name === 'change_author') {
            filter_data = {
                type: $('#filter_type__' + filter_name).val(),
                value: $('#filter_value__' + filter_name).children("option:selected").val()
            };
        }
        else if (filter_name === 'change_date') {
            var fil_val_1 = $('#filter_value_1__change_date').val();
            if (fil_val_1.length) {
                filter_data = {
                    type: $('#filter_type__' + filter_name ).children('option:selected').val(),
                    value: ($('#filter_value_0__change_date').children('option:selected').val() + ':' + fil_val_1)
                };
            }
        }
        else if (filter_name === 'status') {
            var statuses = [];
            $('#filter_value__' + filter_name).find('input').each(function () {
                if ($(this).is(':checked')) {
                    statuses.push($(this).val());
                }
            });
            if (statuses.length > 0) {
                filter_data = {
                    type: 'list',
                    value: statuses
                }
            }
        }
        else if (filter_name === 'resource_component') {
            filter_value = $('#filter_value__' + filter_name).val();
            if (filter_value.length) {
                filter_data = {
                    type: $('#filter_type__' + filter_name ).children("option:selected").val(),
                    value: filter_value
                };
            }
        }
        else if (filter_name === 'problem_component') {
            filter_value = $('#filter_value__' + filter_name).val();
            if (filter_value.length) {
                filter_data = {
                    type: $('#filter_type__' + filter_name).children("option:selected").val(),
                    value: filter_value
                };
            }
        }
        else if (filter_name === 'problem_problem') {
            filter_value = $('#filter_value__' + filter_name).val();
            if (filter_value.length) {
                filter_data = {
                    type: $('#filter_type__' + filter_name).children("option:selected").val(),
                    value: filter_value
                };
            }
        }
        else if (filter_name === 'format') {
            filter_value = $('#filter_value__' + filter_name).val();
            if (filter_value.length) {
                filter_data = {
                    type: $('#filter_type__' + filter_name).val(),
                    value: filter_value
                };
            }
        }
        else if (filter_name === 'priority') {
            filter_data = {
                type: $('#filter_type__' + filter_name).val(),
                value: $('#filter_value__' + filter_name).val()
            };
        }
        else if (filter_name === 'finish_date') {
            filter_data = {
                type: $('#filter_type__' + filter_name ).children('option:selected').val(),
                value: ($('#filter_value_0__finish_date').children('option:selected').val() + ':' + $('#filter_value_1__finish_date').children('option:selected').val())
            };
        }
        if (filter_data) {
            filters[filter_name] = filter_data;
        }
    });
    return filters
}

function collect_filter_data () {
    return {view: JSON.stringify({
        columns: getColumns(),
        orders: getOrders(),
        filters: getFilters()
    })};
}


function compare_jobs() {
    var selected_jobs = [];
    $('input[id^="job_checkbox__"]:checked').each(function () {
        selected_jobs.push($(this).attr('id').replace('job_checkbox__', ''));
    });
    if (selected_jobs.length != 2) {
        err_notify($('#error__no_jobs_to_compare').text());
        return false;
    }
    $('#dimmer_of_page').addClass('active');
    $.post(
        job_ajax_url + 'check_compare_access/',
        {
            job1: selected_jobs[0],
            job2: selected_jobs[1]
        },
        function (data) {
            if (data.error) {
                $('#dimmer_of_page').removeClass('active');
                err_notify(data.error);
            }
            else {
                $.post(
                    '/reports/ajax/fill_compare_cache/',
                    {
                        job1: selected_jobs[0],
                        job2: selected_jobs[1]
                    },
                    function (data) {
                        $('#dimmer_of_page').removeClass('active');
                        if (data.error) {
                            err_notify(data.error);
                        }
                        else {
                            window.location.href = '/reports/comparison/' + selected_jobs[0] + '/' + selected_jobs[1] + '/';
                        }
                    },
                    'json'
                );
            }
        },
        'json'
    );
}

$(document).ready(function () {
    $('.ui.dropdown').dropdown();

    $('#remove_jobs_popup').modal({transition: 'fly up', autofocus: false, closable: false});
    $('#show_remove_jobs_popup').click(function () {
        $('#jobs_actions_menu').popup('hide');
        var jobs_for_delete = [], confirm_delete_btn = $('#delete_jobs_btn'),
            confirm_delete_modal = $('#remove_jobs_popup');
        $("input[id^='job_checkbox__']").each(function () {
            if ($(this).is(':checked')) {
                jobs_for_delete.push($(this).attr('id').replace('job_checkbox__', ''));
            }
        });
        if (jobs_for_delete.length == 0) {
            err_notify($('#error__no_jobs_to_delete').text());
            confirm_delete_modal.modal('hide');
        }
        else {
            confirm_delete_modal.modal('show');
            confirm_delete_btn.unbind();
            confirm_delete_btn.click(function () {
                $.post(
                    job_ajax_url + 'removejobs/',
                    {jobs: JSON.stringify(jobs_for_delete)},
                    function (data) {
                        confirm_delete_modal.modal('hide');
                        data.error ? err_notify(data.error) : window.location.replace('');
                    },
                    'json'
                );
            });
        }
    });

    inittree($('.tree'), 2, 'chevron down violet icon', 'chevron right violet icon', true);
    check_order_form();
    check_filters_form();
    fill_all_values();
    $("input[id^='job_checkbox__']").change(fill_checked_values);
    $("button[id^='remove__order__']").click(delete_selected_order);

    $("#add_order_btn").click(add_new_order);

    $('#add_column_btn').click(function () {
        var selected_column = $('#available_columns').children('option:selected');
        $('<option>', {
            value: selected_column.val(),
            text: selected_column.text(),
            title: selected_column.text()
        }).appendTo('#selected_columns');
        return false;
    });

    $('#remove_column_btn').click(function () {
        $('#selected_columns').children('option:selected').remove();
        return false;
    });

    var fullscreen_btn = $('#jobstree-fullscreen-btn');
    fullscreen_btn.popup();
    fullscreen_btn.click(function () {
        fullscreen_btn.popup('hide');
        var tree_1_bigpart = $('#jobstree-first-big-part');
        tree_1_bigpart.is(':visible') ? tree_1_bigpart.hide() : tree_1_bigpart.show();
        return false;
    });

    $('button[id^=remove__filter__]').click(remove_filter_form);

    $('#add_filter_btn').click(function () {
        var available_filters = $('#available_filters'),
            selected_filter = available_filters.children('option:selected'),
            filter_name = selected_filter.val();
        var filter_template = $('#filter_form_template__' + filter_name).html();
        var new_filter_element = $('<div>', {
            id: ("filter_form__" + filter_name)
        }).append(filter_template);
        new_filter_element.find('[id^="temp___"]').each(function () {
            $(this).attr('id', $(this).attr('id').replace('temp___', ''));
            if ($(this).attr('id') === ('filter_title__' + filter_name)) {
                $(this).text(selected_filter.text());
            }
        });
        new_filter_element.find('label[for^="temp___"]').each(function () {
            $(this).attr('for', $(this).attr('for').replace('temp___', ''));
        });
        $('#selected_filters_list').append(new_filter_element);
        $('#remove__filter__' + filter_name).click(remove_filter_form);
        selected_filter.remove();
        $('.filter-dropdown').dropdown();
        check_filters_form();
        return false;
    });

    $('#show_unsaved_view_btn').click(function () {
        $.redirectPost('', collect_filter_data());
    });

    $('#save_view_btn').click(function () {
        var view_title = $('#new_view_name_input').val();
        $.ajax({
            method: 'post',
            url: job_ajax_url + 'check_view_name/',
            dataType: 'json',
            data: {
                view_title: view_title,
                view_type: '1'
            },
            success: function(data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    var request_data = collect_filter_data();
                    request_data['title'] = view_title;
                    request_data['view_type'] = '1';
                    $.ajax({
                        method: 'post',
                        url: job_ajax_url + 'save_view/',
                        dataType: 'json',
                        data: request_data,
                        success: function(save_data) {
                            if (save_data.error) {
                                err_notify(data.error);
                            }
                            else {
                                $('#available_views').append($('<option>', {
                                    text: save_data['view_name'],
                                    value: save_data['view_id']
                                }));
                                $('#new_view_name_input').val('');
                                success_notify(save_data['message']);
                            }
                        }
                    });
                }
            }
        });
    });

    $('#update_view_btn').click(function () {
        var request_data = collect_filter_data();
        request_data['view_id'] = $('#available_views').children('option:selected').val();
        request_data['view_type'] = '1';
        $.ajax({
            method: 'post',
            url: job_ajax_url + 'save_view/',
            dataType: 'json',
            data: request_data,
            success: function(save_data) {
                save_data.error ? err_notify(save_data.error) : success_notify(save_data.message);
            }
        });
    });

    $('#show_view_btn').click(function () {
        $.redirectPost('', {view_id: $('#available_views').children('option:selected').val()});
    });

    $('#remove_view_btn').click(function () {
        $.ajax({
            method: 'post',
            url: job_ajax_url + 'remove_view/',
            dataType: 'json',
            data: {
                view_id: $('#available_views').children('option:selected').val(),
                view_type: '1'
            },
            success: function(data) {
                if (data.error) {
                    err_notify(data.error)
                }
                else {
                    $('#available_views').children('option:selected').remove();
                    success_notify(data.message)
                }
            }
        });
    });

    $('#share_view_btn').click(function () {
        $.ajax({
            method: 'post',
            url: job_ajax_url + 'share_view/',
            dataType: 'json',
            data: {
                view_id: $('#available_views').children('option:selected').val(),
                view_type: '1'
            },
            success: function(data) {
                if (data.error) {
                    err_notify(data.error)
                }
                else {
                    success_notify(data.message)
                }
            }
        });
    });

    $('#make_preferable_view_btn').click(function () {
        $.ajax({
            method: 'post',
            url: job_ajax_url + 'preferable_view/',
            dataType: 'json',
            data: {
                view_id: $('#available_views').children('option:selected').val(),
                view_type: '1'
            },
            success: function(data) {
                data.error ? err_notify(data.error) : success_notify(data.message);
            }
        });
    });

    $('#move_columns_up').click(function () {
        var $op = $('#selected_columns').children('option:selected');
        if ($op.length) {
            $op.first().prev().before($op);
        }
    });

    $('#move_columns_down').click(function () {
        var $op = $('#selected_columns').children('option:selected');
        if ($op.length) {
            $op.last().next().after($op);
        }
    });

    $('#cancel_remove_jobs').click(function () {
        $('#remove_jobs_popup').modal('hide');
    });

    $('#download_selected_jobs').click(function (event) {
        event.preventDefault();

        $('#jobs_actions_menu').popup('hide');
        var job_ids = [];
        $('input[id^="job_checkbox__"]:checked').each(function () {
            job_ids.push($(this).attr('id').replace('job_checkbox__', ''));
        });
        if (job_ids.length) {
            if (check_jobs_access(job_ids)) {
                $.redirectPost(job_ajax_url + 'downloadjobs/', {job_ids: JSON.stringify(job_ids)});
            }
        }
        else {
            err_notify($('#error__no_jobs_to_download').text());
        }
    });

    $('#compare_reports_btn').click(compare_jobs);
});
