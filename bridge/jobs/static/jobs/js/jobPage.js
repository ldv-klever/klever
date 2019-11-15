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
    let warn_modal = $('#warn_modal');

    function reload_page() {
        window.location.replace('')
    }

    function update_decision_results(interval) {
        let decision_results_url = PAGE_URLS.decision_results + '?' + encodeQueryData(collect_view_data('2'));
        $.get(decision_results_url, {}, function (resp) {
            $('#job_data_div').html(resp);
        }).fail(function () {
            clearInterval(interval);
        });
    }

    function update_progress(interval) {
        $.get(PAGE_URLS.get_progress, {}, function (resp) {
            $('#job_progress_container').html(resp)
        }).fail(function () {
            clearInterval(interval);
        });
    }

    function check_status(interval) {
        $.get(PAGE_URLS.get_status, {}, function (data) {
            if (data.status !== $('#job_status_value').val()) window.location.replace('');
        }, 'json').fail(function (resp) {
            let errors = flatten_api_errors(resp['responseJSON']);
            $.each(errors, function (i, err_text) { err_notify(err_text) });
            clearInterval(interval)
        });
    }

    function activate_download_for_compet() {
        let dfc_modal = $('#dfc_modal'), dfc_problems = $('#dfc_problems');
        dfc_modal.modal({transition: 'slide down', autofocus: false, closable: false});
        $('#dfc_modal_show').click(function () {
            dfc_modal.modal('show')
        });
        dfc_modal.find('.modal-cancel').click(function () {
            dfc_modal.modal('hide')
        });
        dfc_modal.find('.modal-confirm').click(function () {
            let dfc_filters = {
                safes: $('#dfc_safes').is(':checked'),
                unsafes: $('#dfc_unsafes').is(':checked'),
                unknowns: $('#dfc_unknowns').is(':checked'),
                problems: []
            };
            $('.dfc-problem').each(function () {
                if ($(this).is(':checked')) {
                    dfc_filters.problems.push({
                        problem: $(this).data('problem'),
                        component: $(this).data('component')
                    });
                }
            });
            window.location.href = $(this).data('url') + '?filters=' + encodeURIComponent(JSON.stringify(dfc_filters));
        });

        $('#dfc_unknowns').parent().checkbox({
            onChecked: function () { dfc_problems.show() },
            onUnchecked: function () { dfc_problems.hide() }
        });
    }

    function activate_run_history() {
        $('#run_history').dropdown();
        let download_conf_btn = $('#download_conf_btn');
        download_conf_btn.popup();
        download_conf_btn.click(function () {
            window.location.replace($('#run_history').val());
        });
    }

    function show_warn_modal(btn, warn_text_id, action_func) {
        $('.browse').popup('hide');

        let warn_confirm_btn = $('#warn_confirm_btn');
        $('#warn_text').text($('#' + warn_text_id).text());
        warn_confirm_btn.unbind();
        warn_confirm_btn.click(function () {
            warn_modal.modal('hide');
            action_func(btn);
        });
        warn_modal.modal('show');
    }

    function remove_job() {
        $('#dimmer_of_page').addClass('active');
        $.ajax({
            url: PAGE_URLS.remove_job, method: "DELETE", data: {},
            success: function () {
                $('#dimmer_of_page').removeClass('active');
                window.location.replace(PAGE_URLS.jobs_tree);
            }
        });
    }

    function check_children() {
        $.get(PAGE_URLS.has_children, {}, function (data) {
            data.children ? show_warn_modal(null, 'warn__has_children', remove_job) : remove_job();
        }, 'json');
    }

    function fast_run_decision() {
        $('#dimmer_of_page').addClass('active');
        $.post(PAGE_URLS.decide_job, {mode: 'fast'}, reload_page);
    }

    function lastconf_run_decision() {
        $('#dimmer_of_page').addClass('active');
        $.post(PAGE_URLS.decide_job, {mode: 'lastconf'}, reload_page);
    }

    function stop_job_decision() {
        $('#dimmer_of_page').addClass('active');
        $.post(PAGE_URLS.cancel_decision, {}, reload_page);
    }

    function collapse_reports() {
        $('#dimmer_of_page').addClass('active');
        $.post(PAGE_URLS.collapse_reports, {}, reload_page);
    }

    function clear_verifier_files(btn) {
        $('#dimmer_of_page').addClass('active');
        $.ajax({url: btn.data('url'), method: 'DELETE', success: reload_page});
    }

    $('.ui.dropdown').dropdown();
    $('#resources-note').popup();

    activate_download_for_compet();
    activate_run_history();
    init_versions_list();

    warn_modal.modal({transition: 'fade in', autofocus: false, closable: false});
    $('#warn_close_btn').click(function () { warn_modal.modal('hide') });
    $('#remove_job_btn').click(function () { show_warn_modal($(this), 'warn__remove_job', check_children) });
    $('#decide_job_btn').click(function () { show_warn_modal($(this), 'warn__decide_job', function () {
        window.location.href = PAGE_URLS.prepare_decision })
    });
    $('#fast_decide_job_btn').click(function () { show_warn_modal($(this), 'warn__decide_job', fast_run_decision) });
    $('#last_decide_job_btn').click(function () { show_warn_modal($(this), 'warn__decide_job', lastconf_run_decision) });
    $('#stop_job_btn').click(function () { show_warn_modal($(this), 'warn__stop_decision', stop_job_decision) });
    $('#collapse_reports_btn').click(function () { show_warn_modal($(this), 'warn__collapse', collapse_reports) });
    $('#clear_verifier_files_modal_show').click(function () { show_warn_modal($(this), 'warn__clear_files', clear_verifier_files) });


    let num_of_updates = 0, is_filters_open = false, autoupdate_btn = $('#job_autoupdate_btn');

    function stop_autoupdate() {
        if (autoupdate_btn.data('status') === 'off') {
            // Already stopped
            return false;
        }
        err_notify($('#error__autoupdate_off').text());
        autoupdate_btn.text($('#start_autorefresh').text());
        autoupdate_btn.data('status', 'off');
    }
    function start_autoupdate() {
        if (autoupdate_btn.data('status') === 'on') {
            // Already started
            return false;
        }
        num_of_updates = 0;
        autoupdate_btn.text($('#stop_autorefresh').text());
        autoupdate_btn.data('status', 'on');
    }

    autoupdate_btn.click(function () { $(this).data('status') === 'on' ? stop_autoupdate() : start_autoupdate() });

    $('#job_filters_accordion').accordion({'onOpen': function() { is_filters_open = true }, 'onClose': function() { is_filters_open = false }});
    let interval = setInterval(function () {
        if ($.active > 0) return false;
        if (is_filters_open) return false;
        if (autoupdate_btn.data('status') === 'on') {
            // Autoupdate is turned on
            update_decision_results(interval);
            update_progress(interval);
            num_of_updates++;
            if (num_of_updates > 20) stop_autoupdate();
        }
        // Always update the status
        check_status(interval);
    }, 3000);
});
