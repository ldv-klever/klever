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
    $('#resources-note').popup();

    function update_decision_results(interval) {
        let decision_results_url = PAGE_URLS.decision_results + '?' + encodeQueryData(collect_view_data('2'));
        $.get(decision_results_url, {}, function (resp) {
            $('#decision_results_div').html(resp);
        }).fail(function () {
            clearInterval(interval);
        });
    }

    function update_progress(interval) {
        $.get(PAGE_URLS.get_progress, {}, function (resp) {
            $('#decision_progress_container').html(resp)
        }).fail(function () {
            clearInterval(interval);
        });
    }

    function check_status(interval) {
        $.get(PAGE_URLS.get_status, {}, function (data) {
            if (data.status !== $('#current_decision_status').val()) window.location.replace('');
        }, 'json').fail(function (resp) {
            let errors = flatten_api_errors(resp['responseJSON']);
            $.each(errors, function (i, err_text) { err_notify(err_text) });
            clearInterval(interval)
        });
    }

    // Activate rename decision modal
    let rename_decision_modal = $('#rename_decision_modal');
    rename_decision_modal.modal({transition: 'slide down', autofocus: false, closable: false})
        .modal('attach events', '#rename_decision_btn', 'show');
    rename_decision_modal.find('.modal-cancel').click(function () {
        rename_decision_modal.modal('hide')
    });
    rename_decision_modal.find('.modal-confirm').click(function () {
        $.ajax({
            url: $(this).data('url'),
            method: 'PATCH',
            data: {
                title: $('#rename_decision_input').val()
            },
            success: function () {
                window.location.replace('')
            }
        });
    });

    // Activate download verifier files modal
    let download_verifier_files_modal = $('#download_verifier_files_modal');
    let download_verifier_files_problems = $('download_verifier_filesc_problems');
    download_verifier_files_modal.modal({transition: 'slide down', autofocus: false, closable: false});
    $('#download_verifier_files_modal_show').click(function () {
        download_verifier_files_modal.modal('show')
    });
    download_verifier_files_modal.find('.modal-cancel').click(function () {
        download_verifier_files_modal.modal('hide')
    });
    download_verifier_files_modal.find('.modal-confirm').click(function () {
        let download_verifier_files_filters = {
            safes: $('#download_verifier_files_safes').is(':checked'),
            unsafes: $('#download_verifier_files_unsafes').is(':checked'),
            unknowns: $('#download_verifier_files_unknowns').is(':checked'),
            problems: []
        };
        $('.download_verifier_files-problem').each(function () {
            if ($(this).is(':checked')) {
                download_verifier_files_filters.problems.push({
                    problem: $(this).data('problem'),
                    component: $(this).data('component')
                });
            }
        });
        window.location.href = $(this).data('url') + '?filters=' +
                               encodeURIComponent(JSON.stringify(download_verifier_files_filters));
    });
    $('#download_verifier_files_unknowns').parent().checkbox({
        onChecked: function () { download_verifier_files_problems.show() },
        onUnchecked: function () { download_verifier_files_problems.hide() }
    });

    let num_of_updates = 0, is_filters_open = false, autoupdate_btn = $('#decision_autoupdate_btn');

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

    $('#decision_results_view_accordion').accordion({
        onOpen: function() { is_filters_open = true },
        onClose: function() { is_filters_open = false }
    });
    let interval = setInterval(function () {
        if ($.active > 0) return false;
        if (is_filters_open) return false;
        if (autoupdate_btn.data('status') === 'on') {
            // Autoupdate is turned on
            update_decision_results(interval);
            update_progress(interval);
            num_of_updates++;
            if (num_of_updates > 100) stop_autoupdate();
        }
        // Always update the status
        check_status(interval);
    }, 3000);
});
