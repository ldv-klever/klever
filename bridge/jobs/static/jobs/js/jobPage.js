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
});
