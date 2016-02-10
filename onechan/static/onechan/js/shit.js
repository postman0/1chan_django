'use strict';
(function(){
	// taken from Django docs
	function getCookie(name) {
	    var cookieValue = null;
	    if (document.cookie && document.cookie != '') {
	        var cookies = document.cookie.split(';');
	        for (var i = 0; i < cookies.length; i++) {
	            var cookie = $.trim(cookies[i]);
	            // Does this cookie string begin with the name we want?
	            if (cookie.substring(0, name.length + 1) == (name + '=')) {
	                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
	                break;
	            }
	        }
	    }
	    return cookieValue;
	}

	var csrftoken = getCookie('csrftoken');
	$.ajaxSettings.headers = {'X-CSRFToken': csrftoken};

	var secure = (window.location.protocol.search(/https/) != -1) ? 's' : '';
	var ws = new WebSocket("ws" + secure + "://" + window.location.host + "/ws");
	ws.onopen = function(e) {
		console.log(e);
		if (window.wsRoom) {
			ws.send(JSON.stringify({
				type: 'join',
				room: window.wsRoom
			}));
		};
	};
	ws.onmessage = function(e) {
		var msg = JSON.parse(e.data);
		switch (msg.type) {
			case "count": {
				if (msg.room == 'default') {
					$('#stats_online').text(msg.data.count);
				} else {
					$('#post_stats_reading').text(msg.data.count);
				}
				break;
			}
			case "new_comment": {
				var node = $(msg.data.html);
				$('.comments').append(node);
				$('#last_comments_new').prepend(node);
				break;
			}
			case "writer_count": {
				$('#post_stats_writing').text(msg.data.count);
				break;
			}
			case "new_rating": {
				var elemColl = $('#post_rating_' + msg.data['post_id'].toString());
				elemColl.removeClass('post-rating-positive post-rating-negative');
				elemColl.addClass(msg.data.rating >= 0 ? 'post-rating-positive' : 'post-rating-negative');
				elemColl.text(msg.data.rating);
				break;
			}
		};
	};

	var sendWritingState = function(state) {
		return function(e) {
			ws.send(JSON.stringify({
				type: 'writing',
				room: window.wsRoom,
				data: {state: state}
			}));
		};
	}
	$('#comment_form_text').on({
		focus: sendWritingState(true),
		blur: sendWritingState(false)
	})

	$('#comment_form').submit(function(e){
		$.ajax({
			type: 'post',
			url: e.target.action,
			data: $(e.target).serializeArray(),
			complete: function(xhr, status) {
				var resp = JSON.parse(xhr.responseText);
				console.log(resp);
				$('#comment_form_error_captcha').text('');
				$('#comment_form_error_text').text('');
				if (resp.success) {
					$('#id_text').val('');
				} else {
					$.each(resp.errors, function(key, val){
						$('#comment_form_error_'+key).text(val);
					});
				};
				window.grecaptcha.reset();
			},
			dataType: 'json',
		});
		e.preventDefault();
	});

	$('.post-rate-buttons').click(function(e){
		var value = parseInt(e.target.dataset.rateValue);
		var url = e.currentTarget.dataset.rateUrl;
		$.ajax({
			type: 'POST',
			url: url,
			data: {'value': value},
			complete: function(xhr, status) {
			}
		});
		e.preventDefault();
	});

	$('.favourite-icon').click(function(e){
		var value = !(e.target.dataset.favouriteCurrentValue === '1');
		var url = e.target.dataset.favouriteUrl;
		var id = e.target.id;
		$.ajax({
			type: 'POST',
			url: url,
			data: {'value': value},
			complete: function(xhr, status) {
				var resp = JSON.parse(xhr.responseText);
				console.log(id);
				if (resp.success) {
					var elem = $("#post_"+id);
					if (value) {
						elem.removeClass('favourite-icon-disabled');
						elem.addClass('favourite-icon-active');
						elem.data('favouriteCurrentValue', '1');
					} else {
						elem.removeClass('favourite-icon-active');
						elem.addClass('favourite-icon-disabled');
						elem.data('favouriteCurrentValue', '0');
					}
				};
			}
		});
		e.preventDefault();
	});

	$(document).on('mouseenter', '.comment-ref', function(e) {
		$.ajax({
			type: 'GET',
			url: e.target.dataset.commentUrl,
			complete: function(xhr, status) {
				var resp = JSON.parse(xhr.responseText);
				console.log(resp);
				if (resp.success) {
					var cont = $('<div class="comment-ref-preview"></div>');
					cont.append(resp.html);

					cont.css('left', e.pageX + 2);
					cont.css('top', e.pageY + 2);

					cont.on('mouseleave', function(e) {
						if (e.target != cont[0])
							return;
						var timeoutId = window.setTimeout(function() {
							cont.remove();
						}, 500);
						cont.data('hideTimeoutId', timeoutId);
					});
					cont.on('mouseenter', function(e) {
						if (e.target != cont[0])
							return;
						var timeoutId = cont.data('hideTimeoutId');
						console.log(timeoutId);
						if (timeoutId) {
							window.clearTimeout();
						};
					});

					cont.appendTo('#comment_ref_previews');
				};
			}
		});
	});

	$('#news_addform_category').select2({
		allowClear: true,
		width: "50%",
		tags: true,
	});


	var formatHomeboardChoice = function(sel) {
		if (sel.element) {
			return $('<span><img class="select2-homeboard-icon" src="' + sel.element.dataset.boardIcon +
				'">' + sel.text + '</span>');
		} else {
			return sel.text;
		}
	};

	$('#homeboard_select').select2({
		allowClear: true,
		width: "100%",
		templateResult: formatHomeboardChoice,
	})

})();