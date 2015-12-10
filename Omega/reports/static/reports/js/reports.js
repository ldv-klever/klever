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

    return JSON.stringify({filters: filter_values});
}

function unsafe_filters_data() {
    var view_values = {}, filter_values = {};
    var order = $('#filter__attr__order').val();
    if (order.length > 0) {
        view_values['order'] = order;
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
        view_values['order'] = order;
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
    $('#component_name_tr').popup({popup: $('#timeinfo_popup'), position: 'right center'});
    $('#computer_description_tr').popup({popup: $('#computer_info_popup'), position: 'right center'});
    $('.parent-popup').popup({inline:true});
    $('.ui.dropdown').dropdown();

    /*var report_list = $('#report_list_table').find('tbody').children();
    if (report_list.length == 1) {
        window.location.replace(report_list.find('a').first().attr('href'));
    }*/

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
});

