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

window.src_filename_trunc = function() {
    let text_container = $('#ETVSourceTitle'),
        text_width = text_container.width(),
        window_width = $('#ETV_source_code').width();
    if (text_width > window_width * 0.95) text_container.css('float', 'right');
    else text_container.css('float', 'left');
};

$(document).ready(function () {
    let D1 = $('#etv-divider'), D2 = $('#etv-divider-2'),
        S = $('#etv-source'), T = $('#etv-trace'),
        A = $('#etv-assumes'), etv = $('#etv'),
        include_assumptions = (A.length > 0),
        Tw = parseInt(T.width(), 10),
        Sw = parseInt(S.width(), 10),
        D1w = parseInt(D1.width(), 10),
        minw = Math.round((Tw + Sw + D1w) * 15 / 100);

    D1.draggable({
        axis: 'x',
        containment: [
            etv.offset().left + minw,
            etv.offset().top,
            etv.offset().left + Tw + Sw - minw,
            etv.offset().top + etv.height()
        ],
        drag: function (event, ui) {
            let aw = parseInt(ui.position.left),
                bw = Tw + Sw - aw;
            if (ui.position.top < 0) {
                ui.position.top = 0;
            }
            T.css({width: aw});
            S.css({width: bw});
            if (include_assumptions) {
                A.css({width: bw});
                D2.css({left: aw + D1w, width: bw});
            }
            src_filename_trunc();
        },
        distance: 10
    });
    if (include_assumptions) {
        let Sh = parseInt(S.height(), 10),
            Ah = parseInt(A.height(), 10),
            D2h = parseInt(D2.width(), 10),
            minh = Math.round((Sh + Ah + D2h) * 2 / 100);
        D2.draggable({
            axis: 'y',
            containment: [
                etv.offset().left + Tw + D1w,
                etv.offset().top + minh + 35,
                etv.offset().left + Tw + Sw + D1w,
                etv.offset().top + Ah + Sh - minh
            ],
            drag: function (event, ui) {
                let ah = parseInt(ui.position.top),
                    bh = Sh + Ah - ah;
                if (ui.position.right < 0) {
                    ui.position.right = 0;
                }
                S.css({height: ah});
                A.css({height: bh});
            },
            distance: 5
        });
    }
});
