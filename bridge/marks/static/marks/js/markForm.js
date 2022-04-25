/*
 * Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
 * Ivannikov Institute for System Programming of the Russian Academy of Sciences
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

// function encodeData(s) {
//     return encodeURIComponent(s).replace(/\-/g, "%2D").replace(/\_/g, "%5F").replace(/\./g, "%2E").replace(/\!/g, "%21").replace(/\~/g, "%7E").replace(/\*/g, "%2A").replace(/\'/g, "%27").replace(/\(/g, "%28").replace(/\)/g, "%29");
// }

function collect_attrs_data() {
    let attrs = [];
    $("input[id^='attr_checkbox__']").each(function () {
        attrs.push({
            name: $(this).data('name'),
            value: $(this).data('value'),
            is_compare: $(this).is(':checked')
        })
    });
    return attrs;
}

function get_description() {
    let tmp_div = $('<div>').html($('#mark_description').val());
    tmp_div.find('script').remove();
    tmp_div.find('*').each(function () {
        let element_in_div = $(this);
        $.each($(this)[0].attributes, function (i, attr) {
            if (attr.name.match("^on")) element_in_div.removeAttr(attr.name)
        });
    });
    return tmp_div.html();
}

function is_modifiable() {
    let is_modifiable_checkbox = $('#is_modifiable');
    return (!is_modifiable_checkbox.length || is_modifiable_checkbox.is(':checked'));
}

function collect_markdata(action, mark_type) {
    let mark_data = {
        is_modifiable: is_modifiable(),
        description: get_description(),
        attrs: collect_attrs_data(),
        comment: $('#mark_comment').val()
    };
    if (action === 'create') mark_data['report_id'] = $('#report_id').val();

    if (mark_type === 'unknown') {
        mark_data['problem_pattern'] = $('#unknown_problem_pattern').val();
        mark_data['function'] = $('#unknown_function').val();
        mark_data['is_regexp'] = $('#is_regexp').is(':checked');
        mark_data['link'] = $('#unknown_link').val();
    }
    else {
        mark_data['verdict'] = $("input[name='selected_verdict']:checked").val();
        mark_data['tags'] = get_tags_values();
    }
    if (mark_type === 'unsafe') {
        mark_data['status'] = $("input[name='selected_status']:checked").val();
        mark_data['threshold'] = $('#threshold').val();

        if (action === 'edit') {
            const traceInput = $('#mark_error_trace');
            if (traceInput.length) {
                mark_data['error_trace'] = traceInput.val();
            } else {
                mark_data['regexp'] = $('#mark_regexp').val();
            }
        } else {
            const selectedFunction = $("#compare_name").val();
            mark_data['function'] = selectedFunction;
            const isRegexp = parseInt($('#unsafe_functions')
                .find(`.compare-func[data-name="${selectedFunction}"]`)
                .find('.compare-regexp').val());
            if (isRegexp) {
                mark_data['regexp'] = $('#mark_regexp').val();
            }
        }
    }

    return mark_data;
}

function test_unknown_function() {
    let func = $('#unknown_function').val();
    if (func.length <= 0) {
        err_notify($('#error__function_required').text());
        return false;
    }
    $.post(
        $(this).data('url'),
        {
            function: func,
            pattern: $('#unknown_problem_pattern').val(),
            is_regex: $('#is_regexp').is(':checked')
        },
        function (data) {
            if (data.error) {
                err_notify(data.error);
                $('#test_mark_nomatch_div').hide();
                $('#test_mark_result_div').hide();
            }
            else {
                if (data['matched'] === 1) {
                    $('#test_mark_nomatch_div').hide();
                    $('#test_mark_problem').text(data['problem']);
                    $('#test_mark_result').text(data['result']);
                    $('#test_mark_result_div').show();
                }
                else {
                    $('#test_mark_result_div').hide();
                    $('#test_mark_nomatch_div').show();
                    if (data['result'].length > 0) {
                        $('#regexp_err_result').text(data['result']).show();
                    }
                    else {
                        $('#regexp_err_result').text('').hide();
                    }
                }
            }
        }
    );
}

$(document).ready(function () {
    activate_tags();
    $('.ui.dropdown').each(function () { if (!$(this).hasClass('search')) $(this).dropdown() });
    $('#test_unknown_mark').click(test_unknown_function);

    $('#save_mark_btn').click(function () {
        $(this).addClass('disabled');
        $('#dimmer_of_page').addClass('active');

        $.ajax({
            url: $(this).data('url'),
            method: $(this).data('method'),
            data: JSON.stringify(collect_markdata($(this).data('action'), $(this).data('type'))),
            dataType: "json",
            contentType: 'application/json; charset=utf-8',
            traditional: true,
            success: function (resp) {
                window.location.replace(resp['url']);
            },
            error: function () {
                $('#save_mark_btn').removeClass('disabled')
            }
        });
    });

    $('#mark_version_selector').change(function () {
        window.location.replace(get_url_with_get_parameters(window.location.href, {'version': $(this).val()}));
    });

    $('#compare_name').change(function () {
        let selected_compare = $(this).children('option:selected').val(),
            data_container = $('#unsafe_functions').find('.compare-func[data-name="' + selected_compare + '"]');
        $('#compare_desc').text(data_container.find('.compare-desc').text());
        $('#convert_desc').text(data_container.find('.convert-desc').text());
        $('#convert_name').text(data_container.find('.convert-desc').data('name'));

        const isRegexp = parseInt(data_container.find('.compare-regexp').val());
        if (isRegexp) {
            $('#unsafe_regexp_segment').show();
        } else {
            $('#unsafe_regexp_segment').hide();
        }
    });

    let verdict_column = $('#verdict_column'), status_div = $('#status_column');
    if (verdict_column.length && status_div.length) {
        verdict_column.find('input').change(function () {
            if ($(this).is(':checked')) {
                // verdict is "Bug"
                if ($(this).val() === '1') {
                    status_div.show();
                    status_div.find("input:radio[name=selected_status]:first").prop('checked', true);
                }
                else {
                    status_div.find("input:radio[name=selected_status]:checked").prop('checked', false);
                    status_div.hide();
                }
            }
        })
    }
});
