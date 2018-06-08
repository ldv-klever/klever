/*
 * Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
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

var def_file_to_open = 'job.json';

function check_filename(str) {
    if (str.length > 0) {
        if (isASCII(str) || str.length < 30) {
            return true;
        }
        else {
            err_notify($("#error__filename_not_ascii").text());
            return false;
        }
    }
    err_notify($('#error__name_required').text());
    return false;
}

function reselect_node(inst, node) {
    var edit_file_area = $('#editfile_area'), commit_btn = $('#commit_file_changes');
    inst.deselect_node(node);
    edit_file_area.val('');
    edit_file_area.prop('disabled', true);
    if (!commit_btn.hasClass('disabled')) {
        commit_btn.addClass('disabled');
    }
    inst.select_node(node);
}

function uploadFileAction(data) {
    var inst = $.jstree.reference(data.reference), node = inst.get_node(data.reference),
        upload_file_modal = $('#upload_file_modal'), filename = $('#upload_file_name');

    upload_file_modal.find('.btn-file :file').on('fileselect', function (event, numFiles, label) {filename.val(label)});

    upload_file_modal.modal('show');

    var confirm_btn = $('#upload_file_confirm');
    confirm_btn.unbind('click');
    confirm_btn.click(function () {
        if ($('#upload_file_input').val().length <= 0) {
            err_notify($('#error__nofile_selected').text());
            return false;
        }
        if (!check_filename(filename.val())) {
            return false;
        }
        inst.create_node(node, {'type': 'file'}, "last", function(new_node) {
            setTimeout(function() {
                var form_data = new FormData(),
                    file_input = $('#upload_file_input');
                form_data.append('file', file_input[0].files[0]);
                confirm_btn.addClass('disabled');
                $.ajax({
                    url: '/jobs/upload_file/', data: form_data,
                    dataType: 'json', processData: false, type: 'POST', contentType: false,
                    mimeType: 'multipart/form-data', async: false,
                    success: function (resp) {
                        inst.rename_node(new_node, filename.val());
                        inst.open_node(node);
                        confirm_btn.removeClass('disabled');
                        resp.error ? err_notify(resp.error) : new_node.data = {hashsum: resp.hashsum};
                        upload_file_modal.modal('hide');
                        filename.val('');
                        file_input.replaceWith(file_input.clone(true));
                    }
                });
            }, 0);
        });
    });
}

function replace_file_action(data) {
    var inst = $.jstree.reference(data.reference), node = inst.get_node(data.reference),
        replace_file_modal = $('#replace_file_modal'), filename = $('#replace_file_name');

    replace_file_modal.find('.btn-file :file').on('fileselect', function (event, numFiles, label) {filename.val(label)});
    $('#replaced_file_name').text(node.text);

    replace_file_modal.modal('show');

    var confirm_btn = $('#replace_file_confirm'), file_input = $('#replace_file_input');
    confirm_btn.unbind('click');
    confirm_btn.click(function () {
        if (file_input.val().length <= 0) {
            err_notify($('#error__nofile_selected').text());
            return false;
        }
        if (!check_filename(filename.val())) {
            return false;
        }
        var form_data = new FormData();
        form_data.append('file', file_input[0].files[0]);
        confirm_btn.addClass('disabled');
        $.ajax({
            url: '/jobs/upload_file/', data: form_data,
            dataType: 'json', processData: false, type: 'POST', contentType: false,
            mimeType: 'multipart/form-data', async: false,
            success: function (resp) {
                if (resp.error) {
                    err_notify(resp.error);
                }
                else {
                    inst.rename_node(node, filename.val());
                    node.data = {hashsum: resp.hashsum};
                    confirm_btn.removeClass('disabled');
                    replace_file_modal.modal('hide');
                    filename.val('');
                    file_input.replaceWith(file_input.clone(true));
                    reselect_node(inst, node);
                }
            }
        });
    });
}

function load_file_content(node) {
    var editfile_area = $('#editfile_area');
    editfile_area.val('');

    if (node.data && node.data.hashsum) {
        var cached = $('#cached_files').find('span[data-hashsum="' + node.data.hashsum + '"]');
        if (cached.length) {
            editfile_area.val(cached.text());
            editfile_area.prop('disabled', false);
        }
        else if (isFileReadable(node.text)) {
            $.get('/jobs/getfilecontent/' + node.data.hashsum + '/', {}, function (resp) {
                if (resp.error) {
                    err_notify(resp.error);
                }
                else {
                    editfile_area.val(resp.content);
                    editfile_area.prop('disabled', false);
                    $('#cached_files').append($('<span>', {hidden: true, text: resp.content, 'data-hashsum': node.data.hashsum}));
                }
            });
        }
    }
    else if (isFileReadable(node.text)) editfile_area.prop('disabled', false);
}

function commit_file_changes(tree_div_id) {
    var tree = $(tree_div_id).jstree(true), node = tree.get_selected(true)[0];
    if (node) {
        var formData = new FormData();
        formData.append('file', new File([new Blob([$('#editfile_area').val()])], node.text));

        $.ajax({
            url: '/jobs/upload_file/', data: formData,
            processData: false, contentType: false, type: 'POST',
            success: function (resp) {
                if (resp.error) {
                    err_notify(resp.error)
                }
                else {
                    node.data = {hashsum: resp.hashsum};
                    $('#commit_file_changes').addClass('disabled');

                    var cached_files = $('#cached_files'),
                        cached = cached_files.find('span[data-hashsum="' + node.data.hashsum + '"]');
                    if (!cached.length) {
                        cached_files.append($('<span>', {
                            hidden: true, text: $('#editfile_area').val(), 'data-hashsum': node.data.hashsum
                        }));
                    }
                    success_notify($('#success__file_commited').text());
                }
            },
            error: function () {
                err_notify('File was not commited');
            }
        });
    }
}

function download_file(data) {
    var inst = $.jstree.reference(data.reference), node = inst.get_node(data.reference);
    if (node.data && node.data['hashsum']) {
        window.location.replace('/jobs/downloadfile/' + node.data['hashsum'] + '/?name=' + encodeURIComponent(node.text));
    }
}

function clear_editfile_area() {
    $('#commit_file_changes').addClass('disabled');
    var editfile_area = $('#editfile_area');
    editfile_area.prop('disabled', true);
    editfile_area.val('');
}

function get_menu(node) {
    var tmp = $.jstree.defaults.contextmenu.items(),
        node_type = this.get_type(node);
    delete tmp.ccp;

    if (node_type === "file") {
        delete tmp.create;
        tmp.replace = {
            'label': $('#jstree_edit_replace_label').text(),
            'icon': 'ui file icon',
            'action': replace_file_action
        };
        if (node.data && node.data['hashsum']) {
            tmp.download = {
                'label': $('#jstree_download_label').text(),
                'icon': 'ui download icon',
                'action': download_file
            }
        }
    }
    else {
        delete tmp.create.action;
        tmp.create.label = $('#jstree_new_label').text();
        tmp.create.submenu = {
            'create_folder': {
                'separator_after': true,
                'label': $('#jstree_new_folder_label').text(),
                'icon': 'ui folder outline icon',
                'action': function (data) {
                    var inst = $.jstree.reference(data.reference), obj = inst.get_node(data.reference);
                    inst.create_node(obj, {'type': 'folder'}, "first", function(new_node) {
                        setTimeout(function() {inst.edit(new_node);}, 0);
                    })
                }
            },
            'create_file': {
                'label': $('#jstree_new_file_label').text(),
                'icon': 'ui file outline icon',
                'action': function (data) {
                    var inst = $.jstree.reference(data.reference), obj = inst.get_node(data.reference);
                    inst.create_node(obj, {'type': 'file'}, "last", function(new_node) {
                        setTimeout(function() {inst.edit(new_node);}, 0);
                    })
                }
            },
            'upload_file': {
                'label': $('#jstree_new_upload_label').text(),
                'icon': 'ui upload icon',
                'action': uploadFileAction
            }
        };
        if (node_type === "root") return {'create': tmp.create};
    }

    tmp.rename.label = $('#jstree_rename_label').text();
    tmp.rename.icon = 'ui pencil icon';
    tmp.remove.label = $('#jstree_delete_label').text();
    tmp.remove.icon = 'ui remove icon';
    return tmp;
}

window.init_files_tree = function (tree_div_id, job_id, version) {
    $('#replace_file_modal').modal({transition: 'fly left'});
    $('#upload_file_modal').modal({transition: 'fly left'});
    $('.close-modal').click(function () {$('.ui.modal').modal('hide')});

    $.post('/jobs/get_version_files/' + job_id + '/' + version + '/', {}, function (json) {
        if (json.error) {
            err_notify(json.error);
            return false;
        }

        $(tree_div_id).jstree({
            "plugins" : ["contextmenu", "types", "unique", "dnd"],
            'contextmenu': {'items': get_menu},
            'types': {
                'root': {'icon': 'ui violet archive icon'},
                'folder': {'icon': 'ui violet folder icon'},
                'file': {'valid_children': [], 'icon': 'ui file outline icon'}
            },
            'core' : {
                'check_callback': function (operation, node) {
                    return this.get_type(node) !== "root"
                },
                'strings': {'New node': 'name'},
                'multiple': false,
                'data': [json]
            }
        }).on('select_node.jstree', function (e, data) {
            clear_editfile_area();
            if (data.node.type == 'file') load_file_content(data.node);
        }).on('ready.jstree', function () {
            var instance = $(tree_div_id).jstree(true),
                tree_data = instance._model.data,
                root_id = tree_data['#']['children'][0],
                first_file;
            for (var i = 0; i < tree_data[root_id]['children'].length; i++) {
                var child_id = tree_data[root_id]['children'][i];
                if (tree_data[child_id]['type'] == 'file') {
                    if (tree_data[child_id]['text'] == def_file_to_open) {
                        first_file = tree_data[root_id]['children'][i];
                        break;
                    }
                    else if (!first_file && isFileReadable(tree_data[child_id]['text'])) {
                        first_file = tree_data[root_id]['children'][i];
                    }
                }
            }
            if (first_file) instance.select_node(first_file);
        }).on('delete_node.jstree', clear_editfile_area);
    }, 'json');

    $('#commit_file_changes').click(function () { commit_file_changes(tree_div_id) });
    $('#editfile_area').on('input', function () { $('#commit_file_changes').removeClass('disabled') });
};

window.get_files_data = function(tree_div_id) {
    return JSON.stringify($(tree_div_id).jstree(true).get_json('#', {
        'no_state': true,  'no_li_attr': true,  'no_a_attr': true
    }));
};

window.refresh_files_tree = function (tree_div_id, job_id, version) {
    $.post('/jobs/get_version_files/' + job_id + '/' + version + '/', {}, function (json) {
        if (json.error) {
            err_notify(json.error);
            return false;
        }
        $(tree_div_id).jstree(true).settings.core.data = [json];
        $(tree_div_id).jstree(true).refresh();
    }, 'json');
};
