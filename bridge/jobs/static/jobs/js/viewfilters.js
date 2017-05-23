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

window.collect_jobview_data = function() {
    var data_values = [], filter_values = {},
        available_data = [
            'unsafes', 'safes', 'unknowns', 'resources', 'tags_safe', 'tags_unsafe',
            'unsafes_attr_stat', 'safes_attr_stat', 'unknowns_attr_stat'
        ],
        available_filter_checkboxes = ['unknowns_total', 'unknowns_nomark', 'resource_total'],
        available_filters = ['unknown_component', 'unknown_problem', 'resource_component', 'safe_tag', 'unsafe_tag', 'stat_attr_name'];

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
};

$(document).ready(function () {
    set_actions_for_views('2', collect_jobview_data);
});
