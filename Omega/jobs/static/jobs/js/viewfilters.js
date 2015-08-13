$(document).ready(function () {
    function collect_view_data() {
        var data_values = [], filter_values = {},
            available_data = ['unsafes', 'safes', 'unknowns', 'resources', 'tags_safe', 'tags_unsafe'],
            available_filter_checkboxes = ['unknowns_total', 'unknowns_nomark', 'resource_total'],
            available_filters = ['unknown_component', 'unknown_problem', 'resource_component', 'safe_tag', 'unsafe_tag'];

        $("input[id^='job_filter_checkbox__']").each(function () {
            var curr_name = $(this).attr('id').replace('job_filter_checkbox__', '');
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
        return JSON.stringify({
            data: data_values,
            filters: filter_values
        });
    }
    set_actions_for_views('2', collect_view_data);
    if (!$('#resource_title_span').length) {
        $('#resource_star_div').hide();
    }
});
