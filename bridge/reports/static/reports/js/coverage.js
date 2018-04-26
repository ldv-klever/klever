$(document).ready(function () {
    var src_code_content = $("#CoverageSRCContent"),
        src_data_content = $('#CoverageDataContent'),
        with_data = $('#with_data').val(),
        cov_stat_table = $('#CoverageTable'),
        data_stat_table = $('#DataStatisticTable'),
        cov_attr_table = $('#CoverageAttrTable');

    function show_src_code(filename) {
        $.ajax({
            method: 'post',
            url: '/reports/get-coverage-src/' + $('#cov_arch_id').val() + '/',
            dataType: 'json',
            data: {filename: filename, with_data: with_data},
            success: function(data) {
                if (data.error) {
                    err_notify(data.error);
                    return false;
                }
                $('#selected_file_name').text(filename);
                src_code_content.html(data['content']).scrollTop(0);
                if ($(with_data === '1')) {
                    src_data_content.html(data['data']).find('.item').tab();
                }
                $('#div_for_legend').html(data['legend']);
            }
        });
    }
    function init_stat_tree(table) {
        var elems = table.find('.tg-expanded');
        elems.each(function () {
            var curr_id = $(this).data('tg-id');
            table.find('tr[data-tg-parent="' + curr_id + '"]').show();
        });

        table.on('click', '.tg-expander', function (event, with_shift, rec) {
            var tr = $(this).closest('tr'), tr_id = tr.data('tg-id');
            if (tr.hasClass('tg-expanded')) {
                table.find('tr.tg-expanded[data-tg-parent="' + tr_id + '"]').find('i.tg-expander').trigger("click", [false, true]);
                table.find('tr[data-tg-parent="' + tr_id + '"]').hide();
                $(this).removeClass('open');
                tr.removeClass('tg-expanded');
            }
            else {
                table.find('tr[data-tg-parent="' + tr_id + '"]').show();
                $(this).addClass('open');
                tr.addClass('tg-expanded');
                if (event.shiftKey || with_shift) {
                    table.find('tr[data-tg-parent="' + tr_id + '"]').find('i.tg-expander').trigger("click", [event.shiftKey || with_shift, true]);
                }
            }
            if (!rec) {
                update_colors(table);
            }
        });
        table.on('click', '.tree-file-link', function (event) {
            event.preventDefault();
            show_src_code($(this).data('path'));
            $('html, body').stop().animate({ scrollTop: 0 }, "slow");
        });
        cov_stat_table.show();
        update_colors(table);
    }

    init_stat_tree(cov_stat_table.find('table'));

    src_code_content.on('scroll', function () {
        $(this).find('.COVStatic').css('left', $(this).scrollLeft());
    });
    src_code_content.on("click", ".COVLineLink", function(event) {
        event.preventDefault();
        // Clear old selection
        src_code_content.find('.COVLineSelected').removeClass('COVLineSelected');
        var line_container = $(this).closest('.COVLine');

        // If full-weight then show data
        if (with_data === '1') {
            var visible_data = src_data_content.find('div[id^="COVDataLine_"]:visible');
            if (visible_data.length) {
                visible_data.hide();
                visible_data.find('div.segment').empty();
            }

            var line_num = line_container.data('line');
            if (line_num) {
                var new_data = src_data_content.find('#COVDataLine_' + line_num);
                new_data.find('.segment').each(function () {
                    $(this).html($('#' + $(this).data('data-id')).html());
                });
                new_data.find('.menu.item').tab();
                new_data.show();
            }
        }
        line_container.addClass('COVLineSelected');
    });
    src_code_content.on('mouseenter', '.COVLine[data-number]', function () {
        $(this).append($('<span>', {'class': 'CovNumberPopup', text: $(this).data('number')}));
    });
    src_code_content.on('mouseleave', '.COVLine[data-number]', function () {
        $(this).find('.CovNumberPopup').remove();
    });
    src_code_content.on('mouseenter', '.COVIsFC[data-number]', function () {
        $(this).append($('<span>', {'class': 'CovNumberPopup', text: $(this).data('number')}));
    });
    src_code_content.on('mouseleave', '.COVIsFC[data-number]', function () {
        $(this).find('.CovNumberPopup').remove();
    });

    src_code_content.on('mouseenter', '.COVCode[data-number]', function () {
        $(this).siblings('.COVStatic').find('.COVLine').append($('<span>', {'class': 'CovNumberPopup', text: $(this).data('number')}));
    });
    src_code_content.on('mouseleave', '.COVCode[data-number]', function () {
        $(this).siblings('.COVStatic').find('.CovNumberPopup').remove();
    });

    $('#show_cov_attributes').click(function () {
        if (cov_attr_table.is(':visible')) {
            cov_attr_table.hide();
        }
        else {
            cov_stat_table.hide();
            data_stat_table.hide();
            cov_attr_table.show();
        }
    });
    $('#get_coverage_table').click(function () {
        if (cov_stat_table.is(':visible')) {
            cov_stat_table.hide();
        }
        else {
            cov_attr_table.hide();
            data_stat_table.hide();
            cov_stat_table.show();
        }
    });

    if (with_data === '1') {
        data_stat_table.find('.item').tab();
        $('#get_data_statistic').click(function () {
            cov_attr_table.hide();
            cov_stat_table.hide();
            data_stat_table.show();
        });
    }
    $('.ui.dropdown').dropdown();
    $('#identifier_selector').change(function () {
        if (with_data === '1') {
            window.location.href = '/reports/coverage/' + $('#report_id').val() + '?archive=' + $(this).val();
        }
        else {
            window.location.href = '/reports/coverage-light/' + $('#report_id').val() + '?archive=' + $(this).val();
        }
    });
});
