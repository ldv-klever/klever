$(document).ready(function () {
    var A = parseInt($('#etv-trace').width(), 10),
        B = parseInt($('#etv-source').width(), 10),
        Z = parseInt($('#etv-divider').width(), 10),
        minw = parseInt((A + B + Z) * 10 / 100, 10),
        etv = $('#etv'),
        splitter = function (event, ui) {
            var aw = parseInt(ui.position.left),
                bw = A + B - aw;
            if (ui.position.top < 0) {
                ui.position.top = 0;
            }
            $('#etv-trace').css({width: aw});
            $('#etv-source').css({width: bw});
        };
    $('#etv-divider').draggable({
        axis: 'x',
        containment: [
            etv.offset().left + minw,
            etv.offset().top,
            etv.offset().left + A + B - minw,
            etv.offset().top + etv.height()
        ],
        drag: splitter,
        distance: 10
    });

    $('#etv-options-activator').popup({
        popup: $('#etv-options'),
        position: 'bottom right',
        hoverable: true,
        on: 'click',
        delay: {
            show: 100,
            hide: 100
        }
    });

    $('#test_get_source').click(function () {
        $.ajax({
            url: '/reports/ajax/get_source/',
            type: 'POST',
            data: {
                report_id: $('#report_pk').val()
            },
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else if (data.name && data.content) {
                    $('#ETVSourceTitle').html(data.name);
                    $('#ETV_source_code').html(data.content);
                }
            },
            error: function (x) {
                $('#ETV_source_code').html(x.responseText);
            }
        });
    });
});