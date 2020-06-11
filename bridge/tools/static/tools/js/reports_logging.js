function LogProcessor(rep_tree) {
    this.rep_tree = rep_tree;
    this.logs_container_id = 'log_container';
    this.table_body = $('#log_table_body');
    this.name_cache_container = $('#name_cache_div')
    this.current_log_line = null;
    this.table_rows_number = 0;
    this.report_ids = new Set();
    return this;
}

LogProcessor.prototype.refresh = function() {
    this.table_body.empty();
    this.table_rows_number = 0;
    this.current_log_line = null;
    this.report_ids = new Set();
    let root_name = this.rep_tree.tree_obj.get_node('#0').text;
    this.rep_tree.initialize([{'id': '#0', 'type': 'root', 'text': root_name, 'children': [], 'data': {}}]);
    $('#name_cache_div').empty();
};

LogProcessor.prototype.fill_log_data = function(data) {
    let logs_container = $(`#${this.logs_container_id}`);
    logs_container.empty();
    let counter = 0;

    $.each(data, function (i, line_data) {
        let new_obj = $('<span>', {'data-time': line_data['time'], 'data-type': line_data['type']});
        $.each(line_data['text'], function (i, text) {
            new_obj.append($('<span>', {'data-text-id': i, 'text': text}));
        })
        logs_container.append(new_obj);
        counter++;
    });
    return counter;
};

LogProcessor.prototype.get_next_line = function(speed) {
    if (!this.current_log_line) this.current_log_line = $(`#${this.logs_container_id}`).children()['first']();
    else this.current_log_line = this.current_log_line.next();
    if (!this.current_log_line.length) return err_notify("The end is reached!");

    let log_time = this.current_log_line.data('time'),
        log_type = this.current_log_line.data('type'),
        log_data = [], self = this, result;
    this.current_log_line.children('span').each(function () { log_data.push($(this).text()) });

    if (speed <= 2) {
        // For low speed select each node met on updating the tree
        result = self.process_log_step(log_type, log_time, log_data, function (node) {
            self.rep_tree.tree_obj.deselect_all();
            self.rep_tree.tree_obj.select_node(node);
        })
    }
    else result = self.process_log_step(log_type, log_time, log_data);

    if (!result) {
        this.current_log_line = this.current_log_line.prev();
        return err_notify("Log line can't be processed. Type: {0}, data: {1}".format(log_type, log_data))
    }

    if (this.table_rows_number > 20) this.table_body.children()['last']().remove();
    else this.table_rows_number++;

    return true;
};

LogProcessor.prototype.get_tree_node = function(report_id) {
    return this.rep_tree.tree_obj.get_node('' + report_id);
};

LogProcessor.prototype.process_log_step = function(log_type, time, data, callback) {
    let self = this, report_type, action_detail, extra_data = '-', report_id = null;

    switch (log_type) {
        case 'S0': {
            report_type = 'Start';
            action_detail = 'Uploading attributes';
            extra_data = `ID: ${data[0]}`;
            break;
        }
        case 'S1': {
            report_type = 'Start';
            action_detail = 'Creating report';
            extra_data = `Component: ${data[0]}; Parent ID: ${data[2]}; ID: ${data[1]}`;
            this.name_cache_container.append($('<span>', {'data-id': data[1], 'text': data[0]}));
            break;
        }
        case 'S2': {
            report_type = 'Start';
            action_detail = 'Report was created';
            extra_data = `Parent PK: ${data[2]}; ID: ${data[1]}`;
            report_id = data[0];
            this.report_ids.add(report_id);

            let parent_node = data[2] === 'NULL' ? '#0' : '' + data[2];
            let node = this.rep_tree.tree_obj.create_node(parent_node, {
                'id': report_id, 'type': 'component', 'children': [],
                'text': this.name_cache_container.find(`span[data-id="${data[1]}"]`).text(),
                'data': {'pk': data[0], 'identifier': data[1], 'status': 'In progress'}
            }, 'last', function (n) {
                if (callback) callback(n, true);
            });
            if (!node) return false;
            break;
        }
        case 'S3': {
            report_type = 'Start';
            action_detail = 'Cache was updated';
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;
            if (callback) callback(this.get_tree_node(report_id), false);
            break;
        }
        case 'SV0': {
            report_type = 'VerStart';
            action_detail = 'Preparing data';
            extra_data = `ID: ${data[0]}`;
            break;
        }
        case 'SV1': {
            report_type = 'VerStart';
            action_detail = 'Creating report';
            extra_data = `Component: ${data[0]}; Parent: ${data[2]}; ID: ${data[1]}`;
            this.name_cache_container.append($('<span>', {'data-id': data[1], 'text': data[0]}));
            break;
        }
        case 'SV2': {
            report_type = 'VerStart';
            action_detail = 'Report was created';
            extra_data = `Parent PK: ${data[2]}; ID: ${data[1]}`;
            report_id = data[0];
            this.report_ids.add(report_id);

            let node = this.rep_tree.tree_obj.create_node('' + data[2], {
                'id': report_id, 'type': 'verification', 'children': [],
                'text': this.name_cache_container.find(`span[data-id="${data[1]}"]`).text(),
                'data': {'pk': data[0], 'identifier': data[1], 'status': 'In progress'}
            }, 'last', function (n) {
                if (callback) callback(n, true);
            });
            if (!node) return false;
            break;
        }
        case 'SV3': {
            report_type = 'VerStart';
            action_detail = 'Cache was updated';
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;
            if (callback) callback(this.get_tree_node(report_id), false);
            break;
        }
        case 'C0': {
            report_type = 'Coverage';
            action_detail = 'Searching for report';
            extra_data = `ID: ${data[0]}`;
            break;
        }
        case 'C1': {
            report_type = 'Coverage';
            action_detail = 'Report was found';
            extra_data = `ID: ${data[1]}`;
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;
            if (callback) callback(this.get_tree_node(report_id), false);
            break;
        }
        case 'C2': {
            report_type = 'Coverage';
            action_detail = 'Coverage was saved';
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;
            if (callback) callback(this.get_tree_node(report_id), false);
            break;
        }
        case 'P0': {
            report_type = 'Patch';
            action_detail = 'Searching for report';
            extra_data = `ID: ${data[0]}`;
            break;
        }
        case 'P1': {
            report_type = 'Patch';
            action_detail = 'Report was found';
            extra_data = `ID: ${data[1]}`;
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;
            if (callback) callback(this.get_tree_node(report_id), false);
            break;
        }
        case 'P2': {
            report_type = 'Patch';
            action_detail = 'Report was updated';
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;
            if (callback) callback(this.get_tree_node(report_id), false);
            break;
        }
        case 'P3': {
            report_type = 'Patch';
            action_detail = 'Core sources are updated';
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;
            if (callback) callback(this.get_tree_node(report_id), false);
            break;
        }
        case 'F0': {
            report_type = 'Finish';
            action_detail = 'Searching for report';
            extra_data = `ID: ${data[0]}`;
            break;
        }
        case 'F1': {
            report_type = 'Finish';
            action_detail = 'Report was found';
            extra_data = `ID: ${data[1]}`;
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;
            if (callback) callback(this.get_tree_node(report_id), false);
            break;
        }
        case 'F2': {
            report_type = 'Finish';
            action_detail = 'Report was updated';
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;

            let node = this.get_tree_node(report_id);
            if (!node) return false;
            node.data['status'] = 'Finished';
            if (callback) callback(node, true);
            break;
        }
        case 'F3': {
            report_type = 'Finish';
            action_detail = 'Cache was updated';
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;
            if (callback) callback(this.get_tree_node(report_id), false);
            break;
        }
        case 'F4': {
            report_type = 'Finish';
            action_detail = 'Deleting report';
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;

            let node = this.get_tree_node(report_id);
            if (!node) return false;
            node.data['status'] = 'Deleted';
            this.rep_tree.tree_obj.set_type(node, 'deleted');

            // Mark all children as deleted
            let has_non_deleted = false;
            $.each(node.children_d, function (i, val) {
                let child = self.get_tree_node(val);
                if (child.data['status'] !== 'Deleted') {
                    has_non_deleted = true;
                    child.data['status'] = 'Deleted';
                    self.rep_tree.tree_obj.set_type(child, 'deleted');
                }
            });
            if (has_non_deleted) err_notify('The report {0} was deleted before the children are deleted'.format(report_id));

            if (callback) callback(node, true);
            break;
        }
        case 'FV0': {
            report_type = 'VerFinish';
            action_detail = 'Searching for report';
            extra_data = `ID: ${data[0]}`;
            break;
        }
        case 'FV1': {
            report_type = 'VerFinish';
            action_detail = 'Report was found';
            extra_data = `ID: ${data[1]}`;
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;
            if (callback) callback(this.get_tree_node(report_id), false);
            break;
        }
        case 'FV2': {
            report_type = 'VerFinish';
            action_detail = 'Deleting report';
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;

            let node = this.get_tree_node(report_id);
            node.data['status'] = 'Deleted';
            if (!node) return false;
            this.rep_tree.tree_obj.set_type(node, 'deleted');

            // Mark all children as deleted
            let has_non_deleted = false;
            $.each(node.children_d, function (i, val) {
                let child = self.get_tree_node(val);
                if (child.data['status'] !== 'Deleted') {
                    has_non_deleted = true;
                    child.data['status'] = 'Deleted';
                    self.rep_tree.tree_obj.set_type(child, 'deleted');
                }
            });
            if (has_non_deleted) err_notify('The report {0} was deleted before the children are deleted'.format(report_id));

            if (callback) callback(node, true);
            break;
        }
        case 'FV3': {
            report_type = 'VerFinish';
            action_detail = 'Report parent was changed';
            extra_data = `New parent PK: ${data[1]}`;
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;

            let node = this.get_tree_node(report_id);
            if (!node) return false;

            this.rep_tree.tree_obj.move_node(node, data[1], 'last', function (n) {
                if (callback) callback(n, true);
            });
            break;
        }
        case 'FV4': {
            report_type = 'VerFinish';
            action_detail = 'Report was updated';
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;

            let node = this.get_tree_node(report_id);
            if (!node) return false;

            node.data['status'] = 'Finished';
            if (callback) callback(node, true);
            break;
        }
        case 'FV5': {
            report_type = 'VerFinish';
            action_detail = 'Cache was updated';
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;
            if (callback) callback(this.get_tree_node(report_id), false);
            break;
        }
        case 'UN0': {
            report_type = 'Unknown';
            action_detail = 'Creating report';
            extra_data = `Parent ID: ${data[0]}`;
            break;
        }
        case 'UN1': {
            report_type = 'Unknown';
            action_detail = 'Report was created';
            extra_data = `Parent PK: ${data[1]}`;
            report_id = data[0];
            this.report_ids.add(report_id);

            let node = this.rep_tree.tree_obj.create_node(data[1], {
                'id': report_id, 'type': 'unknown', 'text': 'Unknown',
                'data': {'pk': report_id, 'identifier': '-', 'status': 'Created'}
            }, 'last', function (node) {
                if (callback) callback(node, true);
            });
            if (!node) return false;
            break;
        }
        case 'UN2': {
            report_type = 'Unknown';
            action_detail = 'Parent was changed';
            extra_data = `New parent PK: ${data[1]}`;
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;

            let node = this.get_tree_node(report_id);
            if (!node) return false;

            this.rep_tree.tree_obj.move_node(node, data[1], 'last', function (n) {
                if (callback) callback(n, true);
            });
            break;
        }
        case 'UN3': {
            report_type = 'Unknown';
            action_detail = 'Cache was updated';
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;
            if (callback) callback(this.get_tree_node(report_id), false);
            break;
        }
        case 'SF0': {
            report_type = 'Safe';
            action_detail = 'Creating report';
            extra_data = `Parent ID: ${data[0]}`;
            break;
        }
        case 'SF1': {
            report_type = 'Safe';
            action_detail = 'Report was created';
            extra_data = `Parent PK: ${data[1]}`;
            report_id = data[0];
            this.report_ids.add(report_id);

            let node = this.rep_tree.tree_obj.create_node(data[1], {
                'id': report_id, 'type': 'safe', 'text': 'Safe',
                'data': {'pk': report_id, 'identifier': '-', 'status': 'Created'}
            }, 'last', function (n) {
                if (callback) callback(n, true);
            });
            if (!node) return false;
            break;
        }
        case 'SF2': {
            report_type = 'Safe';
            action_detail = 'Cache was updated';
            report_id = data[0];
            if (!this.report_ids.has(report_id)) return false;
            if (callback) callback(this.get_tree_node(report_id), false);
            break;
        }
        case 'UF0': {
            report_type = 'Unsafe';
            action_detail = 'Creating report';
            extra_data = `Parent ID: ${data[0]}`;
            break;
        }
        case 'UF1': {
            report_type = 'Unsafe';
            action_detail = 'Report was created';
            extra_data = `Parent PK: ${data[1]}`;
            report_id = data[0];
            this.report_ids.add(report_id);

            let node = this.rep_tree.tree_obj.create_node(data[1], {
                'id': report_id, 'type': 'unsafe', 'text': 'Unsafe',
                'data': {'pk': report_id, 'identifier': '-', 'status': 'Created'}
            }, 'last', function (n) {
                if (callback) callback(n, true);
            });
            if (!node) return false;
            break;
        }
        case 'UF2': {
            report_type = 'Unsafe';
            action_detail = 'Cache was updated';
            // TODO: uncomment for good logs
            // report_id = data[0];
            // if (!this.report_ids.has(report_id)) return false;
            // if (callback) callback(this.get_tree_node(report_id), false);
            break;
        }
        default: {
            return err_notify('Unknown report log type: {0}'.format(log_type));
        }
    }

    let report_html;
    if (report_id) {
        report_html = $('<a>', {href: '#', 'data-id': report_id, text: report_id});
        report_html.click(function (event) {
            event.preventDefault();
            self.rep_tree.tree_obj.deselect_all();
            self.rep_tree.tree_obj.select_node(self.get_tree_node(report_id));
        });
    }
    else report_html = $('<span>', {text: '-'});

    // Creating table row
    this.table_body.prepend($('<tr>')
        .append($('<td>', {text: time}))
        .append($('<td>', {text: report_type}))
        .append($('<td>', {text: action_detail}))
        .append($('<td>').append(report_html))
        .append($('<td>', {text: extra_data}))
    );
    return true;
};


function ReportsTree(tree_id) {
    this.tree_div = $('#' + tree_id);
    this.tree_obj = null;
    this.title_search_id = 'title_search_input';
    this.icons = {
        'root': 'violet archive icon',
        'component': 'violet desktop icon',
        'verification': 'pink desktop icon',
        'unsafe': 'orange bug icon',
        'safe': 'green leaf icon',
        'unknown': 'pink exclamation circle icon',
        'deleted': 'red ban icon'
    };
    return this;
}

ReportsTree.prototype.open_node_content = function(node) {
    $('#selected_node_status').text(node.data['status']);
    $('#selected_node_identifier').text(node.data['identifier']);
    $('#node_data_segment').show();
};

ReportsTree.prototype.initialize = function (data) {
    let self = this;

    // Already initialized, just refresh it
    if (self.tree_obj) {
        self.tree_obj.deselect_all();
        self.tree_obj.close_all();
        self.tree_obj.settings.core.data = data;
        self.tree_obj.refresh();
        return;
    }

    // Initialize files tree
    self.tree_div.jstree({
        "plugins" : ["types", "search"],
        'types': {
            'root': {'icon': self.icons.root},
            'component': {'icon': self.icons.component},
            'verification': {'icon': self.icons.verification},
            'deleted': {'icon': self.icons.deleted},
            'safe': {'icon': self.icons.safe, 'valid_children': []},
            'unsafe': {'icon': self.icons.unsafe, 'valid_children': []},
            'unknown': {'icon': self.icons.unknown, 'valid_children': []},
        },
        'core' : {'check_callback': true, 'multiple': false, 'data': data}
    })
        .on('ready.jstree', function () {
            // Preserve tree instance;
            self.tree_obj = arguments[1].instance;
        })
        .on('select_node.jstree', function (e, data) {
            self.open_node_content(data.node);
        });

    let to = false;
    $(`#${self.title_search_id}`).keyup(function () {
        if (to) clearTimeout(to);
        to = setTimeout(function () {
            let v = $(`#${self.title_search_id}`).val();
            if (v === 'openall') self.tree_obj.open_all();
            else if (v === 'closeall') self.tree_obj.close_all();
            else self.tree_obj.search(v);
        }, 250);
    });
};

jQuery(function () {
    let rep_tree = new ReportsTree('tree_container_div');

    let parse_logs_btn = $('#parse_logs_btn');
    $('#logs_file_input').on('fileselect', function () {
        if (parse_logs_btn.hasClass('disabled')) parse_logs_btn.removeClass('disabled');
        $(this).siblings('.btn-title').text($(this)[0].files[0].name);
    });

    parse_logs_btn.click(function () {
        let files = $('#logs_file_input')[0].files;
        if (!files.length) return err_notify('Please select the log file');

        let data = new FormData();
        data.append('log', files[0]);

        let decision_id = parseInt($('#decision_id_input').val().trim());
        if (decision_id) data.append('decision', '' + decision_id);

        $('#dimmer_of_page').addClass('active');

        api_upload_file(PAGE_URLS.parse_logs, 'POST', data, function (resp) {
            let number = log_processor.fill_log_data(JSON.parse(resp['reports']));
            $('#steps_number_header').text(number);
            rep_tree.initialize([{
                'id': '#0', 'type': 'root',
                'text': "Decision " + resp['decision'],
                'children': [], 'data': {}
            }]);
            $('#parse_form_container').hide();
            $('#analyze_form_container').show();
            $('#dimmer_of_page').removeClass('active');
        });
    });

    let log_processor = new LogProcessor(rep_tree);
    let start_btn = $('.autofill-btn'), stop_btn = $('#autofill_stop_btn'),
        next_step_btn = $('#next_step_btn'), refresh_all_btn = $('#refresh_log_btn');

    next_step_btn.click(function () {
        let res = log_processor.get_next_line(0);
        if (!res) {
            start_btn.addClass('disabled');
            stop_btn.addClass('disabled');
            next_step_btn.addClass('disabled');
        }
    });

    refresh_all_btn.click(function () {
        log_processor.refresh();
        next_step_btn.removeClass('disabled');
        start_btn.removeClass('disabled');
        $('#node_data_segment').hide();
    });

    let interval = false;
    start_btn.click(function () {
        let speed = parseInt($(this).data('speed')),
            interval_delay = Math.floor(1000 / speed);
        start_btn.addClass('disabled');
        next_step_btn.addClass('disabled');
        refresh_all_btn.addClass('disabled');
        stop_btn.removeClass('disabled');

        interval = setInterval(function () {
            if ($.active > 0) return false;
            let res = log_processor.get_next_line(speed);
            if (!res) {
                stop_btn.addClass('disabled');
                refresh_all_btn.removeClass('disabled');
                if (interval) {
                    clearInterval(interval);
                    interval = false;
                }
            }
        }, interval_delay);
    });

    stop_btn.click(function () {
        stop_btn.addClass('disabled');
        next_step_btn.removeClass('disabled');
        refresh_all_btn.removeClass('disabled');
        start_btn.removeClass('disabled');
        if (interval) {
            clearInterval(interval);
            interval = false;
        }
    });
});
