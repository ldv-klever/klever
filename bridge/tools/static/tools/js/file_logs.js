jQuery(function () {
    let log_selector = $('#log_file_selector'),
        log_container = $('#log_container'),
        position = 0, interval;
    log_selector.dropdown();

    function create_interval(log_name) {
        return setInterval(function () {
            let url = get_url_with_get_parameters(PAGE_URLS.get_log_content, {name: log_name, position: position});
            $.get(url, {}, function (resp) {
                if (position !== resp['position'] || resp['reload']) {
                    if (resp['reload']) log_container.text(resp['content']);
                    else log_container.append(document.createTextNode(resp['content']));

                    log_container.animate({scrollTop: log_container.prop("scrollHeight")}, 500);
                    position = resp['position'];
                }
            }).fail(function () {
                clear_interval()
            });
        }, 5000);
    }

    function clear_interval() {
        if (!interval) return false;
        clearInterval(interval);
        log_container.empty();
        position = 0;
        interval = null;
    }

    function load_log_content(log_name) {
        clear_interval();

        $('#dimmer_of_log_content').addClass('active');

        let url = get_url_with_get_parameters(PAGE_URLS.get_log_content, {name: log_name});
        $.get(url, {}, function (resp) {
            position = resp['position'];
            log_container.text(resp['content']);
            $('#dimmer_of_log_content').removeClass('active');

            log_container.animate({ scrollTop: log_container.prop("scrollHeight")}, 1000);
            interval = create_interval(log_name);
        });
    }

    load_log_content(log_selector.val());

    log_selector.on('change', function () {
        load_log_content($(this).val());
    });

    $('#clear_log_btn').click(function () {
        clear_interval();

        $('#dimmer_of_page').addClass('active');
        let url = get_url_with_get_parameters(PAGE_URLS.clear_log, {
            name: encodeURIComponent(log_selector.val())
        });

        $.ajax({
            url: url,
            method: 'DELETE',
            success: function () {
                $('#dimmer_of_page').removeClass('active');
            }
        });
    });
});