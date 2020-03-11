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

function FilesTree(tree_id) {
    let tree_root = $('#' + tree_id);
    this.tree_div = tree_root.find('.file-tree').first();
    this.file_content_modal = tree_root.find('#filetree_file_content_modal').first();
    this.tree_obj = null;

    this.get_file_url = '/jobs/api/file/{0}/';
    this.download_file_url = '/jobs/downloadfile/{0}/?name={1}';

    this.labels = {
        'download': 'Download',
        'view': 'View'
    };

    this.icons = {
        'download': 'download icon',
        'file_out': 'file outline icon',
        'arch_vio': 'violet archive icon',
        'folder_vio': 'violet folder icon',
        'view': 'eye icon'
    };

    return this;
}

FilesTree.prototype.get_menu = function(node) {
    let instance = this, menu = {};
    if (instance.tree_obj.get_type(node) === "file") {
        if (isFileReadable(node.text)) menu.view = {
            'label': instance.labels.view, 'icon': instance.icons.view,
            'action': function () { instance.open_file_content(instance.tree_obj.get_selected(true)[0]) }
        };
        menu.download = {
            'label': instance.labels.download, 'icon': instance.icons.download,
            'action': function () { instance.download_file(instance.tree_obj.get_selected(true)[0]) }
        };
    }
    return menu;
};

FilesTree.prototype.set_labels = function(labels) {
    let instance = this;
    $.each(labels, function (key, value) { instance.labels[key] = value });
};

FilesTree.prototype.open_file_content = function(node) {
    // Do nothing if node is not file or file is not readable
    if (this.tree_obj.get_type(node) !== 'file' || !isFileReadable(node.text)) return;

    let instance = this;

    if (node.data && node.data.hashsum) {
        $.get(instance.get_file_url.format(node.data.hashsum), {}, function (resp) {
            if (resp.error) { err_notify(resp.error) } else {
                instance.file_content_modal.find('.modal-title').text(node.text);
                instance.file_content_modal.find('.filecontent').text(resp);
                instance.file_content_modal.modal('show');
            }
        });
    }
};

FilesTree.prototype.download_file = function(node) {
    if (node.data && node.data['hashsum']) window.location.replace(
        this.download_file_url.format(node.data['hashsum'], encodeURIComponent(node.text))
    );
};

FilesTree.prototype.initialize = function (data) {
    let instance = this;

    // Already initialized, just return
    if (instance.tree_obj) return;

    // Initialize files tree
    instance.tree_div.jstree({
        "plugins" : ["contextmenu", "types"],
        'contextmenu': {'items': function (node) { return instance.get_menu(node) }},
        'types': {
            'root': {'icon': instance.icons.arch_vio},
            'folder': {'icon': instance.icons.folder_vio},
            'file': {'valid_children': [], 'icon': instance.icons.file_out}
        },
        'core' : {'check_callback': false, 'multiple': false, 'data': data}
    })
        .on('ready.jstree', function () {
            // Preserve tree instance; open root node;
            instance.tree_obj = arguments[1].instance;
            instance.tree_obj.open_node(instance.tree_obj.get_node('#').children[0]);
        })
        .bind("dblclick.jstree", function (event) {
            instance.open_file_content(instance.tree_obj.get_node(event.target));
        });

    instance.file_content_modal.modal('setting', 'transition', 'fade');
    instance.file_content_modal.find('.modal-cancel').click(function () {
        instance.file_content_modal.modal('hide');
        instance.file_content_modal.find('.filecontent').empty();
    });
};
