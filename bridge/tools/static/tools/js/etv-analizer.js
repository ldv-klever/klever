function SourceProcessor() {
    return this;
}

SourceProcessor.prototype.initialize = function() {
}

SourceProcessor.prototype.get_source = function() {
}

function CoverageProcessor() {
    return this;
}

jQuery(function () {
    const trace_selector = $('#error_trace_selector'),
        show_trace_btn = $('#show_error_trace');
    trace_selector.dropdown();
    show_trace_btn.click(function () {
        window.location.href = trace_selector.val();
    });
});