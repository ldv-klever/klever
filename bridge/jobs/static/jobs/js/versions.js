function checked_versions() {
    var versions = [];
    $('input[id^="checkbox_version__"]:checked').each(function () {
        versions.push(parseInt($(this).attr('id').replace('checkbox_version__', ''), 10));
    });
    return versions;
}

function remove_versions() {
    $('#remove_versions_popup').modal('hide');
    var versions = checked_versions();
    $.post(
        job_ajax_url + 'remove_versions/',
        {
            job_id: $('#job_pk').val(),
            versions: JSON.stringify(versions)
        },
        function (data) {
            if (data['error']) {
                err_notify(data['error']);
            }
            else {
                success_notify(data['message']);
                $.each(versions, function (i, val) {
                    var version_line = $("#checkbox_version__" + val).closest('.version-line');
                    if (version_line.length) {
                        version_line.remove();
                    }
                });
            }
        },
        'json'
    );
}

function init_file_actions() {
    var comparison_modal = $('#version_comparison_modal');
    $('#version_file_modal').modal({closable: false});
    $('#version_file_close').click(function () {
        $('#version_file_modal').modal('hide');
        $('#version_file_name').empty();
        $('#version_file_content').empty();
        $('#file_download_btn').attr('href', '#').hide();
        comparison_modal.modal('show');
    });
    comparison_modal.find('.version-file').click(function(event) {
        var href = $(this).attr('href'), file_name = $(this).text();
        if (isFileReadable(file_name)) {
            event.preventDefault();
            $.ajax({
                url: job_ajax_url + 'getfilecontent/',
                data: {file_id: $(this).data('file-id')},
                type: 'POST',
                success: function (data) {
                    if (data.error) {
                        err_notify(data.error);
                    }
                    else {
                        $('#file_download_btn').attr('href', href).show();
                        $('#version_file_name').text(file_name);
                        $('#version_file_content').text(data);
                        $('#version_file_modal').modal('show');
                    }
                }
            });
        }
    });
    comparison_modal.find('.version-diff-files').click(function(event) {
        event.preventDefault();
        var file_name = $(this).closest('li').find('.version-file').first().text();
        $.post(
            job_ajax_url + 'get_files_diff/',
            {
                name1: 'Old', name2: 'New',
                file1_id: $(this).data('file1-id'), file2_id: $(this).data('file2-id')
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error)
                }
                else {
                    $('#file_download_btn').attr('href', '#').hide();
                    $('#version_file_name').text(file_name);
                    $('#version_file_content').text(data);
                    $('#version_file_modal').modal('show');
                }
            }
        );
    });
    return true;
}

function get_versions_comparison(v1, v2, versions_modal) {
    $.post(
        job_ajax_url + 'compare_versions/',
        {job_id: $('#job_pk').val(), v1: v1, v2: v2},
        function (data) {
            if (data.error) {
                err_notify(data.error);
            }
            else {
                versions_modal.find('.content').html(data);
                versions_modal.modal('show');
                init_file_actions();
            }
        }
    );
}

function init_versions_list() {
    $('#edit_job_div').find('.ui.checkbox').checkbox();

    var remove_versions_btn = $('#show_remove_versions_modal');
    remove_versions_btn.unbind();
    remove_versions_btn.hover(function () {
        $('#cant_remove_vers').show();
    }, function () {
        $('#cant_remove_vers').hide();
    });

    $('#remove_versions_popup').modal({transition: 'fly up', autofocus: false, closable: false});
    remove_versions_btn.click(function () {
        var versions = checked_versions();
        if (versions.length === 0) {
            err_notify($('#error__no_vers_selected').text());
        }
        else {
            $('#remove_versions_popup').modal('show');
        }
    });
    $('#close_versions').unbind().click(function () {
        window.location.replace('');
    });
    $('#cancel_remove_versions').unbind().click(function () {
        $('#remove_versions_popup').modal('hide');
    });

    $('#delete_versions_btn').unbind().click(remove_versions);

    var comparison_modal = $('#version_comparison_modal');
    comparison_modal.modal();
    $('#compare_versions').unbind().click(function () {
        var versions = checked_versions();
        if (versions.length !== 2) {
            err_notify($('#error__select_two_vers').text());
        }
        else {
            get_versions_comparison(versions[0], versions[1], comparison_modal);
        }
    });
    $('#close_comparison_view').unbind().click(function () {
        comparison_modal.find('.content').empty();
        comparison_modal.modal('hide');
    });
}

window.get_versions = function () {
    $.post(
        job_ajax_url + 'getversions/',
        {
            job_id: $('#job_pk').val()
        },
        function (data) {
            if (data.error) {
                err_notify(data.error);
            }
            else {
                $('#remove_versions_popup').remove();
                $('#version_comparison_modal').remove();
                $('#version_file_modal').remove();
                $('#edit_job_div').html(data);
                init_versions_list();
            }
        }
    );
};
