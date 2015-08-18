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


function collect_new_markdata() {
    var is_modifiable_checkbox = $('#is_modifiable'), is_modifiable = true;
    if (is_modifiable_checkbox.length) {
        is_modifiable = is_modifiable_checkbox.is(':checked') ? true:false;
    }

    return JSON.stringify({
        attrs: collect_attrs_data(),
        report_id: $('#report_pk').val(),
        convert_id: $("#convert_function").val(),
        compare_id: $("#compare_function").val(),
        verdict: $("input[name='selected_verdict']:checked").val(),
        status: $("input[name='selected_status']:checked").val(),
        data_type: $('#report_type').val(),
        is_modifiable: is_modifiable
    });
}

function collect_markdata() {
    return JSON.stringify({
        attrs: collect_attrs_data(),
        mark_id: $('#mark_pk').val(),
        data_type: $('#mark_type').val(),
        compare_id: $("#compare_function").val(),
        comment: $('#edit_mark_comment').val(),
        verdict: $("input[name='selected_verdict']:checked").val(),
        status: $("input[name='selected_status']:checked").val()
    });
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

        },
        error: function (x) {
            console.log(x.responseText);
        }
    });
}

$(document).ready(function () {
    $('#save_new_mark_btn').click(function () {
        $.redirectPost(marks_ajax_url + 'save_mark/', {savedata: collect_new_markdata()});
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

            },
            error: function (x) {
                console.log(x.responseText);
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
                else if (data.table && data.adddata) {
                    $('#mark_attributes_table').html(data.table);
                    $('#mark_add_data_div').html(data.adddata);
                    $('#compare_function').change(set_action_on_func_change);
                }
            }
        });
    });

    $('#save_mark_btn').click(function () {
        var comment_input = $('#edit_mark_comment');
        if (comment_input.val().length > 0) {
            $.redirectPost(marks_ajax_url + 'save_mark/', {savedata: collect_markdata()});
        }
        else {
            err_notify($('#error__comment_required').text());
            comment_input.focus();
        }
    });
});
