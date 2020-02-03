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

$(document).ready(function () {
    function compare_reports() {
        let sel_jobs = [];
        $('.job-checkbox:checked').each(function () { sel_jobs.push($(this).data('row')) });
        if (sel_jobs.length !== 2) return err_notify($('#error__no_jobs_to_compare').text());

        $('#dimmer_of_page').addClass('active');
        $.post(`/reports/api/fill-comparison/${sel_jobs[0]}/${sel_jobs[1]}/`, {}, function (resp) {
            $('#dimmer_of_page').removeClass('active');
            window.location.href = resp.url;
        }, 'json');
    }

    function compare_files() {
        let sel_jobs = [];
        $('.job-checkbox:checked').each(function () { sel_jobs.push($(this).data('row')) });
        if (sel_jobs.length !== 2) return err_notify($('#error__no_jobs_to_compare').text());
        window.location.href = '/jobs/comparison/' + sel_jobs[0] + '/' + sel_jobs[1] + '/';
    }

    $('.ui.dropdown').dropdown();

    $('#remove_jobs_popup').modal({transition: 'fly up', autofocus: false, closable: false});
    $('#show_remove_jobs_popup').click(function () {
        $('#jobs_actions_menu').popup('hide');
        let jobs_for_delete = [], confirm_delete_btn = $('#delete_jobs_btn');
        $('.job-checkbox:checked').each(function () { jobs_for_delete.push($(this).data('row')) });
        if (!jobs_for_delete.length) return err_notify($('#error__no_jobs_to_delete').text());

        $('#remove_jobs_popup').modal('show');
        confirm_delete_btn.unbind().click(function () {
            $('#remove_jobs_popup').modal('hide');
            $('#dimmer_of_page').addClass('active');
            let remove_failed = false;
            $.each(jobs_for_delete, function (i, job_id) {
                $.ajax({url: `/jobs/api/${job_id}/remove/`, method: "DELETE", error: function () { remove_failed = true }});
            });
            // When all delete requests are finished then reload the page
            $(document).ajaxStop(function () {
                $('#dimmer_of_page').removeClass('active');
                if (!remove_failed) window.location.replace('')
            });
        });
    });

    inittree($('.tree'), 2, 'folder open link violet icon', 'folder link violet icon');

    $('#cancel_remove_jobs').click(function () {
        $('#remove_jobs_popup').modal('hide')
    });

    $('#download_selected_jobs').click(function (event) {
        event.preventDefault();

        $('#jobs_actions_menu').popup('hide');
        let job_ids = [], decision_ids = [];
        $('.job-checkbox:checked').each(function () { job_ids.push($(this).val()) });
        $('.decision-checkbox:checked').each(function () { decision_ids.push($(this).val()) });
        if (!job_ids.length && !decision_ids.length) return err_notify($('#error__no_jobs_to_download').text());
        let job_ids_json = JSON.stringify(job_ids), decision_ids_json = JSON.stringify(decision_ids);
        $.post(PAGE_URLS.can_download, {jobs: job_ids_json, decisions: decision_ids_json}, function () {
            window.location.href = PAGE_URLS.download_jobs + '?jobs=' + encodeURIComponent(job_ids_json) + '&decisions=' + encodeURIComponent(decision_ids_json);
        });
    });

    $('#compare_reports_btn').click(compare_reports);
    $('#compare_files_btn').click(compare_files);

    // Create or change preset dir modal
    let new_preset_modal = $('#new_preset_dir_modal'),
        new_preset_modal_confirm = new_preset_modal.find('.modal-confirm');
    new_preset_modal.modal({transition: 'fly up', autofocus: false, closable: false});
    new_preset_modal.find('.modal-cancel').click(function () {
        new_preset_modal.modal('hide')
    });
    $('.add-preset-dir-link').click(function () {
        new_preset_modal_confirm.data('url', PAGE_URLS.create_preset_dir);
        new_preset_modal_confirm.data('method', 'POST');
        new_preset_modal_confirm.data('parent', $(this).data('parent'));
        new_preset_modal.find('#new_preset_dir_name').val('');
        new_preset_modal.modal('show');
    });
    $('.change-preset-dir-link').click(function () {
        let url = $(this).data('url');
        new_preset_modal_confirm.data('url', url);
        new_preset_modal_confirm.data('method', 'PATCH');
        new_preset_modal_confirm.data('parent', null);
        $.get(url + '?fields=name', {}, function (resp) {
            new_preset_modal.find('#new_preset_dir_name').val(resp['name']);
            new_preset_modal.modal('show');
        });
    });
    new_preset_modal_confirm.click(function () {
        $.ajax({
            url: $(this).data('url'),
            method: $(this).data('method'),
            data: {
                parent: $(this).data('parent'),
                name: new_preset_modal.find('#new_preset_dir_name').val()
            },
            success: function () {
                window.location.replace('')
            }
        });
    });

});
