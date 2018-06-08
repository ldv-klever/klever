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
        return this.selectionStart != this.selectionEnd;
    };

    // Tab space
    var tabspace = "    ", tablen = tabspace.length;
    textarea[0].onkeydown = function(event) {
        var caret_pos = textarea[0].selectionStart, text_value;
        // Tab
        if (event.keyCode == 9) {
            event.preventDefault();
            text_value = textarea.val();
            textarea.val(text_value.substring(0, caret_pos) + tabspace + text_value.substring(caret_pos, text_value.length));
            textarea[0].setCaretPosition(caret_pos + tablen);
            return false;
        }
        // Backspace
        if (event.keyCode == 8 && textarea.val().substring(caret_pos - tablen, caret_pos) == tabspace && !textarea[0].hasSelection()) {
            // it's a tab space
            event.preventDefault();
            text_value = textarea.val();
            textarea.val(text_value.substring(0, caret_pos - tablen) + text_value.substring(caret_pos, text_value.length));
            textarea[0].setCaretPosition(caret_pos - tablen);
        }
    }
}

window.linedTextEditor = function(editor_id) {

    var editor = $('#' + editor_id);
    editor.wrap('<div class="lined-textarea-container"></div>');
    editor.addClass('lined-textarea');

    var container = editor.parent();
    container.prepend('<div class="lines"></div>');

    var lines = container.find('.lines');
    lines.append('<div class="linesContainer"></div>');

    var lines_container = lines.find('.linesContainer');

    var linesNum = numberOfLines(lines_container, lines.height(), 1);
    editor.scroll(function () {
        var top_pos = editor.scrollTop();
        lines_container.css({"margin-top": -1 * top_pos + "px"});
        linesNum = numberOfLines(lines_container, top_pos + editor.height(), linesNum);
    });
    onTabPressed(editor);
};
