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

function checked_versions() {
    let versions = [];
    $('input[id^="checkbox_version__"]:checked').each(function () {
        versions.push($(this).val());
    });
    return versions;
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
        let file_name = $(this).text(),
            download_link = $(this).data('download') + '?name=' + encodeURIComponent(file_name.substring(file_name.lastIndexOf('/') + 1));
        $(this).attr('href', download_link);
    });
    comparison_modal.find('.version-file').click(function(event) {
        let file_name = $(this).text(), href = $(this).attr('href');
        if (isFileReadable(file_name)) {
            event.preventDefault();
            $.get($(this).data('content'), {}, function (resp) {
                $('#file_download_btn').attr('href', href).show();
                $('#version_file_name').text(file_name);
                $('#version_file_content').text(resp);
                $('#version_file_modal').modal('show');
            });
        }
    });
    comparison_modal.find('.version-diff-files').click(function(event) {
        event.preventDefault();
        let file_name = $(this).closest('li').find('.version-file').first().text();
        $.get($(this).data('url'), {}, function (resp) {
            $('#file_download_btn').attr('href', '#').hide();
            $('#version_file_name').text(file_name);
            $('#version_file_content').text(resp);
            $('#version_file_modal').modal('show');
        });
    });
    return true;
}

window.init_versions_list = function() {
    // Remove job versions modal
    let rm_versions_modal = $('#remove_versions_modal');
    rm_versions_modal.modal({transition: 'fly up', autofocus: false, closable: false});
    rm_versions_modal.find('.modal-cancel').click(function () {
        rm_versions_modal.modal('hide');
    });
    rm_versions_modal.find('.modal-confirm').click(function () {
        rm_versions_modal.modal('hide');
        let versions = checked_versions();
        $.ajax({
            url: '/jobs/api/remove-versions/' + $('#job_id').val() + '/',
            method: 'DELETE',
            data: {versions: JSON.stringify(versions)},
            success: function (data) {
                success_notify(data['message']);
                $.each(versions, function (i, val) {
                    let version_line = $("#checkbox_version__" + val).closest('.version-line');
                    if (version_line.length) version_line.remove();
                });
            }
        });
    });
    $('#show_remove_versions_modal')
        .hover(function () { $('#cant_remove_vers').show() }, function () { $('#cant_remove_vers').hide() })
        .click(function () {
            let versions = checked_versions();
            if (versions.length) rm_versions_modal.modal('show');
            else  err_notify($('#error__no_vers_selected').text());
        });

    // Job versions comparison modal
    let comparison_modal = $('#version_comparison_modal');
    comparison_modal.modal();
    comparison_modal.find('.modal-cancel').click(function () {
        comparison_modal.find('.content').empty();
        comparison_modal.modal('hide');
    });
    $('#compare_versions').click(function () {
        let versions = checked_versions();
        if (versions.length !== 2) err_notify($('#error__select_two_vers').text());
        else {
            $.get(`/jobs/api/compare-versions/${$('#job_id').val()}/${versions[0]}/${versions[1]}/`, {}, function (resp) {
                comparison_modal.find('.content').html(resp);
                comparison_modal.modal('show');
                init_file_actions();
            });
        }
    });
};
