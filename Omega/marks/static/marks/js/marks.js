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
    var is_modifiable = $('#is_modifiable').is(':checked') ? true:false;
    return JSON.stringify({
        attrs: collect_attrs_data(),
        report_id: $('#report_pk').val(),
        convert_id: $("#convert_function").val(),
        compare_id: $("#compare_function").val(),
        verdict: $("input[name='selected_verdict']:checked").val(),
        status: $("input[name='selected_status']:checked").val(),
        report_type: $('#report_type').val(),
        is_modifiable: is_modifiable
    });
}


$(document).ready(function () {
    $('#save_new_mark_btn').click(function () {
        $.ajax({
            url: '/marks/save_mark/',
            data: {savedata: collect_new_markdata()},
            type: 'POST',
            success: function (data) {
                console.log(data);
                try {
                    JSON.stringify(data);
                    err_notify(data.error);
                } catch (e) {
                    // $('body').html(data)
                }
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });
});
