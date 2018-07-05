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
    $('a[id^="show_tools_"]').click(function (event) {
        event.preventDefault();
        var tool_type = $(this).attr('id').replace('show_tools_', '');
        $('tr[class="active-tr"]').removeClass('active-tr');
        $('i[id^="tools_arrow_"]').hide();
        $('div[id^="tools_"]').hide();

        $(this).parent().parent().parent().addClass('active-tr');
        $('#tools_' + tool_type).show();
        $('#tools_arrow_' + tool_type).show();
    });
    $('.close-tools').click(function (event) {
        event.preventDefault();
        $('tr[class="active-tr"]').removeClass('active-tr');
        $('i[id^="tools_arrow_"]').hide();
        $('div[id^="tools_"]').hide();
    });

    $('a[id^="show_nodes_"]').click(function (event) {
        event.preventDefault();
        var conf_id = $(this).attr('id').replace('show_nodes_', '');
        $('[class^="node-of-conf-"]').removeClass('active-tr');
        $('.nodes-configuration').removeClass('active-tr');
        $('[id^="conf_info_"]').hide();
        $(this).parent().parent().parent().addClass('active-tr');
        $('.node-of-conf-' + conf_id).addClass('active-tr');
        $('#conf_info_' + conf_id).show();
    });
    $('.close-nodes-conf').click(function (event) {
        event.preventDefault();
        $('[class^="node-of-conf-"]').removeClass('active-tr');
        $('.nodes-configuration').removeClass('active-tr');
        $('[id^="conf_info_"]').hide();
    });

    $('a[id^="show_node_conf__"]').click(function (event) {
        event.preventDefault();
        var conf_id = $(this).attr('id').replace('show_node_conf__', '');
        $('[class^="node-of-conf-"]').removeClass('active-tr');
        $('.nodes-configuration').removeClass('active-tr');
        $('[id^="conf_info_"]').hide();
        $(this).parent().parent().parent().addClass('active-tr');
        $('#show_nodes_' + conf_id).parent().parent().parent().addClass('active-tr');
    });
});
