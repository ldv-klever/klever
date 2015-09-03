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


function collect_new_markdata(tags) {
    var is_modifiable_checkbox = $('#is_modifiable'), is_modifiable = true,
        mark_type = $('#report_type').val(), mark_data;

    if (is_modifiable_checkbox.length) {
        is_modifiable = is_modifiable_checkbox.is(':checked') ? true:false;
    }

    if (mark_type == 'unknown') {
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
            link: $('#unknown_link').val()
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
            tags: tags.getTags()
        };
    }

    if (mark_type == 'unsafe') {
        mark_data['convert_id'] = $("#convert_function").val();
        mark_data['compare_id'] = $("#compare_function").val();
    }

    return JSON.stringify(mark_data);
}


function collect_markdata(tags) {
    var is_modifiable_checkbox = $('#is_modifiable'), is_modifiable = true,
        mark_type = $('#mark_type').val(), mark_data;

    if (is_modifiable_checkbox.length) {
        is_modifiable = is_modifiable_checkbox.is(':checked') ? true:false;
    }

    if (mark_type == 'unknown') {
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
            link: $('#unknown_link').val(),
            comment: $('#edit_mark_comment').val()
        };
    }
    else {
        mark_data = {
            attrs: collect_attrs_data(),
            mark_id: $('#mark_pk').val(),
            verdict: $("input[name='selected_verdict']:checked").val(),
            status: $("input[name='selected_status']:checked").val(),
            data_type: mark_type,
            is_modifiable: is_modifiable,
            tags: tags.getTags(),
            comment: $('#edit_mark_comment').val()
        };
    }

    if (mark_type == 'unsafe') {
        mark_data['compare_id'] = $("#compare_function").val();
    }

    return JSON.stringify(mark_data);
}

function set_action_on_func_change() {
    $.ajax({
        url: marks_ajax_url + 'get_func_description/',
        data: {func_id: $(this).children('option:selected').val(), func_type: 'compare'},
        type: 'POST',
        success: function (data) {
            if (data.error) {
                err_notify(data.error);
            }
            else if (data.description) {
                $('#compare_function_description').text(data.description);
            }

        }
    });
}

function set_actions_for_mark_versions_delete() {
    $('#cancel_del_versions_mark_btn').click(function () {
        window.location.replace('');
    });

    $('#delete_versions_btn').click(function () {
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
                $.each(checked_versions, function (i, val) {
                     $("#checkbox_version__" + val).parent().parent().parent().remove();
                });
                data.status === 0 ? success_notify(data.message) : err_notify(data.message);
            },
            'json'
        );
    });
}

function activate_tags() {
    var tag_list = $('#tag_list');
    if (!tag_list.length) {
        return false;
    }
    var available_tags = [], old_tags = [], save_mark_btn = $('#save_mark_btn'),
        save_new_mark_btn = $('#save_new_mark_btn');
    $('#tags_old').children().each(function () {
        old_tags.push($(this).text());
    });

    if (save_mark_btn.length || save_new_mark_btn.length) {
        $('#tags_available').children().each(function () {
        available_tags.push($(this).text());
        });

        return tag_list.tags({
            tagData: old_tags,
            suggestions: available_tags,
            tagClass: "btn-success",
            promptText: $('#tags__enter_tags').text(),
            readOnlyEmptyMessage: $('#tags__not_tags_to_display').text()
        });
    }
    else {
        return tag_list.tags({
            tagData: old_tags,
            tagClass: "btn-success",
            promptText: $('#tags__enter_tags').text(),
            readOnlyEmptyMessage: $('#tags__not_tags_to_display').text(),
            readOnly: true
        });
    }
}

$(document).ready(function () {

    var marktags = activate_tags();

    $('#save_new_mark_btn').click(function () {
        $.redirectPost(marks_ajax_url + 'save_mark/', {savedata: collect_new_markdata(marktags)});
    });

    $('#convert_function').change(function () {
        $.ajax({
            url: marks_ajax_url + 'get_func_description/',
            data: {func_id: $(this).children('option:selected').val(), func_type: 'convert'},
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else if (data.description) {
                    $('#convert_function_description').text(data.description);
                }

            }
        });
    });

    $('#compare_function').change(set_action_on_func_change);

    $('#mark_version_selector').change(function () {
        $.ajax({
            url: marks_ajax_url + 'get_mark_version_data/',
            data: {
                version: $(this).val(),
                mark_id: $('#mark_pk').val(),
                type: $('#mark_type').val()
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    $('#mark_attributes_table').html(data.table);
                    $('#mark_add_data_div').html(data.adddata);
                    $('#compare_function').change(set_action_on_func_change);
                    marktags = activate_tags();
                }
            }
        });
    });

    $('#save_mark_btn').click(function () {
        var comment_input = $('#edit_mark_comment');
        if (comment_input.val().length > 0) {
            $.redirectPost(marks_ajax_url + 'save_mark/', {savedata: collect_markdata(marktags)});
        }
        else {
            err_notify($('#error__comment_required').text());
            comment_input.focus();
        }
    });

    $('#edit_mark_versions').click(function () {
        $.post(
            marks_ajax_url + 'getversions/',
            {mark_id: $('#mark_pk').val(), mark_type: $('#mark_type').val()},
            function (data) {
                try {
                    JSON.stringify(data);
                    err_notify(data.message);
                } catch (e) {
                    $('#div_for_version_list').html(data);
                    set_actions_for_mark_versions_delete();
                }
            }
        );
    });
});
