$(document).ready(function () {
    function show_src_code(filename) {
        $.ajax({
            method: 'post',
            url: '/reports/ajax/get-coverage-src/',
            dataType: 'json',
            data: {
                report_id: $('#report_id').val(),
                filename: filename
            },
            success: function(data) {
                if (data.error) {
                    err_notify(data.error)
                }
                else {
                    $('#selected_file_name').text(filename);
                    $('#CoverageSRCContent').html(data['content']);
                }
            }
        });
    }
    $('#files_tree').dropdown({
        onChange: show_src_code,
        action: 'select'
    });
});
