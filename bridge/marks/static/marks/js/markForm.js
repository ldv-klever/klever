function encodeData(s) {
    return encodeURIComponent(s).replace(/\-/g, "%2D").replace(/\_/g, "%5F").replace(/\./g, "%2E").replace(/\!/g, "%21").replace(/\~/g, "%7E").replace(/\*/g, "%2A").replace(/\'/g, "%27").replace(/\(/g, "%28").replace(/\)/g, "%29");
}

function collect_attrs_data() {
    var attrs = [];
    $("input[id^='attr_checkbox__']").each(function () {
        var attr = {
            attr: $(this).val(),
            is_compare: false
        };
        if ($(this).is(':checked')) {
            attr['is_compare'] = true;
        }
        attrs.push(attr);
    });
    return attrs;
}


window.collect_new_markdata = function() {
    var is_modifiable_checkbox = $('#is_modifiable'), is_modifiable = true,
        mark_type = $('#report_type').val(), mark_data,
        description = $('#mark_description').val();

    var tmp_div = $('<div>').html(description);
    tmp_div.find('script').remove();
    tmp_div.find('*').each(function () {
        var element_in_div = $(this);
        $.each($(this)[0].attributes, function (i, attr) {
            if (attr.name.match("^on")) {
                element_in_div.removeAttr(attr.name)
            }
        });
    });
    description = tmp_div.html();

    if (is_modifiable_checkbox.length) {
        is_modifiable = is_modifiable_checkbox.is(':checked');
    }

    if (mark_type === 'unknown') {
        var unknown_function = $('#unknown_function').val(),
            unknown_problem_pattern = $('#unknown_problem_pattern').val();
        if (unknown_function.length <= 0) {
            err_notify($('#error__function_required').text());
        }
        if (unknown_problem_pattern.length <= 0) {
            err_notify($('#error__problem_required').text());
        }
        mark_data = {
            report_id: $('#report_pk').val(),
            status: $("input[name='selected_status']:checked").val(),
            data_type: mark_type,
            is_modifiable: is_modifiable,
            problem: unknown_problem_pattern,
            function: unknown_function,
            is_regexp: $('#is_regexp').is(':checked'),
            link: $('#unknown_link').val(),
            description: description
        };
    }
    else {
        mark_data = {
            attrs: collect_attrs_data(),
            report_id: $('#report_pk').val(),
            verdict: $("input[name='selected_verdict']:checked").val(),
            status: $("input[name='selected_status']:checked").val(),
            data_type: mark_type,
            is_modifiable: is_modifiable,
            tags: get_tags_values(),
            description: description
        };
    }

    if (mark_type === 'unsafe') {
        mark_data['compare_id'] = $("#compare_function").val();
    }

    return encodeData(JSON.stringify(mark_data));
};


window.collect_markdata = function() {
    var is_modifiable_checkbox = $('#is_modifiable'), is_modifiable = true,
        mark_type = $('#mark_type').val(), mark_data, description = $('#mark_description').val();

    var tmp_div = $('<div>').html(description);
    tmp_div.find('script').remove();
    tmp_div.find('*').each(function () {
        var element_in_div = $(this);
        $.each($(this)[0].attributes, function (i, attr) {
            if (attr.name.match("^on")) {
                element_in_div.removeAttr(attr.name)
            }
        });
    });
    description = tmp_div.html();

    if (is_modifiable_checkbox.length) {
        is_modifiable = is_modifiable_checkbox.is(':checked');
    }

    if (mark_type === 'unknown') {
        var unknown_function = $('#unknown_function').val(),
            unknown_problem_pattern = $('#unknown_problem_pattern').val();
        if (unknown_function.length <= 0) {
            err_notify($('#error__function_required').text());
        }
        if (unknown_problem_pattern.length <= 0) {
            err_notify($('#error__problem_required').text());
        }
        mark_data = {
            mark_id: $('#mark_pk').val(),
            status: $("input[name='selected_status']:checked").val(),
            data_type: mark_type,
            is_modifiable: is_modifiable,
            problem: unknown_problem_pattern,
            function: unknown_function,
            is_regexp: $('#is_regexp').is(':checked'),
            link: $('#unknown_link').val(),
            comment: $('#edit_mark_comment').val(),
            description: description
        };
    }
    else {
        var error_trace = null, et_selector = $('#mark_error_trace');
        if (et_selector.length) {
            error_trace = et_selector.val();
        }
        mark_data = {
            attrs: collect_attrs_data(),
            mark_id: $('#mark_pk').val(),
            verdict: $("input[name='selected_verdict']:checked").val(),
            status: $("input[name='selected_status']:checked").val(),
            data_type: mark_type,
            is_modifiable: is_modifiable,
            tags: get_tags_values(),
            comment: $('#edit_mark_comment').val(),
            description: description,
            error_trace: error_trace
        };
    }

    if (mark_type === 'unsafe') {
        mark_data['compare_id'] = $("#compare_function").val();
    }

    return encodeData(JSON.stringify(mark_data));
};

window.set_action_on_func_change = function() {
    $.ajax({
        url: marks_ajax_url + 'get_func_description/',
        data: {func_id: $(this).children('option:selected').val()},
        type: 'POST',
        success: function (data) {
            if (data.error) {
                err_notify(data.error);
            }
            else {
                $('#compare_function_description').text(data['compare_desc']);
                $('#convert_function_description').text(data['convert_desc']);
                $('#convert_function_name').text(data['convert_name']);
            }

        }
    });
};

window.set_actions_for_mark_versions_delete = function() {
    $('.ui.checkbox').checkbox();
    $('#remove_versions_popup').modal({transition: 'fly up', autofocus: false, closable: false});
    $('#show_remove_mark_versions_popup').click(function () {
        $('#remove_versions_popup').modal('show');
    });
    $('#cancel_remove_mark_versions').click(function () {
        $('#remove_versions_popup').modal('hide');
    });
    $('#cancel_del_versions_mark_btn').click(function () {
        window.location.replace('');
    });
    $('#reload_page__versions').click(function () {
        window.location.replace('');
    });

    $('#delete_versions_btn').click(function () {
        $('#remove_versions_popup').modal('hide');
        var checked_versions = [];
        $('input[id^="checkbox_version__"]').each(function () {
            if ($(this).is(':checked')) {
                checked_versions.push($(this).attr('id').replace('checkbox_version__', ''));
            }
        });
        $.post(
            marks_ajax_url + 'remove_versions/',
            {
                mark_id: $('#mark_pk').val(),
                mark_type: $('#mark_type').val(),
                versions: JSON.stringify(checked_versions)
            },
            function (data) {
                var global_parent = $('#versions_rows');
                $.each(checked_versions, function (i, val) {
                    var version_line = $("#checkbox_version__" + val).closest('.version-line');
                    if (version_line.length) {
                        version_line.remove();
                    }
                });
                data.error ? err_notify(data.error) : success_notify(data.message);
                if (global_parent && global_parent.children().first().children().length == 0) {
                    $('#versions_to_delete_form').remove();
                    $('#no_versions_to_delete').show();
                }
            },
            'json'
        );
    });
};