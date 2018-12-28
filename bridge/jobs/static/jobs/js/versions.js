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
        '/jobs/remove_versions/' + $('#job_id').val() + '/',
        {
            versions: JSON.stringify(versions)
        },
        function (data) {
            if (data.error) {
                err_notify(data.error);
            }
            else {
                success_notify(data.message);
                $.each(versions, function (i, val) {
                    var version_line = $("#checkbox_version__" + val).closest('.version-line');
                    if (version_line.length) version_line.remove();
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
    comparison_modal.find('.version-file').each(function () {
        var file_name = $(this).text(), new_href = $(this).attr('href') + '?name=' + encodeURIComponent(file_name.substring(file_name.lastIndexOf('/') + 1));
        $(this).attr('href', new_href);
    });
    comparison_modal.find('.version-file').click(function(event) {
        var file_name = $(this).text(), href = $(this).attr('href');
        if (isFileReadable(file_name)) {
            event.preventDefault();
            $.get('/jobs/api/file/{0}/'.format($(this).data('hashsum')), {}, function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    $('#file_download_btn').attr('href', href).show();
                    $('#version_file_name').text(file_name);
                    $('#version_file_content').text(data.content);
                    $('#version_file_modal').modal('show');
                }
            });
        }
    });
    comparison_modal.find('.version-diff-files').click(function(event) {
        event.preventDefault();
        var file_name = $(this).closest('li').find('.version-file').first().text();
        $.post('/jobs/get_files_diff/' + $(this).data('hashsum1') + '/' + $(this).data('hashsum2') + '/', {}, function (data) {
            if (data.error) {
                err_notify(data.error)
            }
            else {
                $('#file_download_btn').attr('href', '#').hide();
                $('#version_file_name').text(file_name);
                $('#version_file_content').text(data.content);
                $('#version_file_modal').modal('show');
            }
        });
    });
    return true;
}

function get_versions_comparison(v1, v2, versions_modal) {
    $.post('/jobs/compare_versions/' + $('#job_id').val() + '/', {v1: v1, v2: v2}, function (data) {
        if (data.error) {
            err_notify(data.error);
        }
        else {
            versions_modal.find('.content').html(data);
            versions_modal.modal('show');
            init_file_actions();
        }
    });
}

window.init_versions_list = function() {
    $('#edit_job_div').find('.ui.checkbox').checkbox();

    $('#show_remove_versions_modal')
        .unbind()
        .hover(function () { $('#cant_remove_vers').show() }, function () { $('#cant_remove_vers').hide() })
        .click(function () { checked_versions().length === 0 ? err_notify($('#error__no_vers_selected').text()) : $('#remove_versions_popup').modal('show') });

    $('#remove_versions_popup').modal({transition: 'fly up', autofocus: false, closable: false});
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
};
