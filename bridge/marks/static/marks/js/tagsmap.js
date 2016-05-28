$(document).ready(function () {
    $('.tagsmap').find(".line").each(function () {
        var for_style = [];
        $.each($(this).attr('class').split(/\s+/), function (a, cl_name) {
            var img_types;
            if (cl_name.startsWith('line-')) {
                 img_types = cl_name.replace('line-', '').split('');
            }
            if (img_types) {
                $.each(img_types, function (a, img_t) {
                    for_style.push("url('/static/marks/css/images/L_" + img_t + ".png') center no-repeat");
                });
            }
        });
        if (for_style.length) {
            $(this).attr('style', "background: " + for_style.join(',') + ';');
        }
    });
    $('td[id^="tag_id_"]').each(function () {
        var tag_id = $(this).attr('id').replace('tag_id_', '');
        $(this).popup({
            popup: $('#tag_description_popup_' + tag_id),
            hoverable: true,
            delay: {show: 100, hide: 300},
            variation: 'very wide'
        });
    });

    function clear_modal() {
        $('#tag_name').val('');
        $('#tag_description').val('');
        $('#tag_parent').children().each(function () {
            if ($(this).val() != 0) {
                $(this).remove();
            }
        });
        $('#edit_tag_id').val('');
    }

    var edit_tag_modal = $('#edit_tag_modal'), parent_dropdown = $('#tag_parent');
    parent_dropdown.dropdown();
    edit_tag_modal.modal({transition: 'drop', autofocus: false, closable: false});
    $('.mark-tag').click(function () {
        if (edit_tag_modal.length) {
            var tag_id = $(this).attr('id').replace('tag_id_', '');

            $('#tag_name').val($(this).text());
            $('#tag_description').val($('#tag_description_popup_' + tag_id).children('.content').first().html());
            $.ajax({
                url: '/marks/ajax/get_tag_parents/',
                type: 'POST',
                data: {
                    tag_type: $('#tags_type').text(),
                    tag_id: tag_id
                },
                success: function (data) {
                    if (data.error) {
                        err_notify(data.error);
                        clear_modal();
                        return false;
                    }
                    if (data['current'] != '0') {
                        parent_dropdown.append($('<option>', {'value': data['current'], 'text': $('#tag_id_' + data['current']).text(), selected: true}));
                    }
                    $.each(JSON.parse(data['parents']), function (i, value) {
                        var parent_name = $('#tag_id_' + value).text();
                        parent_dropdown.append($('<option>', {'value': value, 'text': parent_name}));
                    });
                    $('#edit_tag_id').val(tag_id);

                    edit_tag_modal.modal('show');

                    parent_dropdown.dropdown('refresh');
                    setTimeout(function () {
                        parent_dropdown.dropdown('set selected', parent_dropdown.val());
                    }, 1);
                }
            });
        }
    });
    $('#cancel_edit_tag').click(function () {
        edit_tag_modal.modal('hide');
        clear_modal();
    });
    $('#save_tag').click(function () {
        $.ajax({
            url: '/marks/ajax/save_tag/',
            type: 'POST',
            data: {
                tag_type: $('#tags_type').text()
            },
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                    clear_modal();
                    return false;
                }
                window.location.replace('');
            }
        });
    });
});