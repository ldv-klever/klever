/*
 * Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
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
    var D1 = $('#etv-divider'), D2 = $('#etv-divider-2'),
        S = $('#etv-source'), T = $('#etv-trace'),
        A = $('#etv-assumes'), etv = $('#etv'),
        Tw = parseInt(T.width(), 10),
        Sw = parseInt(S.width(), 10),
        D1w = parseInt(D1.width(), 10),
        minw = parseInt((Tw + Sw + D1w) * 15 / 100, 10),
        Sh = parseInt(S.height(), 10),
        Ah = parseInt(A.height(), 10),
        D2h = parseInt(D2.width(), 10),
        minh = parseInt((Sh + Ah + D2h) * 2 / 100, 10);
    D1.draggable({
        axis: 'x',
        containment: [
            etv.offset().left + minw,
            etv.offset().top,
            etv.offset().left + Tw + Sw - minw,
            etv.offset().top + etv.height()
        ],
        drag: function (event, ui) {
            var aw = parseInt(ui.position.left),
                bw = Tw + Sw - aw;
            if (ui.position.top < 0) {
                ui.position.top = 0;
            }
            $('#etv-trace').css({width: aw});
            $('#etv-source').css({width: bw});
            $('#etv-assumes').css({width: bw});
            $('#etv-divider-2').css({left: aw + D1w, width: bw});
        },
        distance: 10
    });
    D2.draggable({
        axis: 'y',
        containment: [
            etv.offset().left + Tw + D1w,
            etv.offset().top + minh + 35,
            etv.offset().left + Tw + Sw + D1w,
            etv.offset().top + Ah + Sh - minh
        ],
        drag: function (event, ui) {
            var ah = parseInt(ui.position.top),
                bh = Sh + Ah - ah;
            if (ui.position.right < 0) {
                ui.position.right = 0;
            }
            S.css({height: ah});
            A.css({height: bh});
        },
        distance: 5
    });
    $('#etv_start').click(function () {
        $('.ETV_error_trace').first().children().each(function () {
            if ($(this).is(':visible')) {
                var line_link = $(this).find('a.ETV_La');
                var etv_window = $(this).closest('.ETV_error_trace');
                etv_window.scrollTop(etv_window.scrollTop() + $(this).position().top - etv_window.height() * 3/10);
                if (line_link.length) {
                    line_link.click();
                    return false;
                }
            }
        });
        $('#etv_play_forward').click();
    });

    $('#etv_start_backward').click(function () {
        var etv_window = $('.ETV_error_trace'),
            next_child = etv_window.first().children().last();
        while (next_child) {
            if (next_child.is(':visible')) {
                var line_link = next_child.find('a.ETV_La');
                if (line_link.length) {
                    etv_window.scrollTop(etv_window.scrollTop() + next_child.position().top - etv_window.height() * 7/10);
                    line_link.click();
                    next_child = null;
                }
            }
            if (next_child) {
                next_child = next_child.prev();
            }
        }
        $('#etv_play_backward').click();
    });
    $('.ETV_error_trace').first().children().each(function () {
        if ($(this).is(':visible')) {
            var line_link = $(this).find('a.ETV_La');
            var etv_window = $(this).closest('.ETV_error_trace');
            etv_window.scrollTop(etv_window.scrollTop() + $(this).position().top - etv_window.height() * 3/10);
            if (line_link.length) {
                line_link.click();
                return false;
            }
        }
    });
});
