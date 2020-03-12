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
    $('.show-sch-tools').click(function (event) {
        event.preventDefault();
        let sch_type = $(this).data('type');
        $('tr[class="active-tr"]').removeClass('active-tr');
        $('.tools-arrow').hide();
        $('.tools-list').hide();

        $(this).closest('tr').addClass('active-tr');
        $(`.tools-list[data-type="${sch_type}"]`).show();
        $(`.tools-arrow[data-type="${sch_type}"]`).show();
    });
    $('.close-tools').click(function (event) {
        event.preventDefault();
        $('tr[class="active-tr"]').removeClass('active-tr');
        $('.tools-arrow').hide();
        $('.tools-list').hide();
    });

    $('.show-nodes').click(function (event) {
        event.preventDefault();
        let conf_id = $(this).data('conf');
        $('.node-of-conf').removeClass('active-tr');
        $('.nodes-configuration').removeClass('active-tr');
        $('.conf-info').hide();

        $(this).closest('tr').addClass('active-tr');
        $(`.node-of-conf[data-conf="${conf_id}"]`).addClass('active-tr');
        $(`.conf-info[data-conf="${conf_id}"]`).show();
    });
    $('.close-nodes-conf').click(function (event) {
        event.preventDefault();
        $('.node-of-conf').removeClass('active-tr');
        $('.nodes-configuration').removeClass('active-tr');
        $('.conf-info').hide();
    });

    $('.show-node-conf').click(function (event) {
        event.preventDefault();
        $('.node-of-conf').removeClass('active-tr');
        $('.nodes-configuration').removeClass('active-tr');
        $('.conf-info').hide();

        let conf_id = $(this).data('conf');
        $(this).closest('tr').addClass('active-tr');
        $(`.show-nodes[data-conf="${conf_id}"]`).closest('tr').addClass('active-tr');
    });
});
