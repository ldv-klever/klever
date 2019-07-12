/*
 * Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

function collect_attrs_data() {
    let attrs = [];
    $('#inline_mark_attrs').find('span').each(function () {
        attrs.push({
            name: $(this).data('name'),
            value: $(this).data('value'),
            is_compare: $(this).data('compare')
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

function collect_markdata(action, mark_type) {
    let mark_data = {
        is_modifiable: true,
        description: get_description(),
        attrs: collect_attrs_data(),
        comment: $('#inline_mark_comment').val()
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
        if (mark_type === 'unsafe') {
            mark_data['status'] = $("input[name='selected_status']:checked").val();
            mark_data['function'] = $("#compare_function").val();
            mark_data['threshold'] = $("#threshold").val();
        }
    }
    return mark_data;
}

window.get_inline_mark_form = function(url, container) {
    $.get(url, {}, function (resp) {
        container.html(resp);
        activate_tags();
        container.find('.ui.checkbox').checkbox();
        container.show();
        $('#close_inline_mark_form').click(function () {
            container.hide().empty()
        });
        $('#save_inline_mark_btn').click(function () {
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
                    $('#dimmer_of_page').removeClass('active');
                }
            });
        });

        let verdict_column = container.find('#verdict_column'),
            status_div = container.find('#status_column');
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
};

