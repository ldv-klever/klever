var do_not_count = ['resource', 'format', 'version', 'type', 'identifier',
    'parent_id', 'name', 'author', 'date', 'status'];

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
        new_item.find('input').attr('name', sel_value);
        available_orders.children('option[value=' + sel_value + ']').remove();
        check_order_form();
    }
    return false;
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
    var filters_form = $('#available_filters_form');
    $('#available_filters').children('option').length ? filters_form.show() : filters_form.hide();
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
            status = res.status;
            if (!status) {
                err_notify(res.message);
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
            filter_data = {
                type: $('#filter_type__' + filter_name ).children("option:selected").val(),
                value: $('#filter_value__' + filter_name).children("option:selected").val()
            };
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
    var max_table_height = $(window).height() - 100,
        small_table_height = $(window).height() - 300;
    $('.tree').treegrid({
        treeColumn: 1,
        expanderExpandedClass: 'treegrid-span-obj glyphicon glyphicon-chevron-down',
        expanderCollapsedClass: 'treegrid-span-obj glyphicon glyphicon-chevron-right'
    });
    $('#jobtable').attr('style', 'max-height: ' + small_table_height + 'px;');
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

    $('#jobstree-fullscreen-btn').click(function () {
        var tree_1_bigpart = $('#jobstree-first-big-part');
        if (tree_1_bigpart.is(':visible')) {
            tree_1_bigpart.hide();
            $(this).find('span').attr('class', "glyphicon glyphicon-save");
            $('#jobtable').attr('style', 'max-height: ' + max_table_height + 'px;')
        }
        else {
            tree_1_bigpart.show();
            $(this).find('span').attr('class', "glyphicon glyphicon-fullscreen");
            $('#jobtable').attr('style', 'max-height: ' + small_table_height + 'px;')
        }
        return false;
    });

    $('button[id^=remove__filter__]').click(remove_filter_form);

    $('#add_filter_btn').click(function () {
        var selected_filter = $('#available_filters').children('option:selected'),
            filter_name = selected_filter.val();
        var filter_template = $('#filter_form_template__' + filter_name).html();
        var new_filter_element = $('<li>', {
            "class": "list-group-item",
            id: ("filter_form__" + filter_name)
        }).append(filter_template);
        new_filter_element.find('[id^="temp___"]').each(function () {
            // var new_id = $(this).attr('id').replace('temp___', '');
            $(this).attr('id', $(this).attr('id').replace('temp___', ''));
            if ($(this).attr('id') === ('filter_title__' + filter_name)) {
                $(this).html(selected_filter.html());
            }
        });
        $('#selected_filters_list').append(new_filter_element);
        $('#remove__filter__' + filter_name).click(remove_filter_form);
        selected_filter.remove();
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
                if (data.status) {
                    var request_data = collect_filter_data();
                    request_data['title'] = view_title;
                    request_data['view_type'] = '1';
                    $.ajax({
                        method: 'post',
                        url: job_ajax_url + 'save_view/',
                        dataType: 'json',
                        data: request_data,
                        success: function(save_data) {
                            if (save_data.status === 0) {
                                $('#available_views').append($('<option>', {
                                    text: save_data.view_name,
                                    value: save_data.view_id
                                }));
                                $('#new_view_name_input').val('');
                                success_notify(save_data.message);
                            }
                            else {
                                err_notify(data.message);
                            }
                        }
                    });
                }
                else {
                    err_notify(data.message);
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
                save_data.status === 0 ? success_notify(save_data.message) : err_notify(save_data.message);
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
                if (data.status === 0) {
                    $('#available_views').children('option:selected').remove();
                    success_notify(data.message)
                }
                else {
                    err_notify(data.message)
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
                data.status === 0 ? success_notify(data.message) : err_notify(data.message);
            }
        });
    });

    $('#delete_jobs_btn').click(function () {
        var jobs_for_delete = [];
        $("input[id^='job_checkbox__']").each(function () {
            if ($(this).is(':checked')) {
                jobs_for_delete.push($(this).attr('id').replace('job_checkbox__', ''));
            }
        });
        if (jobs_for_delete.length == 0) {
            err_notify($('#error__no_jobs_to_delete').text());
        }
        if (jobs_for_delete.length) {
            $.post(
                job_ajax_url + 'removejobs/',
                {jobs: JSON.stringify(jobs_for_delete)},
                function (data) {
                    data.status === 0 ? window.location.replace('') : err_notify(data.message);
                },
                'json'
            );
        }
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

    $('#download_selected_jobs').click(function () {
        var job_ids = [];
        $('input[id^="job_checkbox__"]:checked').each(function () {
            job_ids.push($(this).attr('id').replace('job_checkbox__', ''));
        });
        if (job_ids.length) {
            if (check_jobs_access(job_ids)) {
                for (var i = 0; i < job_ids.length; i++) {
                    download_job(job_ids[i]);
                }
            }
        }
        else {
            err_notify($('#error__no_jobs_to_download').text());
        }
    });

    $('#upload_job_file_input').on('fileselect', function () {
        var files = $(this)[0].files,
            filename_list = $('<ul>');
        for (var i = 0; i < files.length; i++) {
            filename_list.append($('<li>', {text: files[i].name}));
        }
        $('#upload_job_filename').html(filename_list);
    });

    $('#upload_job_cancel').click(function () {
        var file_input = $('#upload_job_file_input');
        file_input.replaceWith(file_input.clone( true ));
        $('#upload_job_parent_id').val('');
        $('#upload_job_filename').empty();
    });

    $('#upload_jobs_start').click(function () {
        var parent_id = $('#upload_job_parent_id').val();
        if (parent_id.length === 0) {
            err_notify($('#error__parent_required').text());
            return false;
        }
        var files = $('#upload_job_file_input')[0].files,
            data = new FormData();
        for (var i = 0; i < files.length; i++) {
            data.append('file', files[i]);
        }
        $.ajax({
            url: job_ajax_url + 'upload_job/' + encodeURIComponent(parent_id) + '/',
            type: 'POST',
            data: data,
            dataType: 'json',
            contentType: false,
            processData: false,
            mimeType: 'multipart/form-data',
            async: false,
            xhr: function() {
                return $.ajaxSettings.xhr();
            },
            success: function (data) {
                if (data.status) {
                    window.location.replace('')
                }
                else {
                    if (data.messages) {
                        for (var i = 0; i < data.messages.length; i++) {
                            var err_message = data.messages[i][0] + ' (' + data.messages[i][1] + ')';
                            err_notify(err_message, 10000);
                        }
                    }
                    else {
                        err_notify(data.message);
                    }
                }
            }
        });
    });

    $('#upload_marks_start').click(function () {
        $('body').addClass("loading");
        $('#upload_marks_popup').toggle();
        var files = $('#upload_marks_file_input')[0].files,
            data = new FormData();
        for (var i = 0; i < files.length; i++) {
            data.append('file', files[i]);
        }
        $.ajax({
            url: marks_ajax_url + 'upload_marks/',
            type: 'POST',
            data: data,
            dataType: 'json',
            contentType: false,
            processData: false,
            mimeType: 'multipart/form-data',
            // async: false,
            xhr: function() {
                return $.ajaxSettings.xhr();
            },
            success: function (data) {
                $('body').removeClass("loading");
                if (data.status) {
                    if (data.mark_id.length && data.mark_type.length) {
                        window.location.replace("/marks/" + data.mark_type + "/edit/" + data.mark_id + "/")
                    }
                }
                else {
                    if (data.messages && data.messages.length) {
                        for (var i = 0; i < data.messages.length; i++) {
                            var err_message = data.messages[i][0] + ' (' + data.messages[i][1] + ')';
                            err_notify(err_message, 10000);
                        }
                    }
                    else if (data.message && data.message.length) {
                        err_notify(data.message);
                    }
                }
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });

    $('#upload_marks_cancel').click(function () {
        var file_input = $('#upload_marks_file_input');
        file_input.replaceWith(file_input.clone( true ));
        $('#upload_marks_filename').empty();
    });

    $('#upload_marks_file_input').on('fileselect', function () {
        console.log($(this).attr('id'));
        var files = $(this)[0].files,
            filename_list = $('<ul>');
        for (var i = 0; i < files.length; i++) {
            filename_list.append($('<li>', {text: files[i].name}));
        }
        $('#upload_marks_filename').html(filename_list);
    });

});
