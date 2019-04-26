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
    let versions = [];
    $('input[id^="checkbox_version__"]:checked').each(function () {
        versions.push($(this).val());
    });
    return versions;
}

function get_versions_comparison(v1, v2, versions_modal) {
    $.get(
        '/marks/' + $('#mark_type').val() + '/' + $('#mark_pk').val() + '/compare-versions/' + v1 + '/' + v2 + '/', {},
        function (resp) {
            versions_modal.find('.content').html(resp);
            versions_modal.modal('show');
        }
    );
}

$(document).ready(function () {
    $('.ui.dropdown').each(function () {
        if (!$(this).hasClass('search')) $(this).dropdown()
    });
    activate_tags();

    // Remove mark actions
    let remove_mark_modal = $('#remove_mark_modal');
    remove_mark_modal.modal({transition: 'fly up', autofocus: false, closable: false});
    remove_mark_modal.find('.modal-cancel').click(function () {
        remove_mark_modal.modal('hide')
    });
    remove_mark_modal.find('.modal-confirm').click(function () {
        remove_mark_modal.modal('hide');
        let redirect_url = $(this).data('redirect');
        $.ajax({
            url: $(this).data('url'),
            method: 'DELETE',
            success: function () {
                window.location.replace(redirect_url)
            }
        });
    });
    $('#remove_mark_modal_show').click(function () {
        if (!$(this).hasClass('disabled')) {
            $('.browse').popup('hide');
            remove_mark_modal.modal('show');
        }
    });

    // Remove versions actions
    let remove_versions_btn = $('#show_remove_versions_modal'), remove_versions_modal = $('#remove_versions_modal');
    remove_versions_btn.hover(function () { $('#cant_remove_vers').show() }, function () { $('#cant_remove_vers').hide()});
    remove_versions_btn.click(function () {
        let versions = checked_versions();
        versions.length === 0 ? err_notify($('#error__no_vers_selected').text()) : $('#remove_versions_modal').modal('show');
    });
    remove_versions_modal.modal({transition: 'fly up', autofocus: false, closable: false});
    remove_versions_modal.find('.modal-cancel').click(function () { remove_versions_modal.modal('hide') });
    remove_versions_modal.find('.modal-confirm').click(function () {
        remove_versions_modal.modal('hide');
        let versions = checked_versions();
        $.ajax({
            url: '/marks/api/' + $('#mark_type').val() + '/' + $('#mark_pk').val() + '/remove-versions/',
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

    // Compare versions actions
    let comparison_modal = $('#version_comparison_modal');
    comparison_modal.modal();
    $('#compare_versions').click(function () {
        let versions = checked_versions();
        if (versions.length !== 2) err_notify($('#error__select_two_vers').text());
        else get_versions_comparison(versions[0], versions[1], comparison_modal);
    });
    comparison_modal.find('.modal-cancel').click(function () {
        comparison_modal.find('.content').empty();
        comparison_modal.modal('hide');
    });
});
