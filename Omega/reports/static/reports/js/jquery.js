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
    view_values['columns'] = [];
    $("input[type=checkbox][id^='show_mark_'][value^='mark_']").each(function () {
        if ($(this).is(':checked')) {
            view_values['columns'].push($(this).val());
        }
    });
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

function set_action_on_log_click() {

}

$(document).ready(function () {
    var data_collection;
    $('input[class=buttons-view-type]').each(function () {
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

    $('#show_component_log').click(function () {
        var file_div = $('#file_content_div');
        if (file_div.length) {
            $.ajax({
                url: '/reports/logcontent/' + $('#report_pk').val() + '/',
                type: 'GET',
                success: function (data) {
                    $('#file_content_div').find('div').text(data);
                    file_div.show();
                    $('body').addClass("file-view");
                    $('#close_file_view').click(function () {
                        $('body').removeClass("file-view");
                        $('#file_content_div').find('div').empty();
                        file_div.hide();
                    });
                }
            });
        }
    });
});

