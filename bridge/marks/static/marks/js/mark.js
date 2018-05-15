/*
 * Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
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
    $.post('/marks/' + $('#mark_type').val() + '/' + $('#mark_pk').val() + '/remove_versions/', {versions: JSON.stringify(versions)}, function (data) {
        if (data['error']) {
            err_notify(data['error']);
        }
        else {
            success_notify(data['success']);
            $.each(versions, function (i, val) {
                var version_line = $("#checkbox_version__" + val).closest('.version-line');
                if (version_line.length) {
                    version_line.remove();
                }
            });
        }
    }, 'json');
}

function get_versions_comparison(v1, v2, versions_modal) {
    $.post('/marks/' + $('#mark_type').val() + '/' + $('#mark_pk').val() + '/compare_versions/', {v1: v1, v2: v2}, function (data) {
        if (data.error) {
            err_notify(data.error);
        }
        else {
            versions_modal.find('.content').html(data);
            versions_modal.modal('show');
        }
    });
}

$(document).ready(function () {
    $('.ui.dropdown').each(function () { if (!$(this).hasClass('search')) $(this).dropdown() });
    activate_tags();

    // Remove mark actions
    $('#remove_mark_popup').modal({transition: 'fly up', autofocus: false, closable: false});
    $('#cancel_remove_mark').click(function () { $('#remove_mark_popup').modal('hide') });
    $('#show_remove_mark_popup').click(function () {
        if (!$(this).hasClass('disabled')) {
            $('.browse').popup('hide');
            $('#remove_mark_popup').modal('show');
        }
    });
    $('#confirm_remove_mark').click(function () {
        var mark_type = $('#mark_type').val();
        $.post('/marks/delete/', {
            'type': mark_type, ids: JSON.stringify([$('#mark_pk').val()])
        }, function (data) {
            if (data.error) {
                err_notify(data.error);
            }
            else {
                var report_id = $('#report_id');
                if (report_id.length) {
                    window.location.replace('/reports/' + mark_type + '/' + report_id.val() + '/');
                }
                else {
                    window.location.replace('/marks/' + mark_type + '/');
                }
            }
        });
    });

    // Remove versions actions
    var remove_versions_btn = $('#show_remove_versions_modal');
    remove_versions_btn.hover(function () { $('#cant_remove_vers').show() }, function () { $('#cant_remove_vers').hide()});
    remove_versions_btn.click(function () {
        var versions = checked_versions();
        versions.length === 0 ? err_notify($('#error__no_vers_selected').text()) : $('#remove_versions_popup').modal('show');
    });
    $('#remove_versions_popup').modal({transition: 'fly up', autofocus: false, closable: false});
    $('#cancel_remove_versions').click(function () { $('#remove_versions_popup').modal('hide') });
    $('#delete_versions_btn').click(remove_versions);

    // Compare versions actions
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
