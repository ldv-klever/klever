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
        marks_ajax_url + 'remove_versions/',
        {
            mark_id: $('#mark_pk').val(),
            mark_type: $('#mark_type').val(),
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

function get_versions_comparison(v1, v2, versions_modal) {
    $.post(
        marks_ajax_url + 'compare_versions/',
        {mark_id: $('#mark_pk').val(), mark_type: $('#mark_type').val(), v1: v1, v2: v2},
        function (data) {
            if (data.error) {
                err_notify(data.error);
            }
            else {
                versions_modal.find('.content').html(data);
                versions_modal.modal('show');
            }
        }
    );
}

$(window).ready(function () {
    $('#edit_mark_div').find('.ui.checkbox').checkbox();

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
    $('#cancel_remove_versions').click(function () {
        $('#remove_versions_popup').modal('hide');
    });

    $('#delete_versions_btn').click(remove_versions);

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
    $('#close_comparison_view').click(function () {
        comparison_modal.find('.content').empty();
        comparison_modal.modal('hide');
    });
});
