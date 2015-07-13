$.getScript('/static/jobs/js/common.js');

//-------------
// FOR TABLE
//-------------
var do_not_count = "resource|format|version|type|identifier|parent_id|parent_name|date";

function fill_all_values() {
    $("td[id^='all__']").each(function() {
        var cell_id_data = $(this).attr('id').split('__');
        if (cell_id_data.length > 0) {
            cell_id_data.shift();
            var value_start = "td[id^='value__" + cell_id_data.join('__') + "__']";
            var sum = 0, have_numbers = false;
            $(value_start).each(function() {
                var num = parseInt($(this).html());
                if (isNaN(num) || cell_id_data[0].match(do_not_count)) {
                    num = 0;
                }
                else {
                    have_numbers = true
                }
                sum += num;
            });
            if (have_numbers == true) {
                $(this).html(sum);
            }
        }
    });
}

function fill_checked_values() {
    console.log('Entered!');
    $("td[id^='checked__']").each(function() {
        var cell_id_data = $(this).attr('id').split('__');
        if (cell_id_data.length > 0) {
            cell_id_data.shift();
            var value_start = "td[id^='value__" + cell_id_data.join('__') + "__']";
            var sum = 0, have_numbers = false, is_checked = false;
            $(value_start).each(function() {
                var row_id = $(this).attr('id').split('__').slice(-1)[0];
                if ($('#job_checkbox__' + row_id).is(':checked')) {
                    is_checked = true;
                    var num = parseInt($(this).html());
                    if (isNaN(num) || cell_id_data[0].match(do_not_count)) {
                        num = 0;
                    }
                    else {
                        have_numbers = true
                    }
                    sum += num;
                }
            });
            if (have_numbers == true && is_checked == true) {
                $(this).html(sum);
            }
            else {
                $(this).html('-');
            }
        }
    });
}

//-------------
// FOR FILTERS
//-------------
function add_order_to_available(value, title) {
    var sel = $('#available_orders');
    if (sel.children("option[value='" + value + "']").length == 0) {
        sel.append("<option value='" + value + "'>" + title + "</option>")
    }
    check_order_form()
}

function check_order_form() {
    if ($('#available_orders').children('option').length > 0) {
        $('#available_orders_form').show();
    }
    else {
        $('#available_orders_form').hide();
    }
}

function check_filters_form() {
    if ($('#available_filters').children('option').length > 0) {
        $('#available_filters_form').show();
    }
    else {
        $('#available_filters_form').hide();
    }
}

function delete_selected_order(form) {
    var order_value = form.attr('id').split('__').slice(-1)[0];
    var order_form_id = 'order__' + order_value;
    add_order_to_available(order_value, $('#selected_order_title__' + order_value).html());
    $('#' + order_form_id).remove();
}

function remove_filter_form(filter_form) {
    var filter_name = filter_form.attr('id').split('__').slice(-1)[0];
    var filter_title = $('#filter_title__' + filter_name).html();
    $('#available_filters').append($('<option>', {
        value: filter_name,
        text: filter_title
    }));
    $('#filter_form__' + filter_name).remove();
    check_filters_form();
    return false;
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
        var order_dir = $(this).find('input:checked').val();
        if (order_dir == 'up') {
            order_name = '-' + order_name;
        }
        orders.push(order_name);
    });
    return orders
}

function getFilters() {
    var filters = {};
    $('#selected_filters_list').children().each(function () {
        var filter_name = $(this).attr('id').replace('filter_form__', '');
        var filter_data;
        if (filter_name == 'name') {
            filter_data = {
                type: $('#filter_type__' + filter_name ).children("option:selected").val(),
                value: $('#filter_value__' + filter_name).val()
            };
        }
        else if (filter_name == 'change_author') {
            filter_data = {
                type: $('#filter_type__' + filter_name ).val(),
                value: $('#filter_value__' + filter_name).children("option:selected").val()
            };
        }
        else if (filter_name == 'change_date') {
            var fil_val_0 = $('#filter_value_0__change_date').children('option:selected').val(),
                fil_val_1 = $('#filter_value_1__change_date').val();
            filter_data = {
                type: $('#filter_type__' + filter_name ).children('option:selected').val(),
                value: (fil_val_0 + ':' + fil_val_1)
            };
        }
        else if (filter_name == 'status') {
            filter_data = {
                type: $('#filter_type__' + filter_name ).children("option:selected").val(),
                value: $('#filter_value__' + filter_name).children("option:selected").val()
            };
        }
        else if (filter_name == 'resource_component') {
            filter_data = {
                type: $('#filter_type__' + filter_name ).children("option:selected").val(),
                value: $('#filter_value__' + filter_name).val()
            };
        }
        else if (filter_name == 'problem_component') {
            filter_data = {
                type: $('#filter_type__' + filter_name ).children("option:selected").val(),
                value: $('#filter_value__' + filter_name).val()
            };
        }
        else if (filter_name == 'problem_problem') {
            filter_data = {
                type: $('#filter_type__' + filter_name ).children("option:selected").val(),
                value: $('#filter_value__' + filter_name).val()
            };
        }
        else if (filter_name == 'format') {
            filter_data = {
                type: $('#filter_type__' + filter_name ).val(),
                value: $('#filter_value__' + filter_name).val()
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

$(document).ready(function () {

    var ajax_url = window.location.href + 'ajax/',
        available_orders = $('#available_orders');
    check_order_form();
    check_filters_form();
    if($('#jobtable').length) {
        $.post(
            '/jobs/jobtable/',
            collect_filter_data(),
            function(data) {
                $('#jobtable').html(data);
                fill_all_values();
                $("input[id^='job_checkbox__']").change(fill_checked_values);
                $('.tree').treegrid({
                    treeColumn: 1,
                    expanderExpandedClass: 'treegrid-span-obj glyphicon glyphicon-chevron-down',
                    expanderCollapsedClass: 'treegrid-span-obj glyphicon glyphicon-chevron-right'
                });
            }
        );
    }

    $("button[id^='remove__order__']").click(function () {
        delete_selected_order($(this));
        return false;
    });

    $("#add_order_btn").click(function() {
        var selected_order = available_orders.children('option:selected');
        if (selected_order.length == 1) {
            var sel_title = selected_order.html();
            var sel_value = selected_order.val();
            var selected_orders_div = $('#all_selected_orders');
            if (selected_orders_div.find('div[id=order__' + sel_value + ']').length > 0) {
                return false;
            }
            selected_orders_div.append($('#selected_order_template').html());

            var new_item = selected_orders_div.find('div[id=order__]');
            new_item.attr('id', 'order__' + sel_value);

            var span_obj = new_item.find('span[id=selected_order_title__]');
            span_obj.attr('id', 'selected_order_title__' + sel_value);
            span_obj.html(sel_title);

            var new_button = new_item.find('button[id=remove__order__]');
            new_button.attr('id', 'remove__order__' + sel_value);
            new_button.click(function () {
                delete_selected_order($(this));
            });
            new_item.find('input').attr('name', sel_value);
            available_orders.children('option[value=' + sel_value + ']').remove();
            check_order_form();
        }
        return false;
    });

    $('#add_column_btn').click(function () {
        var selected_column = $('#available_columns').children('option:selected');
        $('#selected_columns').append($('<option>', {
            value: selected_column.val(),
            text: selected_column.html(),
            title: selected_column.html()
        }));
        return false;
    });

    $('#remove_column_btn').click(function () {
        $('#selected_columns').children('option:selected').remove();
        return false;
    });

    $('#jobstree-fullscreen-btn').click(function () {
        var tree_1_bigpart = $('#jobstree-first-big-part');
        if (tree_1_bigpart.is(':visible')) {
            tree_1_bigpart.hide();
            $(this).find('span').attr('class', "glyphicon glyphicon-save")
        }
        else {
            tree_1_bigpart.show();
            $(this).find('span').attr('class', "glyphicon glyphicon-fullscreen")
        }
        return false;
    });

    $('button[id^=remove__filter__]').click(function () {
        remove_filter_form($(this));
        return false;
    });

    $('#add_filter_btn').click(function () {
        var selected_filter = $('#available_filters').children('option:selected');
        var filter_name = selected_filter.val(),
            filter_title = selected_filter.html(),
            global_filter_list = $('#selected_filters_list');
        var filter_template = $('#filter_form_template__' + filter_name).html();
        var new_filter_element = $('<li>', {
            class: "list-group-item",
            id: ("filter_form__" + filter_name)
        }).append(filter_template);
        new_filter_element.find('[id^="temp___"]').each(function () {
            var new_id = $(this).attr('id').replace('temp___', '');
            $(this).attr('id', new_id);
            if ($(this).attr('id') == ('filter_title__' + filter_name)) {
                $(this).html(filter_title);
            }
        });
        global_filter_list.append(new_filter_element);
        $('#remove__filter__' + filter_name).click(function () {
            remove_filter_form($(this));
            return false;
        });
        selected_filter.remove();
        check_filters_form();
        return false;
    });

    // On click button "Show selected" we are making post request to the same page
    $('#show_unsaved_view_btn').click(function () {
        $.redirectPost('', collect_filter_data());
    });

    // On click to the "Save" view button we are saving it and reloading page
    $('#save_view_btn').click(function () {
        var view_title = $('#new_view_name_input').val();
        var reserved_titles = [];
        $('#available_views').children('option').each(function () {
            reserved_titles.push($(this).html());
        });
        if (reserved_titles.indexOf(view_title) > -1) {
            $.notify("Please choose another view name.", {
                autoHide: true,
                autoHideDelay: 1500,
                style: 'bootstrap',
                className: 'error'
            });
            return false;
        }
        if (view_title.length == 0) {
            $.notify("View name is required.", {
                autoHide: true,
                autoHideDelay: 1500,
                style: 'bootstrap',
                className: 'error'
            });
            return false;
        }
        var request_data = collect_filter_data();
        request_data['title'] = view_title;
        $.ajax({
            method: 'post',
            url: ajax_url + 'save_view/',
            dataType: 'json',
            data: request_data,
            success: function() {
                window.location.replace('')
            }
        });
    });

    // On click to the "Show" view button we are changing preferable view and reloading page
    $('#show_view_btn').click(function () {
        var view_id = $('#available_views').children('option:selected').val();
        $.ajax({
            method: 'post',
            url: ajax_url + 'change_preferable/',
            dataType: 'json',
            data: {view_id: view_id},
            success: function() {
                window.location.replace('')
            }
        });
    });

    // On click to the "Remove" view button we are removing preferable view,
    // needed view and then reloading page
    $('#remove_view_btn').click(function () {
        var view_id = $('#available_views').children('option:selected').val();
        $.ajax({
            method: 'post',
            url: ajax_url + 'remove_view/',
            dataType: 'json',
            data: {view_id: view_id},
            success: function() {
                window.location.replace('')
            }
        });
    });
});
