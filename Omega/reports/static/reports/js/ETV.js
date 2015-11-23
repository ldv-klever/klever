$(document).ready(function () {
    var D1 = $('#etv-divider'), D2 = $('#etv-divider-2'),
        S = $('#etv-source'), T = $('#etv-trace'), A = $('#etv-assumes'), etv = $('#etv'),
        Tw = parseInt(T.width(), 10),
        Sw = parseInt(S.width(), 10),
        Sh = parseInt(S.height(), 10),
        Ah = parseInt(A.height(), 10),
        D1w = parseInt(D1.width(), 10),
        D2h = parseInt(D2.width(), 10),
        minw = parseInt((Tw + Sw + D1w) * 15 / 100, 10),
        minh = parseInt((Sh + Ah + D2h) / 100, 10),
        splitter = function (event, ui) {
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
        splitter2 = function (event, ui) {
            var ah = parseInt(ui.position.top),
                bh = Sh + Ah - ah;
            if (ui.position.right < 0) {
                ui.position.right = 0;
            }
            S.css({height: ah});
            A.css({height: bh});
        };
    D1.draggable({
        axis: 'x',
        containment: [
            etv.offset().left + minw,
            etv.offset().top,
            etv.offset().left + Tw + Sw - minw,
            etv.offset().top + etv.height()
        ],
        drag: splitter,
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
        drag: splitter2,
        distance: 5
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
    function get_source_code(line, filename) {
        console.log(line);
        $.ajax({
            url: '/reports/ajax/get_source/',
            type: 'POST',
            data: {
                report_id: $('#report_pk').val(),
                file_name: filename
            },
            success: function (data) {
                var source_code_window = $('#ETV_source_code');
                if (data.error) {
                    $('#ETVSourceTitle').empty();
                    source_code_window.empty();
                    err_notify(data.error);
                }
                else if (data.name && data.content) {
                    $('#ETVSourceTitle').html(data.name);
                    source_code_window.html(data.content);
                    var selected_src_line = $('#ETVSrcL_' + line);
                    if (selected_src_line.length) {
                        source_code_window.scrollTop(source_code_window.scrollTop() + selected_src_line.position().top - source_code_window.height() * 3/10);
                        selected_src_line.parent().addClass('ETVSelectedLine');
                    }
                    else {
                        err_notify($('#error___line_not_found').text());
                    }
                }
            },
            error: function (x) {
                $('#ETV_source_code').html(x.responseText);
            }
        });
    }

    $('#test_get_source').click(function () {
        get_source_code(1, 'default-file.c');
    });

    $('.ETV_HideLink').click(function (event) {
        event.preventDefault();
        var whole_line = $(this).parent().parent(),
            expanded = 'mini icon violet caret down',
            collapsed = 'mini icon violet caret right',
            last_selector = $('.' + $(this).attr('id')).last(),
            next_line = whole_line.next('span');
        if ($(this).children('i').first().attr('class') == expanded) {
            $(this).children('i').first().attr('class', collapsed);
            whole_line.addClass('func_collapsed');
            while (!next_line.is(last_selector) && !next_line.is($('.ETV_End_of_trace').first())) {
                next_line.hide();
                next_line = next_line.next('span');
            }
            last_selector.hide();
        }
        else {
            $(this).children('i').first().attr('class', expanded);
            whole_line.removeClass('func_collapsed');
            while (!next_line.is(last_selector) && !next_line.is($('.ETV_End_of_trace').first())) {
                next_line.show();
                if (next_line.hasClass('func_collapsed')) {
                    next_line = $(
                        '.' + next_line.find('a[class="ETV_HideLink"]').first().attr('id')
                    ).last().next('span').next('span');
                }
                else {
                    next_line = next_line.next('span');
                }

            }
            last_selector.show();
        }
    });

    $('.ETV_La').click(function (event) {
        event.preventDefault();
        $('.ETVSelectedLine').removeClass('ETVSelectedLine');
        get_source_code(parseInt($(this).text()), 'default-file.c');
        var whole_line = $(this).parent().parent();
        whole_line.addClass('ETVSelectedLine');

        var assume_window = $('#ETV_assumes');
        assume_window.empty();
        whole_line.find('span[class="ETV_CurrentAssumptions"]').each(function () {
            var assume_ids = $(this).text().split(';');
            $.each(assume_ids, function (i, v) {
                var curr_assume = $('#' + v);
                if (curr_assume.length) {
                    assume_window.append($('<span>', {
                        text: curr_assume.text(),
                        style: 'color: red'
                    })).append($('<br>'));
                }
            });
        });
        whole_line.find('span[class="ETV_Assumptions"]').each(function () {
            var assume_ids = $(this).text().split(';');
            $.each(assume_ids, function (i, v) {
                var curr_assume = $('#' + v);
                if (curr_assume.length) {
                    assume_window.append($('<span>', {
                        text: curr_assume.text()
                    })).append($('<br>'));
                }
            });
        });
    });

    // $('.global_hide').hide();
});