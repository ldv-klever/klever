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

function numberOfLines(linesContainer, linesHeight, lineNo) {
    while (linesContainer.height() < linesHeight) {
        linesContainer.append('<div class="line-number">' + lineNo + '</div>');
        lineNo++;
    }
    return lineNo;
}

function onTabPressed(textarea) {
    HTMLTextAreaElement.prototype.setCaretPosition = function (position) {
        this.selectionStart = position;
        this.selectionEnd = position;
        this.focus();
        return this;
    };
    HTMLTextAreaElement.prototype.hasSelection = function () {
        return this.selectionStart !== this.selectionEnd;
    };

    // Tab space
    const tabspace = "    ", tablen = tabspace.length;
    textarea[0].onkeydown = function(event) {
        let caret_pos = textarea[0].selectionStart, text_value;
        // Tab
        if (event.keyCode === 9) {
            event.preventDefault();
            text_value = textarea.val();
            textarea.val(text_value.substring(0, caret_pos) + tabspace + text_value.substring(caret_pos, text_value.length));
            textarea[0].setCaretPosition(caret_pos + tablen);
            return false;
        }
        // Backspace
        if (event.keyCode === 8 && textarea.val().substring(caret_pos - tablen, caret_pos) === tabspace && !textarea[0].hasSelection()) {
            // it's a tab space
            event.preventDefault();
            text_value = textarea.val();
            textarea.val(text_value.substring(0, caret_pos - tablen) + text_value.substring(caret_pos, text_value.length));
            textarea[0].setCaretPosition(caret_pos - tablen);
        }
    }
}

window.linedTextEditor = function(editor_id) {
    console.log(1);
    let editor = $('#' + editor_id);
    editor.wrap('<div class="lined-textarea-container"></div>');
    editor.addClass('lined-textarea');
    console.log(2);
    let container = editor.parent();
    container.prepend('<div class="lines"></div>');
    console.log(3);
    let lines = container.find('.lines');
    lines.append('<div class="linesContainer"></div>');
    console.log(4);
    let lines_container = lines.find('.linesContainer');

    console.log('Get number of lines');
    let linesNum = numberOfLines(lines_container, lines.height(), 1);
    console.log(linesNum);
    editor.scroll(function () {
        let top_pos = editor.scrollTop();
        lines_container.css({"margin-top": -1 * top_pos + "px"});
        linesNum = numberOfLines(lines_container, top_pos + editor.height(), linesNum);
    });
    onTabPressed(editor);
};
