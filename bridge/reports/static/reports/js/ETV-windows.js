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
    let D = $('#etv-divider'), S = $('#etv-source'), T = $('#etv-trace'), etv = $('#etv'),
        Tw = parseInt(T.width(), 10), Sw = parseInt(S.width(), 10), Dw = parseInt(D.width(), 10),
        minw = Math.round((Tw + Sw + Dw) * 15 / 100);

    D.draggable({
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
        },
        distance: 10
    });
});