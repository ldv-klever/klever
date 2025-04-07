/*
 * Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

// (function($) { $.fn.getCodeMirror = function() { return (this).find('.CodeMirror')[0].CodeMirror } }(jQuery));

function FilesTree(tree_id, editor_id) {
    let tree_root = $('#' + tree_id);
    this.tree_div = tree_root.find('.file-tree').first();
    this.tree_upload_modal = tree_root.find('#filetree_upload_model').first();
    this.tree_replace_modal = tree_root.find('#filetree_replace_modal').first();
    this.tree_obj = null;

    this.mirror = null;
    this.editor_div = $('#' + editor_id);
    this.editor_status = this.editor_div.find('.editor-status').first();
    this.editor_display = this.editor_div.find('.editor-display').first();
    this.editor_filename = this.editor_div.find('.editor-filename').first();
    this.editor_cache = this.editor_div.find('.editor-cache').first();

    this.upload_file_url = '/jobs/api/file/';
    this.get_file_url = '/jobs/api/file/{0}/';
    this.download_file_url = '/jobs/downloadfile/{0}/?name={1}';
    this.def_file_to_open = 'job.json';

    this.messages = {
        not_ascii: 'File name is not ascii',
        filename_required: 'File name is required',
        file_commited: 'The file was committed',
        file_not_commited: 'The file was not committed',
        file_required: 'Please select the file',
        commit_required: 'Please commit the changed file'
    };
    this.labels = {
        'new': 'New',
        'folder': 'Directory',
        'file': 'File',
        'upload': 'Upload',
        'rename': 'Rename',
        'delete': 'Delete',
        'replace': 'Replace',
        'download': 'Download'
    };

    this.icons = {
        'file': 'file icon',
        'download': 'download icon',
        'folder_out': 'folder outline icon',
        'file_out': 'file outline icon',
        'upload': 'upload icon',
        'rename': 'pencil icon',
        'remove': 'remove icon',
        'arch_vio': 'violet archive icon',
        'folder_vio': 'violet folder icon'
    };

    return this;
}

FilesTree.prototype.not_commited = function() {
    return !this.editor_status.is(':hidden');
};

FilesTree.prototype.serialize = function() {
    return JSON.stringify(this.tree_obj.get_json('#', {'no_state': true,  'no_li_attr': true,  'no_a_attr': true}));
};

FilesTree.prototype.get_menu = function(node) {
    let instance = this;

    let tmp = $.jstree.defaults.contextmenu.items(),
        node_type = instance.tree_obj.get_type(node);
    delete tmp.ccp;

    if (node_type === "file") {
        delete tmp.create;
        tmp.replace = {
            'label': instance.labels.replace, 'icon': instance.icons.file,
            'action': function () {
                instance.tree_replace_modal.find('.modal-title').text(node.text);
                instance.tree_replace_modal.modal('show');
            }
        };
        if (node.data && node.data['hashsum']) {
            tmp.download = {
                'label': instance.labels.download, 'icon': instance.icons.download,
                'action': function () { instance.download_file() }
            }
        }
    }
    else {
        delete tmp.create.action;
        tmp.create.label = instance.labels.new;
        tmp.create.submenu = {
            'create_folder': {
                'separator_after': true, 'label': instance.labels.folder, 'icon': instance.icons.folder_out,
                'action': function (data) {
                    instance.tree_obj.create_node(
                        instance.tree_obj.get_node(data.reference), {'type': 'folder'}, "first",
                        function(new_node) { setTimeout(function() { instance.tree_obj.edit(new_node); }, 0); })
                }
            },
            'create_file': {
                'label': instance.labels.file, 'icon': instance.icons.file_out,
                'action': function (data) {
                    instance.tree_obj.create_node(
                        instance.tree_obj.get_node(data.reference), {'type': 'file'}, "last",
                        function(new_node) {
                            setTimeout(function() {instance.tree_obj.edit(new_node);}, 0);
                        });
                }
            },
            'upload_file': {
                'label': instance.labels.upload, 'icon': instance.icons.upload,
                'action': function () { instance.tree_upload_modal.modal('show') }
            }
        };
        if (node_type === "root") return {'create': tmp.create};
    }

    tmp.rename.label = instance.labels.rename;
    tmp.rename.icon = instance.icons.rename;
    tmp.remove.label = instance.labels.delete;
    tmp.remove.icon = instance.icons.remove;
    return tmp;
};

FilesTree.prototype.set_messages = function(messages) {
    let instance = this;
    $.each(messages, function (key, value) { instance.messages[key] = value });
};

FilesTree.prototype.set_labels = function(labels) {
    let instance = this;
    $.each(labels, function (key, value) { instance.labels[key] = value });
};

FilesTree.prototype.clear_editor = function() {
    // Clear editor content, history and make it read-Only
    this.mirror.setValue('');
    this.mirror.setOption('readOnly', true);
    this.mirror.clearHistory();
    this.editor_filename.empty();
    this.editor_status.hide();
};

FilesTree.prototype.open_first_file = function() {
    // Clear and disable editor in case if file wouldn't be found
    this.clear_editor();

    let tree = this.tree_div.jstree(true),
        tree_data = tree._model.data,
        root_id = tree_data['#']['children'][0],
        first_file;
    for (let i = 0; i < tree_data[root_id]['children'].length; i++) {
        let child_id = tree_data[root_id]['children'][i];
        if (tree_data[child_id]['type'] === 'file') {
            if (tree_data[child_id]['text'] === this.def_file_to_open) {
                first_file = tree_data[root_id]['children'][i];
                break;
            }
            else if (!first_file && isFileReadable(tree_data[child_id]['text'])) {
                first_file = tree_data[root_id]['children'][i];
            }
        }
    }
    if (first_file) tree.select_node(first_file);
};

FilesTree.prototype.upload_file = function(data, on_success, on_error) {
    let instance = this;
    $.ajax({
        url: instance.upload_file_url, type: 'POST',
        data: data, dataType: "json", processData: false,  contentType: false,
        success: function (resp) {
            resp.error ? err_notify(resp.error) : on_success(resp.hashsum);
        }, error: function (resp) {
            let errors = flatten_api_errors(resp['responseJSON']);
            $.each(errors, function (i, err) { err_notify(err) });
            if (on_error) on_error();
        }
    });
};

FilesTree.prototype.commit_file = function() {
    let instance = this;

    return new Promise((resolve, reject) => {
        // The file wasn't changed
        if (instance.editor_status.is(':hidden')) return;

        let node = instance.tree_obj.get_selected(true)[0];

        // No selected node
        if (!node) {
            reject("There are no selected node");
            return;
        }

        let data = new FormData(), content = instance.mirror.getValue();
        data.append('file', new File([new Blob([content])], node.text));

        instance.upload_file(data, function (hash_sum) {
            node.data = {hashsum: hash_sum};
            let cached = instance.editor_cache.find('span[data-hashsum="' + hash_sum + '"]');

            // Caching file content
            if (!cached.length) instance.editor_cache.append(
                $('<span>').text(content).data('hashsum', node.data.hashsum)
            );
            success_notify(instance.messages.file_commited);
            instance.editor_status.hide();
            resolve();
        }, () => {
            reject("File uploading failed");
        });
    });
};

FilesTree.prototype.set_editor_value = function(filename, content) {
    // Get highlighting mode
    let h_mode = 'text/plain';
    switch (getFileExtension(filename)) {
        case 'json':
            h_mode = {name: 'javascript', json: true};
            break;
        case 'c':
        case 'h':
        case 'i':
        case 'aspect':
        case 'tmpl':
            h_mode = 'text/x-csrc';
            break;
        case 'xml':
            h_mode = 'application/xml';
            break;
        case 'py':
            h_mode = 'text/x-python';
            break;
        case 'yml':
            h_mode = "text/x-yaml";
            break;
    }

    // Set editor content with mode, clear history and make it editable
    this.mirror.setValue(content);
    this.mirror.setOption('readOnly', false);
    this.mirror.setOption('mode', h_mode);
    this.mirror.clearHistory();
    this.editor_filename.text(filename);
};

FilesTree.prototype.load_file_content = function(node) {
    // Do nothing if file is not readable
    if (!isFileReadable(node.text)) return;

    let instance = this;

    if (node.data && node.data.hashsum) {
        let cached = instance.editor_cache.find('span[data-hashsum="' + node.data.hashsum + '"]');
        if (cached.length) {
            instance.set_editor_value(node.text, cached.text());
        }
        else {
            $.get(instance.get_file_url.format(node.data.hashsum), {}, function (resp) {
                instance.set_editor_value(node.text, resp);
                // Caching file content
                instance.editor_cache.append(
                    $('<span>', {hidden: true}).data('hashsum', node.data.hashsum).text(resp)
                );
            });
        }
    }
    // If readable file was created and content is still empty
    else instance.set_editor_value(node.text, '');
};

FilesTree.prototype.add_file_node = function(filename, hashsum) {
    let tree_inst = this.tree_obj, parent = tree_inst.get_selected(true)[0];

    tree_inst.create_node(parent, {'type': 'file'}, "last", function(new_node) {
        setTimeout(function() {
            tree_inst.rename_node(new_node, filename);
            tree_inst.open_node(parent);
            new_node.data = {hashsum: hashsum};
            tree_inst.deselect_node(parent);
            tree_inst.select_node(new_node);
        }, 0);
    });
};

FilesTree.prototype.check_filename = function(str) {
    if (str.length > 0) {
        if (isASCII(str) || str.length < 30) {
            return true;
        }
        else {
            err_notify(this.messages.not_ascii);
            return false;
        }
    }
    err_notify(this.messages.filename_required);
    return false;
};

FilesTree.prototype.initialize_modals = function() {
    let instance = this;

    // Initialize replace file modal
    instance.tree_replace_modal.modal({transition: 'fly left'});
    instance.tree_replace_modal.find('.modal-cancel').click(function () {
        instance.tree_replace_modal.modal('hide')
    });

    // Upload new file and replace old one on confirm button click
    instance.tree_replace_modal.find('.modal-confirm').click(function () {
        let confirm_btn = $(this), form_data = new FormData(),
            form_container = instance.tree_replace_modal.find('.modal-form');

        form_data.append('name', form_container.find('input[name="name"]').first().val());
        form_data.append('file', form_container.find('input[name="file"]')[0].files[0]);

        if (form_data.get('file').name.length === 0) return err_notify(instance.messages.file_required);
        if (!instance.check_filename(form_data.get('name'))) return false;

        confirm_btn.addClass('loading disabled');
        instance.upload_file(form_data, function (hash_sum) {
            confirm_btn.removeClass('loading disabled');

            // Update file node data (hashsum and name)
            let node = instance.tree_obj.get_selected(true)[0];
            instance.tree_obj.rename_node(node, form_data.get('name'));
            node.data = {hashsum: hash_sum};

            // Reselect the node to load new file content
            instance.tree_obj.deselect_node(node);
            instance.mirror.setValue('');
            instance.mirror.setOption('readOnly', true);
            instance.tree_obj.select_node(node);

            // Hide modal
            instance.tree_replace_modal.modal('hide');

            // Clear form
            let name_input = instance.tree_replace_modal.find('input[name="name"]'),
                file_input = instance.tree_replace_modal.find('input[name="file"]');
            name_input.val('');
            file_input.replaceWith(file_input.clone(true));
        }, function () { confirm_btn.removeClass('loading disabled') });
    });

    // Set file name on file select
    instance.tree_replace_modal.find('input[name="file"]').on('fileselect', function () {
        instance.tree_replace_modal.find('input[name="name"]').val(arguments[2])
    });

    // Initialize file upload modal
    instance.tree_upload_modal.modal({transition: 'fly left'});
    instance.tree_upload_modal.find('.modal-cancel').click(function () {
        instance.tree_upload_modal.modal('hide')
    });

    // Upload new file on confirm
    instance.tree_upload_modal.find('.modal-confirm').click(function () {
        let confirm_btn = $(this), form_data = new FormData(),
            form_container = instance.tree_upload_modal.find('.modal-form');

        form_data.append('name', form_container.find('input[name="name"]').first().val());
        form_data.append('file', form_container.find('input[name="file"]')[0].files[0]);

        if (form_data.get('file').name.length === 0) {
            err_notify(instance.messages.file_required);
            return false;
        }

        if (!instance.check_filename(form_data.get('name'))) return false;

        confirm_btn.addClass('loading disabled');
        instance.upload_file(form_data, function (hash_sum) {
            confirm_btn.removeClass('loading disabled');

            // Hide modal
            instance.tree_upload_modal.modal('hide');

            // Clear form
            let name_input = instance.tree_upload_modal.find('input[name="name"]'),
                file_input = instance.tree_upload_modal.find('input[name="file"]');
            name_input.val('');
            file_input.replaceWith(file_input.clone(true));

            // Add node to the tree
            instance.add_file_node(form_data.get('name'), hash_sum)
        }, function () { confirm_btn.removeClass('loading disabled') });
    });

    // Set file name on file select
    instance.tree_upload_modal.find('input[name="file"]').on('fileselect', function () {
        instance.tree_upload_modal.find('input[name="name"]').val(arguments[2])
    });
};

FilesTree.prototype.download_file = function() {
    let node = this.tree_obj.get_selected(true)[0];
    if (node.data && node.data['hashsum']) window.location.replace(
        this.download_file_url.format(node.data['hashsum'], encodeURIComponent(node.text))
    );
};

FilesTree.prototype.initialize = function (data) {
    let instance = this;

    // Already initialized, just refresh it
    if (instance.tree_obj) {
        instance.tree_obj.settings.core.data = data;
        instance.tree_obj.refresh();
        return;
    }

    // Init files editor help
    instance.editor_div.find('.editor-help-icon').popup({
        popup: instance.editor_div.find('.editor-help'),
        position: 'bottom right', lastResort: 'bottom right'
    });

    // Init files editor window
    let commit_file_key = is_mac() ? 'Cmd-S' : 'Ctrl-S';
    instance.mirror = CodeMirror(function (elt) { instance.editor_display.append(elt) }, {
        mode: {name: "javascript", json: true}, theme: "midnight", lineNumbers: true,
        readOnly: true, extraKeys: {
            [commit_file_key]: function () {
                instance.commit_file().catch(err => {
                    err_notify(err);
                });
            }}
    });
    instance.mirror.setSize('100%', '85vh');
    instance.mirror.on('change', function (doc, changeObj) {
        if (changeObj.origin !== 'setValue') instance.editor_status.show();
    });

    // Initialize files tree
    instance.tree_div.jstree({
        "plugins" : ["contextmenu", "types", "unique", "dnd"],
        'contextmenu': {'items': function (node) { return instance.get_menu(node) }},
        'types': {
            'root': {'icon': instance.icons.arch_vio},
            'folder': {'icon': instance.icons.folder_vio},
            'file': {'valid_children': [], 'icon': instance.icons.file_out}
        },
        'core' : {
            'check_callback': function (operation, node) { return this.get_type(node) !== "root" },
            'strings': {'New node': 'name'},
            'multiple': false,
            'data': data
        }
    })
        .on('select_node.jstree', function (e, data) {
            instance.clear_editor();
            if (data.node.type === 'file') instance.load_file_content(data.node);
        })
        .on('ready.jstree', function () {
            // Preserve tree instance; open root node; open first fouind file
            instance.tree_obj = arguments[1].instance;
            instance.tree_obj.open_node(instance.tree_obj.get_node('#').children[0]);
            instance.open_first_file();
        })
        .on('refresh.jstree', function () { instance.open_first_file() })
        .on('delete_node.jstree', function () { instance.clear_editor() });

    instance.initialize_modals();
};
