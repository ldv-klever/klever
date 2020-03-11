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

window.inittree = function(table, column, expanded, collapsed) {

    function get_ids(tr_class) {
        if (!tr_class) {
            return [null, null];
        }
        let classlist = tr_class.split(/\s+/), tt_par_id = null, tt_id = null;
        $.each(classlist, function(i, item) {
            if (item.startsWith('treegrid-parent-')) {
                tt_par_id = item.replace('treegrid-parent-', '');
            }
            else if (item.startsWith('treegrid-')) {
                tt_id = item.replace('treegrid-', '');
            }
        });
        return [tt_id, tt_par_id];
    }

    let old_rows = {}, indent = 16, prev_icon, prev_indent;
    let expanded_parents = [];
    table.find('tr').each(function() {
        let tt_par_id, tt_id,
            new_element = $('<div>', {class: 'tabletree'}), curr_ids = get_ids($(this).attr('class')),
            tree_cell = $(this).children('td:nth-child(' + column + ')');
        tt_id = curr_ids[0];
        tt_par_id = curr_ids[1];

        if (!tt_id) {
            return;
        }
        let curr_indent = 0, exists = false;
        if ($(this).find('.tabletree').length) {
            curr_indent = parseInt(tree_cell.find('.tabletree').css('margin-left'), 10);
            exists = true;
        }
        else {
            if (tt_par_id && tt_par_id in old_rows) {
                curr_indent = old_rows[tt_par_id] + indent;
            }
            new_element.append($("<span>", {style: 'margin-left: ' + curr_indent + 'px;', class: 'tabletree'}));
            if ($(this).hasClass('tr-show')) {
                $(this).removeClass('tr-show');
                new_element.append($('<i>', {class: expanded, style: 'cursor: pointer', id: 'tt_expander_' + tt_id}));
                expanded_parents.push(tt_id);
            }
            else {
                new_element.append($('<i>', {class: collapsed, style: 'cursor: pointer', id: 'tt_expander_' + tt_id}));
            }
            tree_cell.prepend(new_element.html());
            if (tt_par_id && expanded_parents.indexOf(tt_par_id) === -1) {
                $(this).hide();
            }
        }
        old_rows[tt_id] = curr_indent;
        if (prev_icon) {
            if (prev_indent >= curr_indent) {
                prev_icon.attr('style', 'opacity:0;');
                prev_icon.removeClass('link');
            }
            else prev_icon.attr('style', 'opacity:100%;');
        }
        prev_icon = tree_cell.find('i').first();
        prev_indent = curr_indent;

        if (!exists) {
            $('#tt_expander_' + tt_id).click(function () {
                let prev_ids = [tt_id], next_tr = $(this).closest('tr').next('tr'),
                    next_ids, next_id, next_par_id;
                if ($(this).attr('class') === expanded) {
                    $(this).attr('class', collapsed);
                    while (true) {
                        if (!next_tr.length) return update_colors(table);
                        next_ids = get_ids(next_tr.attr('class'));
                        next_id = next_ids[0];
                        next_par_id = next_ids[1];
                        if (!next_id) return update_colors(table);
                        if (next_par_id && prev_ids.indexOf(next_par_id) >= 0) {
                            next_tr.hide();
                            prev_ids.push(next_id);
                        }
                        else return update_colors(table);
                        next_tr = next_tr.next('tr');
                    }
                }
                else if ($(this).attr('class') === collapsed) {
                    $(this).attr('class', expanded);
                    while (true) {
                        if (!next_tr.length) return update_colors(table);
                        next_ids = get_ids(next_tr.attr('class'));
                        next_id = next_ids[0];
                        next_par_id = next_ids[1];
                        if (!next_id) return update_colors(table);
                        if (next_par_id && prev_ids.indexOf(next_par_id) >= 0) {
                            next_tr.show();
                            if (next_tr.find('i').first().attr('class') === expanded) {
                                prev_ids.push(next_id);
                            }
                        }
                        next_tr = next_tr.next('tr');
                    }
                }
            });
        }
    });
    if (prev_icon) {
        prev_icon.attr('style', 'opacity:0;');
        prev_icon.removeClass('link');
    }
};