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

$(document).ready(function () {
    let etv_window = $('#ETV_error_trace'),
        data_window = $('#ETV_data');

    function unselect_etv_line() {
        etv_window.find('.ETVSelectedLine').removeClass('ETVSelectedLine');
        etv_window.find('.ETV_LINE_Note_Selected').removeClass('ETV_LINE_Note_Selected');
        data_window.empty();
    }

    let source_processor = new SourceProcessor(
        '#ETV_source_code', '#ETVSourceTitle',
        '#sources_history', '#ETV_data',
        '#CoverageLegend'
    );
    if (!etv_window.length) return false;
    source_processor.initialize(unselect_etv_line, $('#source_url').val());

    function show_scope(node) {
        if (!node.hasClass('scope_opened')) {
            node.addClass('scope_opened');
            node.find('.ETV_EnterLink').switchClass('right', 'down');
        }
        etv_window.find('.scope-' + node.data('scope')).each(function () {
            let node_type = $(this).data('type');
            if (node_type === 'function call' || node_type === 'action') {
                let has_note = $(this).hasClass('commented'),
                    was_opened = $(this).hasClass('scope_opened');

                // Actions can't have notes so it is always shown here
                if (!has_note || was_opened) $(this).show();

                // Open scope if it was opened earlier
                if (was_opened) show_scope($(this));
            }
            // Triangle should be shown for the opened scope if it exists
            else if (node_type === 'exit' || node_type === 'declarations') $(this).show();

            // Notes, statements and declarations are shown by show_display()
        });
        show_display(node);
    }

    function hide_scope(node, shift_pressed, change_state) {
        hide_display(node);
        if (change_state && node.hasClass('scope_opened')) {
            node.removeClass('scope_opened');
            node.find('.ETV_EnterLink').switchClass('down', 'right');
        }
        etv_window.find('.scope-' + node.data('scope')).each(function () {
            $(this).hide();
            let node_type = $(this).data('type');
            if (node_type === 'function call' || node_type === 'action') {
                hide_scope($(this), shift_pressed, shift_pressed);
            }
            else if (node_type === 'declarations' && $(this).find('.ETV_OpenEye').hasClass('hide')) {
                // Close eye of opened declarations block
                hide_display($(this));
            }
        });
    }

    function show_scope_shift(node) {
        if (!node.hasClass('scope_opened')) {
            node.addClass('scope_opened');
            node.find('.ETV_EnterLink').switchClass('right', 'down');
        }
        etv_window.find('.scope-' + node.data('scope')).each(function () {
            let node_type = $(this).data('type');
            if (node_type === 'function call' || node_type === 'action') {
                $(this).show();
                show_scope_shift($(this));
            }
            // Triangle should be shown for the opened scope if it exists
            else if (node_type === 'exit') $(this).show();

            // Notes, statements and declarations are shown by show_display()
        });
        show_display(node);
    }

    function show_display(node) {
        node.find('.ETV_OpenEye').switchClass('unhide', 'hide');
        node.find('.ETV_Display').hide();
        node.find('.ETV_Source').show();

        let node_type = node.data('type');

        // Show statements/declarations/notes if scope is shown
        if ((node_type === 'function call' || node_type === 'action') && node.hasClass('scope_opened')) {
            // If the statement/declaration is commented, then it is shown by its note click
            etv_window.find('.scope-' + node.data('scope') + '[data-type="statement"]').not('.commented').show();
            etv_window.find('.scope-' + node.data('scope') + '[data-type="declaration"]').not('.commented').show();

            // All notes should be shown in the scope
            etv_window.find('.scope-' + node.data('scope') + '[data-type="note"]').show();
        }
        // Show notes and not commented declarations
        else if (node_type === 'declarations') {
            etv_window.find('.scope-' + node.data('scope')).not('.commented').show()
        }
    }

    function hide_display(node) {
        node.find('.ETV_OpenEye').switchClass('hide', 'unhide');
        node.find('.ETV_Display').show();
        node.find('.ETV_Source').hide();

        let node_type = node.data('type');

        // Hide statements without comments if scope is shown
        if ((node_type === 'function call' || node_type === 'action') && node.hasClass('scope_opened')) {
            let prev_note_shown = false;
            etv_window.find('.scope-' + node.data('scope')).each(function () {
                let child_type = $(this).data('type');
                if (child_type === 'statement' || child_type === 'declaration') {
                    // Hide statement/declaration without note or if its note was hidden
                    if (!prev_note_shown) $(this).hide();
                    prev_note_shown = false;
                }
                else if (child_type === 'note') {
                    if ($(this).data('level') > 1) {
                        $(this).hide();
                        prev_note_shown = false;
                    }
                    else prev_note_shown = true;
                }
                else prev_note_shown = false;
            });
        }
        else if (node_type === 'declarations') {
            etv_window.find('.scope-' + node.data('scope')).hide()
        }
    }

    $('.ETV_EnterLink').click(function (event) {
        let node = $(this).parent().parent();
        if (node.hasClass('scope_opened')) {
            hide_scope(node, event.shiftKey, true);
        }
        else {
            if (event.shiftKey) show_scope_shift(node);
            else show_scope(node);
        }
    });
    $('.ETV_ExitLink').click(function (event) {
        let node = $('span[data-scope="' + $(this).data('scope') + '"]').first();
        hide_scope(node, event.shiftKey, true);
    });

    $('.ETV_OpenEye').click(function () {
        let node = $(this).parent().parent();
        if ($(this).hasClass('hide')) hide_display(node);
        else show_display(node);
    });

    $('.ETV_Declarations_Text').click(function () {
        $(this).parent().find('.ETV_OpenEye').click();
    });

    $('.ETV_LINE').click(function () {
        // Unselect everything first
        unselect_etv_line();

        let node = $(this).parent().parent();
        // Select clicked line
        node.addClass('ETVSelectedLine');

        // Get source code if node has file and line number
        let line_num = parseInt($(this).text(), 10),
            filename = $(this).data('file');
        if (filename && line_num) source_processor.get_source(line_num, filename);

        // Show assumptions
        if (data_window.length) {
            // Show old assumptions
            let old_assumes = node.find('.ETV_OldAssumptions');
            if (old_assumes.length) {
                $.each(old_assumes.text().split('_'), function (i, v) {
                    let curr_assume = $('#assumption_' + v);
                    if (curr_assume.length) data_window.append($('<p>', {text: curr_assume.text()}));
                });
            }
            // Show new assumptions
            let new_assumes = node.find('.ETV_NewAssumptions');
            if (new_assumes.length) {
                $.each(new_assumes.text().split('_'), function (i, v) {
                    let curr_assume = $('#assumption_' + v);
                    if (curr_assume.length) data_window.append($('<span>', {
                        text: curr_assume.text(), 'class': 'ETV_NewAssumption'
                    }));
                });
            }
        }
    });

    $('.ETV_Action,.ETV_RelevantAction').click(function () {
        let node = $(this).parent().parent();

        // If action can be collapsed/expanded, do it
        node.find('.ETV_EnterLink').click();

        // Get source for the action
        node.find('.ETV_LINE').click();
    });

    $('.ETV_ShowCommentCode').click(function () {
        let node = $(this).parent().parent().next('span');
        if (node.is(':hidden')) {
            node.show();
            // If next node is function call with allowed collapsing then that node will have enter link, click it
            node.find('.ETV_EnterLink').click();
            node.find('.ETV_LINE').click();
        }
        else {
            // Collapse the scope first
            if (node.hasClass('scope_opened')) node.find('.ETV_EnterLink').click();
            node.hide();
        }
    });

    $('.ETV_LINE_Note').click(function () {
        $(this).parent().parent().next('span').find('.ETV_LINE').click();
        $(this).addClass('ETV_LINE_Note_Selected');
    });

    etv_window.scroll(function () {
        $(this).find('.ETV_LN').css('left', $(this).scrollLeft());
    });

    // Click error trace first found line
    let file_name = getUrlParameter('source'), file_line = getUrlParameter('sourceline');
    if (file_name) {
        source_processor.get_source(file_line, file_name);
        history.replaceState([file_name, file_line], null, window.location.href);
    }
    else {
        etv_window.children().each(function () {
            if ($(this).is(':visible')) {
                let line_link = $(this).find('.ETV_LINE');
                if (line_link.length && parseInt(line_link.text(), 10)) {
                    etv_window.scrollTop(etv_window.scrollTop() + $(this).position().top - etv_window.height() * 3/10);
                    line_link.click();
                    return false;
                }
            }
        });
    }

    // Initialize coverage
    new CoverageProcessor(source_processor, '#CoverageDataContent', '#CoverageStatisticsTable', unselect_etv_line);
});
