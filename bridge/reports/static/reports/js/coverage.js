$(document).ready(function () {
    var src_code_content = $("#CoverageSRCContent"),
        src_data_content = $('#CoverageDataContent'),
        weight = $('#cov_weight').val();

    function show_src_code(filename) {
        $.ajax({
            method: 'post',
            url: '/reports/ajax/get-coverage-src/',
            dataType: 'json',
            data: {
                report_id: $('#report_id').val(),
                filename: filename,
                weight: weight
            },
            success: function(data) {
                if (data.error) {
                    err_notify(data.error)
                }
                else {
                    $('#selected_file_name').text(filename);
                    src_code_content.html(data['content']).scrollTop(0);
                    if ($(weight === '0')) {
                        src_data_content.html(data['data']).find('.item').tab();
                    }
                    $('#div_for_legend').html(data['legend']);
                }
            }
        });
    }
    $('#files_tree').dropdown({
        onChange: show_src_code,
        action: 'select'
    });
    src_code_content.on('scroll', function () {
        $(this).find('.COVStatic').css('left', $(this).scrollLeft());
    });
    src_code_content.on("click", ".COVLineLink", function(event) {
        event.preventDefault();
        // Clear old selection
        src_code_content.find('.COVLineSelected').removeClass('COVLineSelected');
        var line_container = $(this).closest('.COVLine');

        // If full-weight then show data
        if (weight === '0') {
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
        if ($(this).data('number')) {
            $(this).find('.CovNumberPopup').remove();
        }
    });
    src_code_content.on('mouseenter', '.COVIsFC[data-number]', function () {
        $(this).append($('<span>', {'class': 'CovNumberPopup', text: $(this).data('number')}));
    });
    src_code_content.on('mouseleave', '.COVIsFC[data-number]', function () {
        $(this).find('.CovNumberPopup').remove();
    });

    $('#show_cov_attributes').click(function () {
        var cov_attrs = $('#CoverageAttrTable');
        if (cov_attrs.is(':visible')) {
            cov_attrs.hide();
        }
        else {
            $('#CoverageTable').hide();
            $('#DataStatisticTable').hide();
            cov_attrs.show();
        }
    });
    $('#get_coverage_table').click(function () {
        var cov_table = $('#CoverageTable');
        if (cov_table.is(':visible')) {
            cov_table.hide();
        }
        else {
            if (cov_table.is(':empty')) {
                $.ajax({
                    method: 'post',
                    url: '/reports/ajax/get-coverage-statistic/',
                    dataType: 'json',
                    data: {
                        report_id: $('#report_id').val()
                    },
                    success: function (data) {
                        if (data.error) {
                            err_notify(data.error)
                        }
                        else {
                            cov_table.html(data['table']);
                            inittree($('.tree'), 1, 'folder open violet icon', 'folder violet icon');
                            cov_table.find('.tree-file-link').click(function (event) {
                                event.preventDefault();
                                show_src_code($(this).data('path'));
                                $('body').animate({ scrollTop: 0 }, "slow");
                            })
                        }
                    }
                });
            }
            $('#CoverageAttrTable').hide();
            $('#DataStatisticTable').hide();
            cov_table.show();
        }
    });

    if (weight === '0') {
        $('#get_data_statistic').click(function () {
            var data_stat = $('#DataStatisticTable');
            if (data_stat.is(':visible')) {
                data_stat.hide();
            }
            else {
                if (data_stat.is(':empty')) {
                    $.ajax({
                        method: 'post',
                        url: '/reports/ajax/get-coverage-data-statistic/',
                        dataType: 'json',
                        data: {
                            report_id: $('#report_id').val()
                        },
                        success: function (data) {
                            if (data.error) {
                                err_notify(data.error)
                            }
                            else {
                                data_stat.html(data['table']).find('.item').tab();
                            }
                        }
                    });
                }
                $('#CoverageAttrTable').hide();
                $('#CoverageTable').hide();
                data_stat.show();
            }
        });
    }
});
