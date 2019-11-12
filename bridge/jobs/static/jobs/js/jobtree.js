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

$(document).ready(function () {
    function fill_all_values() {
        $('.all-footer-col').each(function () {
            let column = $(this).data('column'), sum = 0;
            $('.cell-column-' + column).each(function () {
                let number = $(this).data('number');
                if (number) sum += parseInt(number);
            });
            $(this).text(sum);
        });
    }

    function fill_checked_values() {
        $('.checked-footer-col').each(function () {
            let column = $(this).data('column'), sum = 0, has_checked = false;
            $('.job-checkbox:checked').each(function () {
                let number = $('.cell-column-' + column + '.cell-row-' + $(this).data('row')).first().data('number');
                if (number) sum += parseInt(number);
                has_checked = true;
            });
            $(this).text(has_checked ? sum : '-');
        });
    }

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

    inittree($('.tree'), 2, 'chevron down violet icon', 'chevron right violet icon');
    fill_all_values();
    $('.job-checkbox').change(fill_checked_values);

    $('#cancel_remove_jobs').click(function () {
        $('#remove_jobs_popup').modal('hide')
    });

    $('#download_selected_jobs').click(function (event) {
        event.preventDefault();

        $('#jobs_actions_menu').popup('hide');
        let job_ids = [];
        $('.job-checkbox:checked').each(function () { job_ids.push($(this).data('row')) });
        if (!job_ids.length) return err_notify($('#error__no_jobs_to_download').text());
        let job_ids_json = JSON.stringify(job_ids);
        $.post(PAGE_URLS.can_download, {jobs: job_ids_json}, function () {
            window.location.href = PAGE_URLS.download_jobs + '?jobs=' + encodeURIComponent(job_ids_json);
        });
    });

    $('#download_selected_trees').click(function (event) {
        event.preventDefault();
        if ($(this).hasClass('disabled')) return false;
        $('#jobs_actions_menu').popup('hide');
        let job_ids = [];
        $('.job-checkbox:checked').each(function () { job_ids.push($(this).data('row')) });
        if (!job_ids.length) return err_notify($('#error__no_jobs_to_download').text());
        window.location.href = PAGE_URLS.download_trees + '?jobs=' + encodeURIComponent(JSON.stringify(job_ids));
    });

    $('#compare_reports_btn').click(compare_reports);
    $('#compare_files_btn').click(compare_files);

    let create_job_modal = $('#create_job_modal');
    create_job_modal.modal({transition: 'fade', autofocus: false, closable: true})
        .modal('attach events', '#create_job_modal_show');
    create_job_modal.find('.modal-cancel').click(function () {
        create_job_modal.modal('hide')
    })
});
