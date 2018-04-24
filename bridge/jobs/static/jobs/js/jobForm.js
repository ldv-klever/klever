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

function get_last_version_id() {
    var last_job_version = 0;
    $('#job_version_selector').children('option').each(function () {
        var child_version = parseInt($(this).val());
        if (child_version > last_job_version) {
            last_job_version = child_version;
        }
    });
    return last_job_version;
}

function save_job() {
    var title_input = $('#job_name'), description = $('#description').val();

    if (title_input.val().length === 0) {
        err_notify($('#error__title_required').text());
        title_input.focus();
        return false;
    }

    var tmp_div = $('<div>').html(description);
    tmp_div.find('script').remove();
    tmp_div.find('*').each(function () {
        var element_in_div = $(this);
        $.each($(this)[0].attributes, function (i, attr) {
            if (attr.name.match("^on")) {
                element_in_div.removeAttr(attr.name)
            }
        });
    });
    description = tmp_div.html();

    $('#dimmer_of_page').addClass('active');
    $.post('', {
        name: title_input.val(),
        comment: $('#job_comment').val(),
        description: description,
        global_role: global_role(),
        user_roles: get_user_roles(),
        file_data: get_files_data('#filestree'),
        parent: $('#parent_identifier').val(),
        last_version: get_last_version_id(),
        safe_marks: $('#safe_marks_checkbox').is(':checked')
    }, function (data) {
        $('#dimmer_of_page').removeClass('active');
        data.error ? err_notify(data.error) : window.location.replace('/jobs/' + data.job_id + '/');
    }, "json");
}

$(document).ready(function () {
    var versions_selector = $('#job_version_selector'), job_id = $('#job_id').val(), version = versions_selector.children('option:selected').val();

    versions_selector.dropdown();
    init_files_tree('#filestree', job_id, version);
    linedTextEditor('editfile_area');
    init_roles_form('#user_roles_form', job_id, version);

    $('#file_not_commited_modal').modal({transition: 'fade in', autofocus: false, closable: false});
    $('#close_save_job_btn').click(function () { $('#file_not_commited_modal').modal('hide') });
    $('#confirm_save_job_btn').click(save_job);

    $('#save_job_btn').click(function () {
        !$('#commit_file_changes').hasClass('disabled') ? $('#file_not_commited_modal').modal('show') : save_job();
    });

    versions_selector.change(function () {
        var job_id = $("#job_id").val(), version = $(this).children('option:selected').val();
        $.get('/jobs/get_version_data/' + job_id + '/' + version + '/', {}, function (data) {
            data.error ? err_notify(data.error) : $('#description').val(data.description);
        });
        init_roles_form('#user_roles_form', job_id, version);
        refresh_files_tree('#filestree', job_id, version);

        var editfile_area = $('#editfile_area'), commit_btn = $('#commit_file_changes');
        editfile_area.val('');
        editfile_area.prop('disabled', true);
        if (!commit_btn.hasClass('disabled')) {
            commit_btn.addClass('disabled');
        }
    });
});
