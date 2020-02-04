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
    $('.ui.dropdown').dropdown();

    let compare_reports_btn = $('#compare_reports_btn'),
        compare_files_btn = $('#compare_files_btn'),
        download_selected_jobs = $('#download_selected_jobs'),
        show_remove_jobs_popup = $('#show_remove_jobs_popup');

    function update_action_button(btn_obj, disable=false) {
        if (disable) {
            if (!btn_obj.hasClass('disabled')) btn_obj.addClass('disabled');
        }
        else {
            if (btn_obj.hasClass('disabled')) btn_obj.removeClass('disabled');
        }
    }

    $('.job-checkbox').parent().checkbox({
        onChange: function () {
            let sel_jobs = get_selected_objs('job'), sel_decisions = get_selected_objs('decision');
            update_action_button(compare_files_btn, sel_jobs.length !== 2);
            update_action_button(download_selected_jobs, !sel_jobs.length && !sel_decisions.length);
            update_action_button(show_remove_jobs_popup, !sel_jobs.length && !sel_decisions.length);
        }
    });
    $('.decision-checkbox').parent().checkbox({
        onChange: function () {
            let sel_jobs = get_selected_objs('job'), sel_decisions = get_selected_objs('decision');
            update_action_button(compare_reports_btn, sel_decisions.length !== 2);
            update_action_button(download_selected_jobs, !sel_jobs.length && !sel_decisions.length);
            update_action_button(show_remove_jobs_popup, !sel_jobs.length && !sel_decisions.length);
        }
    });

    inittree($('.tree'), 2, 'folder open link violet icon', 'folder link violet icon');

    function get_selected_objs(obj_type) {
        let selected_ids = [];
        $(`.${obj_type}-checkbox:checked`).each(function () {
            selected_ids.push(parseInt($(this).val()))
        });
        return selected_ids;
    }

    // Remove selected jobs and decisions
    let selected_jobs = [], selected_decisions = [];
    $('#remove_jobs_popup').modal({transition: 'fly up', autofocus: false, closable: false});
    show_remove_jobs_popup.click(function () {
        $('#jobs_actions_menu').popup('hide');
        selected_jobs = get_selected_objs('job');
        selected_decisions = get_selected_objs('decision');
        if (!selected_jobs.length && !selected_decisions.length) return err_notify($('#error__no_objs_to_delete').text());

        $('#remove_jobs_popup').modal('show');
    });
    $('#delete_jobs_btn').click(function () {
        $('#remove_jobs_popup').modal('hide');
        $('#dimmer_of_page').addClass('active');
        let remove_failed = false;

        // Remove decisions first as jobs can remove its decisions
        $.each(selected_decisions, function (i, decision_id) {
            $.ajax({url: `/jobs/api/decision/${decision_id}/remove/`, method: "DELETE", error: function () { remove_failed = true }});
        });

        $.each(selected_jobs, function (i, job_id) {
            $.ajax({url: `/jobs/api/${job_id}/remove/`, method: "DELETE", error: function () { remove_failed = true }});
        });

        // When all delete requests are finished then reload the page
        $(document).ajaxStop(function () {
            $('#dimmer_of_page').removeClass('active');
            if (!remove_failed) window.location.replace('')
        });
    });
    $('#cancel_remove_jobs').click(function () {
        $('#remove_jobs_popup').modal('hide')
    });

    // Download selected jobs and/or decisions
    download_selected_jobs.click(function (event) {
        event.preventDefault();

        $('#jobs_actions_menu').popup('hide');
        let job_ids = get_selected_objs('job'),
            decision_ids = get_selected_objs('decision');
        if (!job_ids.length && !decision_ids.length) return err_notify($('#error__no_jobs_to_download').text());
        let job_ids_json = JSON.stringify(job_ids), decision_ids_json = JSON.stringify(decision_ids);
        $.post(PAGE_URLS.can_download, {jobs: job_ids_json, decisions: decision_ids_json}, function () {
            window.location.href = PAGE_URLS.download_jobs + '?jobs=' + encodeURIComponent(job_ids_json) + '&decisions=' + encodeURIComponent(decision_ids_json);
        });
    });

    // Compare decisions' reports
    compare_reports_btn.click(function () {
        let sel_decisions = get_selected_objs('decision');
        if (sel_decisions.length !== 2) return err_notify($('#error__no_decisions_to_compare').text());

        $('#dimmer_of_page').addClass('active');
        $.post(`/reports/api/fill-comparison/${sel_decisions[0]}/${sel_decisions[1]}/`, {}, function (resp) {
            $('#dimmer_of_page').removeClass('active');
            window.location.href = resp.url;
        }, 'json');
    });

    // Compare jobs' files
    compare_files_btn.click(function () {
        let sel_jobs = get_selected_objs('job');
        if (sel_jobs.length !== 2) return err_notify($('#error__no_jobs_to_compare').text());
        window.location.href = '/jobs/comparison/' + sel_jobs[0] + '/' + sel_jobs[1] + '/';
    });

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
