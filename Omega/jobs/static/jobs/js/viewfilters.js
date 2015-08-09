function collect_view_data() {
    var data_values = [], filter_values = {},
        available_data = ['unsafes', 'safes', 'unknowns', 'resources', 'tags_safe', 'tags_unsafe'],
        available_filter_checkboxes = ['unknowns_total', 'unknowns_nomark', 'resource_total'],
        available_filters = ['unknown_component', 'unknown_problem', 'resource_component', 'safe_tag', 'unsafe_tag'];

    $("input[id^='checkbox__']").each(function () {
        var curr_name = $(this).attr('id').replace('checkbox__', '');
        if ($(this).is(':checked')) {
            if ($.inArray(curr_name, available_data) !== -1) {
                data_values.push(curr_name);
            }
            else if ($.inArray(curr_name, available_filter_checkboxes) !== -1) {
                filter_values[curr_name] = {
                    type: 'hide'
                };
            }
        }
    });
    $.each(available_filters, function (index, value) {
        var filter_type = $('#filter__type__' + value),
            filter_value = $('#filter__value__' + value);
        if (filter_value.val().length > 0) {
            filter_values[value] = {
                type: filter_type.val(),
                value: filter_value.val()
            };
        }
    });

    return {view: JSON.stringify({
        data: data_values,
        filters: filter_values
    })};
}


$(document).ready(function () {

    $('#jobview_show_unsaved_view_btn').click(function () {
        $.redirectPost('', collect_view_data());
    });

    $('#jobview_save_view_btn').click(function () {
        var view_title = $('#jobview_view_name_input').val();
        $.ajax({
            method: 'post',
            url: job_ajax_url + 'check_view_name/',
            dataType: 'json',
            data: {
                view_title: view_title,
                view_type: '2'
            },
            success: function(data) {
                if (data.status) {
                    var request_data = collect_view_data();
                    request_data['title'] = view_title;
                    request_data['view_type'] = '2';
                    $.ajax({
                        method: 'post',
                        url: job_ajax_url + 'save_view/',
                        dataType: 'json',
                        data: request_data,
                        success: function(save_data) {
                            if (save_data.status === 0) {
                                $('#jobview_available_views').append($('<option>', {
                                    text: save_data.view_name,
                                    value: save_data.view_id
                                }));
                                $('#jobview_view_name_input').val('');
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

    $('#jobview_update_view_btn').click(function () {
        var request_data = collect_view_data();
        request_data['view_id'] = $('#jobview_available_views').children('option:selected').val();
        request_data['view_type'] = '2';
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

    $('#jobview_show_view_btn').click(function () {
        $.redirectPost('', {view_id: $('#jobview_available_views').children('option:selected').val()});
    });

    $('#jobview_remove_view_btn').click(function () {
        $.ajax({
            method: 'post',
            url: job_ajax_url + 'remove_view/',
            dataType: 'json',
            data: {
                view_id: $('#jobview_available_views').children('option:selected').val(),
                view_type: '2'
            },
            success: function(data) {
                if (data.status === 0) {
                    $('#jobview_available_views').children('option:selected').remove();
                    success_notify(data.message)
                }
                else {
                    err_notify(data.message)
                }
            }
        });
    });

    $('#jobview_make_preferable_view_btn').click(function () {
        $.ajax({
            method: 'post',
            url: job_ajax_url + 'preferable_view/',
            dataType: 'json',
            data: {
                view_id: $('#jobview_available_views').children('option:selected').val(),
                view_type: '2'
            },
            success: function(data) {
                data.status === 0 ? success_notify(data.message) : err_notify(data.message);
            }
        });
    });
});