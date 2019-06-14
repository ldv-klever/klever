/*
 * Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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
        source_window = $('#ETV_source_code'),
        sources_history = $('#sources_history'),
        src_back_btn = $('#ETVSourceBack');
    if (!etv_window.length) return false;

    function init_source_code() {
        let source_references_div = source_window.find('#source_references_links');

        $('.ETVRefToLink').click(function () {
            $('.ETVSelectedLine').removeClass('ETVSelectedLine');
            $('.ETV_LN_Note_Selected').removeClass('ETV_LN_Note_Selected');
            $('.ETV_LN_Warning_Selected').removeClass('ETV_LN_Warning_Selected');

            let assume_window = $('#ETV_assumes');
            if (assume_window.length) assume_window.empty();

            let line_num = parseInt($(this).data('line')),
                file_name = $(this).data('file');
            if (file_name === null) {
                file_name = $('#ETVSourceTitleFull').text()
            }
            else {
                file_name = source_window.find('#source_file_' + file_name).text();
            }
            get_source_code(line_num, file_name);
        });
        $('.ETVRefFromLink').popup({
            popup: '#source_references_links',
            onShow: function (activator) {
                let data_html = source_window.find('#' + $(activator).data('id')).html();
                source_references_div.html(data_html);
                source_references_div.find('.ETVRefLink').click(function () {
                    get_source_code($(this).data('line'), $(this).data('file'));
                })
            },
            onHide: function () {
                source_references_div.empty();
            },
            position: 'bottom left',
            hoverable: true,
            inline: true,
            delay: {
                show: 100,
                hide: 300
            }
        });
    }

    function select_source_line(line) {
        let selected_src_line = $(`#SrcL_${line}`);
        if (selected_src_line.length) {
            source_window.scrollTop(source_window.scrollTop() + selected_src_line.position().top - source_window.height() * 3/10);
            selected_src_line.find('.SrcLineCov').addClass('SrcLineSelected');
        }
        else err_notify($('#error___line_not_found').text());
    }

    function get_source_code(line, filename, save_history=true) {
        if (save_history) {
            sources_history.append($('<span>').data('file', filename).data('line', line));
            if (sources_history.children().length > 1 && src_back_btn.hasClass('disabled')) src_back_btn.removeClass('disabled');
        }
        if (filename === $('#ETVSourceTitleFull').text()) {
            source_window.find('.SrcLineSelected').removeClass('SrcLineSelected');
            select_source_line(line);
        }
        else {
            $.ajax({
                url: $('#source_url').val(),
                type: 'GET',
                data: {file_name: encodeURIComponent(filename)},
                success: function (resp) {
                    source_window.html(resp);
                    let title_place = $('#ETVSourceTitle');
                    title_place.text(filename);
                    title_place.popup({content: filename});
                    $('#ETVSourceTitleFull').text(filename);
                    select_source_line(line);
                    init_source_code();
                }
            });
        }
    }

    $('.ETV_GlobalExpander').click(function (event) {
        event.preventDefault();
        let global_icon = $(this).find('i').first();
        if (global_icon.hasClass('unhide')) {
            global_icon.removeClass('unhide').addClass('hide');
            etv_window.find('.scope-global:not(.commented)').show();
        }
        else {
            global_icon.removeClass('hide').addClass('unhide');
            etv_window.find('.scope-global:not([data-type="comment"])').hide();
        }
    });

    function show_scope(node) {
        if (!node.hasClass('scope_opened')) {
            node.addClass('scope_opened');
            node.find('.ETV_EnterLink').switchClass('right', 'down');
        }
        let parent_display = node.find('.ETV_OpenEye').hasClass('hide');
        etv_window.find('.scope-' + node.data('scope')).each(function () {
            let node_type = $(this).data('type');

            if (node_type === 'statement') {
                if (parent_display && !$(this).hasClass('commented')) $(this).show();
            }
            else if (node_type === 'function call' || node_type === 'action') {
                let has_note = $(this).hasClass('commented'),
                    was_opened = $(this).hasClass('scope_opened');

                // Actions can't have notes so it is always shown here
                if (!has_note || was_opened) $(this).show();

                // Open scope if it was opened earlier
                if (was_opened) show_scope($(this));
            }
            else $(this).show();  // note or exit
        });
    }

    function hide_scope(node, shift_pressed, change_state) {
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
        });
    }

    function show_scope_shift(node) {
        if (!node.hasClass('scope_opened')) {
            node.addClass('scope_opened');
            node.find('.ETV_EnterLink').switchClass('right', 'down');
        }
        etv_window.find('.scope-' + node.data('scope')).each(function () {
            let node_type = $(this).data('type');
            if (node_type === 'statement') {
                // Even on shift click statements with notes are not shown
                if (!$(this).hasClass('commented')) $(this).show();
            }
            else if (node_type === 'function call' || node_type === 'action') {
                $(this).show();
                show_scope_shift($(this));
            }
            else $(this).show();  // note or exit
        });
    }
    function show_display(node) {
        node.find('.ETV_OpenEye').switchClass('unhide', 'hide');
        node.find('.ETV_Display').hide();
        node.find('.ETV_Source').show();

        let node_type = node.data('type');

        // Show statements without comments if scope is shown
        if ((node_type === 'function call' || node_type === 'action') && node.hasClass('scope_opened')) {
            etv_window.find('.scope-' + node.data('scope') + '[data-type="statement"]').not('.commented').show()
        }
    }
    function hide_display(node) {
        node.find('.ETV_OpenEye').switchClass('hide', 'unhide');
        node.find('.ETV_Display').show();
        node.find('.ETV_Source').hide();

        let node_type = node.data('type');
        // Hide statements without comments if scope is shown
        if ((node_type === 'function call' || node_type === 'action') && node.hasClass('scope_opened')) {
            etv_window.find('.scope-' + node.data('scope') + '[data-type="statement"]').not('.commented').hide()
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

    $('.ETV_LINE').click(function () {
        let node = $(this).parent().parent();

        // Unselect everything first
        etv_window.find('.ETVSelectedLine').removeClass('ETVSelectedLine');
        etv_window.find('.ETV_LN_Note_Selected').removeClass('ETV_LN_Note_Selected');
        etv_window.find('.ETV_LN_Warning_Selected').removeClass('ETV_LN_Warning_Selected');

        // Select clicked line
        node.addClass('ETVSelectedLine');

        // Get source code if node has file and line number
        let line_num = parseInt($(this).text(), 10),
            filename = $(this).data('file');
        if (filename && line_num) get_source_code(line_num, filename);

        // Show assumptions
        let assume_window = $('#ETV_assumes');
        if (assume_window.length) {
            assume_window.empty();

            // Show old assumptions
            let old_assumes = node.find('.ETV_OldAssumptions');
            if (old_assumes.length) {
                $.each(old_assumes.text().split('_'), function (i, v) {
                    let curr_assume = $('#assumption_' + v);
                    if (curr_assume.length) assume_window.append($('<p>', {text: curr_assume.text()}));
                });
            }
            // Show new assumptions
            let new_assumes = node.find('.ETV_NewAssumptions');
            if (new_assumes.length) {
                $.each(new_assumes.text().split('_'), function (i, v) {
                    let curr_assume = $('#assumption_' + v);
                    if (curr_assume.length) assume_window.append($('<span>', {
                        text: curr_assume.text(), 'class': 'ETV_NewAssumption'
                    }));
                });
            }
        }
    });

    $('.ETV_Action').click(function () {
        let node = $(this).parent().parent(), enter_link = node.find('.ETV_EnterLink');
        // If action can be collapsed/expanded, do it
        if (enter_link.length) enter_link.click();
        // Get source for the action
        node.find('.ETV_LINE').click();
    });
    $('.ETV_CallbackAction').click(function () {
        // Callback actions are always shown
        // Get source for the callback action
        $(this).parent().parent().find('.ETV_LINE').click();
    });

    $('.ETV_La').click(function (event) {
        event.preventDefault();
        $('.ETVSelectedLine').removeClass('ETVSelectedLine');
        $('.ETV_LN_Note_Selected').removeClass('ETV_LN_Note_Selected');
        $('.ETV_LN_Warning_Selected').removeClass('ETV_LN_Warning_Selected');
        if ($(this).next('span.ETV_File').length) {
            get_source_code(parseInt($(this).text()), $(this).next('span.ETV_File').text());
        }
        let whole_line = $(this).parent().parent();
        whole_line.addClass('ETVSelectedLine');

        let assume_window = $('#ETV_assumes');
        if (assume_window.length) {
            assume_window.empty();
            whole_line.find('span[class="ETV_CurrentAssumptions"]').each(function () {
                let assume_ids = $(this).text().split(';');
                $.each(assume_ids, function (i, v) {
                    let curr_assume = $('#' + v);
                    if (curr_assume.length) {
                        assume_window.append($('<span>', {
                            text: curr_assume.text(),
                            style: 'color: red'
                        })).append($('<br>'));
                    }
                });
            });
            whole_line.find('span[class="ETV_Assumptions"]').each(function () {
                let assume_ids = $(this).text().split(';');
                $.each(assume_ids, function (i, v) {
                    let curr_assume = $('#' + v);
                    if (curr_assume.length) {
                        assume_window.append($('<span>', {
                            text: curr_assume.text()
                        })).append($('<br>'));
                    }
                });
            });
        }
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

    $('.ETV_LN_Note').click(function () {
        $(this).parent().next('span').find('.ETV_LINE').click();
        $(this).addClass('ETV_LN_Note_Selected');
    });
    $('.ETV_LN_Warning').click(function () {
        $(this).parent().next('span').find('.ETV_LINE').click();
        $(this).addClass('ETV_LN_Warning_Selected');
    });

    etv_window.scroll(function () {
        $(this).find('.ETV_LN').css('left', $(this).scrollLeft());
    });
    source_window.scroll(function () {
        $(this).find('.ETVSrcL').css('left', $(this).scrollLeft());
    });

    etv_window.children().each(function () {
        if ($(this).is(':visible')) {
            let line_link = $(this).find('.ETV_LINE');
            if (line_link.length) {
                etv_window.scrollTop(etv_window.scrollTop() + $(this).position().top - etv_window.height() * 3/10);
                line_link.click();
                return false;
            }
        }
    });

    src_back_btn.click(function () {
        if (sources_history.children().length > 1) {
            let last_child = sources_history.children().last(), prev_child = last_child.prev();
            get_source_code(prev_child.data('line'), prev_child.data('file'), false);
            last_child.remove();
        }
        if (sources_history.children().length < 2) src_back_btn.addClass('disabled');
    });

    source_window.on('mouseenter', '.SrcLineCov[data-value]', function () {
        $(this).append($('<span>', {'class': 'SrcNumberPopup', text: $(this).data('value')}));
    });
    source_window.on('mouseleave', '.SrcLineCov[data-value]', function () {
        $(this).find('.SrcNumberPopup').remove();
    });
    source_window.on('mouseenter', '.SrcFuncCov[data-value]', function () {
        $(this).append($('<span>', {'class': 'SrcNumberPopup', text: $(this).data('value')}));
    });
    source_window.on('mouseleave', '.SrcFuncCov[data-value]', function () {
        $(this).find('.SrcNumberPopup').remove();
    });
    source_window.on('mouseenter', '.SrcCode[data-value]', function () {
        $(this).siblings('.SrcLine').find('.SrcLineCov')
            .append($('<span>', {'class': 'SrcNumberPopup', text: $(this).data('value')}));
    });
    source_window.on('mouseleave', '.SrcCode[data-value]', function () {
        $(this).siblings('.SrcLine').find('.SrcNumberPopup').remove();
    });
});
