$(document).ready(function () {
    drow_connections();
    init_popups();
    var create_root_btn = $('#create_root_tag');
    create_root_btn.popup();

    // Clear data in create/edit modals
    function clear_modal() {
        $('#edit_tag_id').val('');
        $('#tag_name').val('');
        $('#tag_description').val('');
        $('#create_tag_name').val('');
        $('#create_tag_description').val('');
        $('#tag_parent').children().each(function () {
            if ($(this).val() != 0) {
                $(this).remove();
            }
        });
        $('#create_tag_parent').children().each(function () {
            if ($(this).val() != 0) {
                $(this).remove();
            }
        });
    }

    var remove_tag_icon = $('.remove-tag-icon'),
        create_tag_icon = $('.create-tag-icon'),
        edit_tag_icon = $('.edit-tag-icon');

    /*************
    * Remove Tag *
    *************/
    remove_tag_icon.hover(function () {
        $(this).parent().children('.icon-text-remove').first().show();
    }, function () {
        $(this).parent().children('.icon-text-remove').first().hide();
    });
    var remove_tag_modal = $('#remove_tag_modal');
    remove_tag_modal.modal({transition: 'fly up', autofocus: false, closable: false});
    remove_tag_icon.click(function () {
        $('.edit-tag-cell').popup('hide');
        $('#edit_tag_id').val($(this).parent().attr('id').replace('tag_popup_', ''));
        remove_tag_modal.modal('show');
    });
    $('#confirm_remove_tag').click(function () {
        $.ajax({
            url: '/marks/ajax/remove_tag/',
            type: 'POST',
            data: {
                tag_id: $('#edit_tag_id').val(),
                tag_type: $('#tags_type').text()
            },
            success: function (data) {
                if (data.error) {
                    remove_tag_modal.modal('hide');
                    clear_modal();
                    err_notify(data.error);
                    return false;
                }
                window.location.replace('');
            }
        });
    });
    $('#cancel_remove_tag').click(function () {
        remove_tag_modal.modal('hide');
        clear_modal();
    });

    /***********
    * Edit Tag *
    ***********/
    var edit_tag_modal = $('#edit_tag_modal'), parent_dropdown = $('#tag_parent');
    parent_dropdown.dropdown();
    edit_tag_modal.modal({transition: 'drop', autofocus: false, closable: false});

    $('#cancel_edit_tag').click(function () {
        edit_tag_modal.modal('hide');
        clear_modal();
    });
    edit_tag_icon.hover(function () {
        $(this).parent().children('.icon-text-edit').first().show();
    }, function () {
        $(this).parent().children('.icon-text-edit').first().hide();
    });
    edit_tag_icon.click(function () {
        var tag_popup = $(this).parent(), tag_id = tag_popup.attr('id').replace('tag_popup_', '');
        $('#tag_name').val($('#tag_id_' + tag_id).text());
        $('#tag_description').val(tag_popup.children('.content').first().html());
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
                    parent_dropdown.append($('<option>', {'value': value, 'text': $('#tag_id_' + value).text()}));
                });
                $('#edit_tag_id').val(tag_id);

                $('.edit-tag-cell').popup('hide');
                edit_tag_modal.modal('show');

                parent_dropdown.dropdown('refresh');
                setTimeout(function () {
                    parent_dropdown.dropdown('set selected', parent_dropdown.val());
                }, 1);
            }
        });
    });
    $('#save_tag').click(function () {
        $.ajax({
            url: '/marks/ajax/save_tag/',
            type: 'POST',
            data: {
                name: $('#tag_name').val(),
                tag_id: $('#edit_tag_id').val(),
                tag_type: $('#tags_type').text(),
                description: $('#tag_description').val(),
                parent_id: $('#tag_parent').val(),
                action: 'edit'
            },
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                    return false;
                }
                window.location.replace('');
            }
        });
    });

    /*************
    * Create Tag *
    *************/
    create_tag_icon.hover(function () {
        $(this).parent().children('.icon-text-create').first().show();
    }, function () {
        $(this).parent().children('.icon-text-create').first().hide();
    });

    var create_tag_modal = $('#create_tag_modal'), create_tag_parent = $('#create_tag_parent');
    create_tag_modal.modal({transition: 'drop', autofocus: false, closable: false});
    function create_tag_click(parent_id) {
        $.ajax({
            url: '/marks/ajax/get_tag_parents/',
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
                $.each(JSON.parse(data['parents']), function (i, value) {
                    var dropdown_option_data = {'value': value, 'text': $('#tag_id_' + value).text()};
                    if (value == parent_id) {
                        dropdown_option_data['selected'] = true;
                    }
                    create_tag_parent.append($('<option>', dropdown_option_data));
                });
                create_tag_parent.dropdown('refresh');
                setTimeout(function () {
                    create_tag_parent.dropdown('set selected', create_tag_parent.val());
                }, 1);
                $('.edit-tag-cell').popup('hide');
                create_tag_modal.modal('show');
            }
        });
    }
    create_root_btn.click(function () {
        create_tag_click(0);
    });
    create_tag_icon.click(function () {
        create_tag_click($(this).parent().attr('id').replace('tag_popup_', ''));
    });
    $('#cancel_create_tag').click(function () {
        create_tag_modal.modal('hide');
        clear_modal();
    });
    $('#confirm_create_tag').click(function () {
        $.ajax({
            url: '/marks/ajax/save_tag/',
            type: 'POST',
            data: {
                name: $('#create_tag_name').val(),
                tag_type: $('#tags_type').text(),
                description: $('#create_tag_description').val(),
                parent_id: $('#create_tag_parent').val(),
                action: 'create'
            },
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                    return false;
                }
                window.location.replace('');
            }
        });
    });
});