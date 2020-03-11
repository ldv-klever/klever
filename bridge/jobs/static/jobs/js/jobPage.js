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

    function get_selected_decisions() {
        let selected_ids = [];
        $(".decision-checkbox-input:checked").each(function () {
            selected_ids.push(parseInt($(this).val()))
        });
        return selected_ids;
    }

    // Remove job modal
    let remove_job_warn_modal = $('#remove_job_warn_modal');
    remove_job_warn_modal.modal({transition: 'fade in', autofocus: false, closable: false});
    remove_job_warn_modal.find('.modal-cancel').click(function () {
        remove_job_warn_modal.modal('hide')
    });
    remove_job_warn_modal.find('.modal-confirm').click(function () {
        $('#dimmer_of_page').addClass('active');
        $.ajax({
            url: $(this).data('url'), method: "DELETE", data: {},
            success: function () {
                window.location.replace('/')
            }
        });
    });
    $('#remove_job_btn').click(function () {
        $('.browse').popup('hide');
        remove_job_warn_modal.modal('show');
    });

    // Fast start decision
    $('#fast_decide_job_btn').click(function () {
        $('#dimmer_of_page').addClass('active');
        $.post($(this).data('url'), {}, function (resp) {
            window.location.href = resp['url']
        });
    });

    let download_decisions_btn = $('#download_decisions_btn'),
        remove_decisions_btn = $('#remove_decisions_btn'),
        compare_files_btn = $('#compare_files_btn'),
        compare_decisions_btn = $('#compare_decisions_btn');

    $('.decision-checkbox').checkbox({
        onChange: function () {
            let sel_decisions = get_selected_decisions();
            update_action_button(download_decisions_btn, !sel_decisions.length);
            update_action_button(remove_decisions_btn, !sel_decisions.length);
            update_action_button(compare_files_btn, sel_decisions.length !== 2);
            update_action_button(compare_decisions_btn, sel_decisions.length !== 2);
        }
    });

    // Compare decisions' files
    compare_files_btn.click(function () {
        let sel_decisions = get_selected_decisions();
        if (sel_decisions.length !== 2) return err_notify(LOCAL_PAGE_ERRORS.compare_decisions_error);
        window.location.href = '/jobs/comparison/' + sel_decisions[0] + '/' + sel_decisions[1] + '/';
    });

    // Compare decisions' reports
    compare_decisions_btn.click(function () {
        let sel_decisions = get_selected_decisions();
        if (sel_decisions.length !== 2) return err_notify(LOCAL_PAGE_ERRORS.compare_decisions_error);

        $('#dimmer_of_page').addClass('active');
        $.post(`/reports/api/fill-comparison/${sel_decisions[0]}/${sel_decisions[1]}/`, {}, function (resp) {
            $('#dimmer_of_page').removeClass('active');
            window.location.href = resp.url;
        }, 'json');
    });

    // Download the job with decisions
    download_decisions_btn.click(function () {
        let sel_decisions = get_selected_decisions();
        if (!sel_decisions.length) return err_notify(LOCAL_PAGE_ERRORS.download_decisions_error);

        let decision_values = [];
        $.each(sel_decisions, function (i, value) {
            decision_values.push(`decision=${value}`);
        });
        window.location.href = $(this).data('url') + decision_values.join('&');
    });

    // Remove selected decisions
    let sel_decisions = [], remove_decisions_modal = $('#remove_decisions_warn_modal');
    remove_decisions_modal.modal({transition: 'fly up', autofocus: false, closable: false});
    remove_decisions_btn.click(function () {
        $('#jobs_actions_menu').popup('hide');
        sel_decisions = get_selected_decisions();
        if (!sel_decisions.length) return err_notify(LOCAL_PAGE_ERRORS.remove_decisions_error);

        remove_decisions_modal.modal('show');
    });
    remove_decisions_modal.find('.modal-confirm').click(function () {
        remove_decisions_modal.modal('hide');
        $('#dimmer_of_page').addClass('active');
        let remove_failed = false;
        $.each(sel_decisions, function (i, decision_id) {
            $.ajax({url: `/jobs/api/decision/${decision_id}/remove/`, method: "DELETE", error: function () { remove_failed = true }});
        });

        // When all delete requests are finished then reload the page
        $(document).ajaxStop(function () {
            $('#dimmer_of_page').removeClass('active');
            if (!remove_failed) window.location.replace('')
        });
    });
    remove_decisions_modal.find('.modal-cancel').click(function () {
        remove_decisions_modal.modal('hide')
    });
});
