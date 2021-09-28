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
    $('.parent-popup').popup({inline:true});

    $('#resources-note').popup();
    $('#component_name_tr').popup({
        popup: $('#timeinfo_popup'),
        position: 'right center',
        hoverable: true,
        delay: {show: 100, hide: 300}
    });
    $('#computer_description_tr').popup({
        popup: $('#computer_info_popup'),
        position: 'right center',
        hoverable: true,
        delay: {show: 100, hide: 300}
    });
    $('.report-data-popup').each(function () {
        $(this).popup({
            html: $(this).attr('data-content'),
            position: 'right center',
            hoverable: $(this).hasClass('hoverable')
        });
    });

    let graph = new ReportGraph(document.getElementById('graph_container'));
    $('.load-graph-icon').click(function (event) {
        event.preventDefault();
        $('#graph_content_div').hide();
        $.get($(this).data('url'), function (resp) {
            $('#graph_title').text(resp.title);
            graph.fromDotData(resp.content);
            $('#graph_content_div').show();
        });
    })

    $('#open_fullscreen_graph_btn').click(function (event) {
        event.preventDefault();
        graph.openFullScreen();
    });
});
