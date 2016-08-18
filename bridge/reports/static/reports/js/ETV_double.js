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
    var etv = $('#etv'), S = $('#etv-source'), A = $('#etv-assumes'),
        D1 = $('#etv-divider'), D2 = $('#etv-divider-2'), D3 = $('#etv-divider-3'),
        T1 = $('#etv-trace___et1'), T2 = $('#etv-trace___et2'),
        Tw = parseInt(T1.width(), 10),
        T1h = parseInt(T1.height(), 10),
        T2h = parseInt(T2.height(), 10),
        D1w = parseInt(D1.width(), 10),
        D2h = parseInt(D2.height(), 10),
        D3h = parseInt(D3.height(), 10),
        Sw = parseInt(S.width(), 10),
        Sh = parseInt(S.height(), 10),
        Ah = parseInt(A.height(), 10),
        minw = parseInt((Tw + Sw + D1w) * 15 / 100, 10),
        minh1 = parseInt((Sh + Ah + D2h) * 4 / 100, 10),
        minh2 = parseInt((T1h + T2h + D3h) * 4 / 100, 10);
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
            T1.css({width: aw});
            T2.css({width: aw});
            $('#etv-divider-3').css({width: aw});
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
            etv.offset().top + minh1 + 35,
            etv.offset().left + Tw + Sw + D1w,
            etv.offset().top + Ah + Sh - minh1
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
    D3.draggable({
        axis: 'y',
        containment: [
            etv.offset().left,
            etv.offset().top + minh2 + 35,
            etv.offset().left + Tw,
            etv.offset().top + T1h + T2h + D3h - minh2
        ],
        drag: function (event, ui) {
            var ah = parseInt(ui.position.top),
                bh = T1h + T2h - ah;
            if (ui.position.left < 0) {
                ui.position.left = 0;
            }
            T1.css({height: ah});
            T2.css({height: bh});
        },
        distance: 5
    });
});
