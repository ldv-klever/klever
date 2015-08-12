function set_actions_for_attr_filters() {
    function collect_attr_data() {
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

        return {
            view: JSON.stringify({
                filters: filter_values
            }),
            view_type: '3'
        };
    }

    $('#attrview_show_unsaved_view_btn').click(function () {
        $.redirectPost('', collect_attr_data());
    });

    $('#attrview_save_view_btn').click(function () {
        var view_title = $('#attrview_view_name_input').val();
        $.ajax({
            method: 'post',
            url: job_ajax_url + 'check_view_name/',
            dataType: 'json',
            data: {
                view_title: view_title,
                view_type: '3'
            },
            success: function(data) {
                if (data.status) {
                    var request_data = collect_attr_data();
                    request_data['title'] = view_title;
                    request_data['view_type'] = '3';
                    $.ajax({
                        method: 'post',
                        url: job_ajax_url + 'save_view/',
                        dataType: 'json',
                        data: request_data,
                        success: function(save_data) {
                            if (save_data.status === 0) {
                                $('#attrview_available_views').append($('<option>', {
                                    text: save_data.view_name,
                                    value: save_data.view_id
                                }));
                                $('#attrview_view_name_input').val('');
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

    $('#attrview_update_view_btn').click(function () {
        var request_data = collect_attr_data();
        request_data['view_id'] = $('#attrview_available_views').children('option:selected').val();
        request_data['view_type'] = '3';
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

    $('#attrview_show_view_btn').click(function () {
        $.redirectPost('', {
            view_id: $('#attrview_available_views').children('option:selected').val(),
            view_type: '3'
        });
    });

    $('#attrview_remove_view_btn').click(function () {
        $.ajax({
            method: 'post',
            url: job_ajax_url + 'remove_view/',
            dataType: 'json',
            data: {
                view_id: $('#attrview_available_views').children('option:selected').val(),
                view_type: '3'
            },
            success: function(data) {
                if (data.status === 0) {
                    $('#attrview_available_views').children('option:selected').remove();
                    success_notify(data.message)
                }
                else {
                    err_notify(data.message)
                }
            }
        });
    });

    $('#attrview_make_preferable_view_btn').click(function () {
        $.ajax({
            method: 'post',
            url: job_ajax_url + 'preferable_view/',
            dataType: 'json',
            data: {
                view_id: $('#attrview_available_views').children('option:selected').val(),
                view_type: '3'
            },
            success: function(data) {
                data.status === 0 ? success_notify(data.message) : err_notify(data.message);
            }
        });
    });
}

$(document).ready(function () {
    set_actions_for_view_filters();
    if ($('#accordion-attrs').length) {
        set_actions_for_attr_filters();
    }
    return false;
});
