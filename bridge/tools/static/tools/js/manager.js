$(document).ready(function () {
    $('button[id^="rename_component_btn__"]').click(function () {
        var component_id = $(this).attr('id').replace('rename_component_btn__', '');
        $.post(
            '/tools/ajax/change_component/',
            {
                action: 'rename',
                component_id: component_id,
                name: $('#component_name_input__' + component_id).val()
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify(data.message);
                }
            }
        );
    });
    $('button[id^="delete_component_btn__"]').click(function () {
        var component_id = $(this).attr('id').replace('delete_component_btn__', '');
        $.post(
            '/tools/ajax/change_component/',
            {
                action: 'delete',
                component_id: component_id
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify(data.message);
                    $('#component__' + component_id).remove();
                }
            }
        );
    });
    $('#clear_all_components').click(function () {
        $.post(
            '/tools/ajax/clear_components_table/',
            {},
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify(data.message);
                }
            }
        );
    });
    $('#clear_all_problems').click(function () {
        $.post(
            '/tools/ajax/clear_problems/',
            {},
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify(data.message);
                }
            }
        );
    });
    $('button[id^="delete_problem_btn__"]').click(function () {
        var problem_id = $(this).attr('id').replace('delete_problem_btn__', '');
        $.post(
            '/tools/ajax/delete_problem/',
            {
                problem_id: problem_id
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify(data.message);
                    $('#problem__' + problem_id).remove();
                }
            }
        );
    });

    $('#clear_system').click(function () {
        $('#dimmer_of_page').addClass('active');
        $.post(
            '/tools/ajax/clear_system/',
            {},
            function (data) {
                $('#dimmer_of_page').removeClass('active');
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify(data.message);
                }
            }
        );
    });
    $('#recalc_for_all_jobs_checkbox').checkbox({
        onChecked: function () {
            $('input[id^="job__"]').each(function () {
                $(this).prop('checked', true);
                $(this).parent().addClass('disabled');
            });
        },
        onUnchecked: function () {
            $('input[id^="job__"]').each(function () {
                $(this).prop('checked', false);
                $(this).parent().removeClass('disabled');
            });
        }
    });

    function get_data() {
        var jobs = [];
        if ($('#recalc_for_all_jobs').is(':checked')) {
            return {};
        }
        $('input[id^="job__"]').each(function () {
            if ($(this).is(':checked')) {
                jobs.push($(this).attr('id').replace('job__', ''));
            }
        });
        return {'jobs': JSON.stringify(jobs)};
    }
    $('button[id^="recalc_"]').click(function () {
        var data = get_data();
        data['type'] = $(this).attr('id').replace('recalc_', '');
        $('#dimmer_of_page').addClass('active');
        $('button[id^="recalc_"]').addClass('disabled');
        $.post(
            '/tools/ajax/recalculation/',
            data,
            function (data) {
                $('#dimmer_of_page').removeClass('active');
                $('button[id^="recalc_"]').removeClass('disabled');
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify(data.message);
                }
            }
        );
    });

    $('#upload_all_marks_popup').modal({transition: 'vertical flip'}).modal('attach events', '#upload_all_marks', 'show');
    $('#upload_all_marks_cancel').click(function () {
        $('#upload_all_marks_popup').modal('hide');
    });
    $('#upload_all_marks_file_input').on('fileselect', function () {
        $('#upload_all_marks_filename').text($(this)[0].files[0].name);
    });

    $('#uploaded_marks_modal').modal({transition: 'fade down', closable: false});
    $('#uploaded_marks_close').click(function () {
        $('#uploaded_marks_modal').modal('hide');
    });
    $('#upload_all_marks_start').click(function () {
        var files = $('#upload_all_marks_file_input')[0].files, data = new FormData();
        if (files.length <= 0) {
            err_notify($('#error__no_file_chosen').text());
            return false;
        }
        data.append('file', files[0]);
        if ($('#delete_marks_before_upload').is(':checked')) {
            data.append('delete', 1);
        }
        $('#upload_all_marks_popup').modal('hide');
        $('#dimmer_of_page').addClass('active');
        $.ajax({
            url: '/marks/upload-all/',
            type: 'POST',
            data: data,
            dataType: 'json',
            contentType: false,
            processData: false,
            mimeType: 'multipart/form-data',
            xhr: function() {
                return $.ajaxSettings.xhr();
            },
            success: function (data) {
                $('#dimmer_of_page').removeClass('active');
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    $('#num_uploaded_unsafe_marks').text(data['unsafe']);
                    $('#num_uploaded_safe_marks').text(data['safe']);
                    $('#num_uploaded_unknown_marks').text(data['unknown']);
                    $('#num_uploaded_fail_marks').text(data['fail']);
                    $('#uploaded_marks_modal').modal('show');
                }
            }
        });
    });
});
