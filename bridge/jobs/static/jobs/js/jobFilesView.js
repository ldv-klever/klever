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

function open_file_content(node) {
    if (node.data && node.data.hashsum) {
        $.get('/jobs/getfilecontent/' + node.data.hashsum + '/', {}, function (resp) {
            if (resp.error) {
                err_notify(resp.error);
                return false;
            }
            $('#file_content_name').text(node.text);
            $('#file_content').text(resp.content);
            $('#file_content_modal').modal('show');
        });
    }
}

function open_file_content_action(data) {
    var inst = $.jstree.reference(data.reference);
    open_file_content(inst.get_node(data.reference));

}

function open_file_content_dbl_click(event) {
    var inst = $(this).jstree(true), node = inst.get_node(event.target);
    if (inst.get_type(node) === 'file' && isFileReadable(node.text)) open_file_content(node);
}

function download_file(data) {
    var inst = $.jstree.reference(data.reference), node = inst.get_node(data.reference);
    if (node.data && node.data['hashsum']) {
        window.location.replace('/jobs/downloadfile/' + node.data['hashsum'] + '/?name=' + encodeURIComponent(node.text));
    }
}

function get_menu(node) {
    var menu = {};
    if (this.get_type(node) === "file") {
        if (isFileReadable(node.text)) menu.view = {'label': $('#jstree_view_label').text(), 'icon': 'ui eye icon', 'action': open_file_content_action};
        menu.download = {'label': $('#jstree_download_label').text(), 'icon': 'ui download icon', 'action': download_file};
    }
    return menu;
}

window.init_files_tree = function (tree_div_id, job_id, version) {
    $('#file_content_modal').modal('setting', 'transition', 'fade');
    $('#close_file_view').click(function (event) {
        event.preventDefault();
        $('#file_content_modal').modal('hide');
        $('#file_content').empty();
    });
    $.post('/jobs/get_version_files/' + job_id + '/' + version + '/', {}, function (json) {
        if (json.error) {
            err_notify(json.error);
            return false;
        }
        $(tree_div_id).jstree({
            "plugins" : ["contextmenu", "types"],
            'contextmenu': {'items': get_menu},
            'types': {
                'root': {'icon': 'ui violet archive icon'},
                'folder': {'icon': 'ui violet folder icon'},
                'file': {'valid_children': [], 'icon': 'ui file outline icon'}
            },
            'core' : {
                'check_callback': false,
                'multiple': false,
                'data': [json]
            }
        }).bind("dblclick.jstree", open_file_content_dbl_click);
    }, 'json');
};
