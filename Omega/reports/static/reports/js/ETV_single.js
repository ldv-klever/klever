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
        minh = parseInt((Sh + Ah + D2h) / 100, 10);
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
            etv.offset().top + minh + 50,
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
});
