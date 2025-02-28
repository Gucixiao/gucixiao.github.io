// Stop autosave
Config.saves.maxAutoSaves = 0;

// Limit the history to 20
Config.history.maxStates = 20;

// Set clicking event to close the pages
$(document).click(function (e) {
    // Check if the click is outside of #menu-button or #page-container
    if (!$(e.target).closest("#menu-button").length && !$(e.target).closest("#page-container").length) {
        $("#page-container").addClass("hidden");
    }
});


//点击任何位于.passage的链接都将触发<<refreshSidbar>> widget
$(document).click(function (e) {
    if (!$(e.target).closest("#ui-bar").length && $(e.target).is("a")) {
        $.wiki('<<refreshSidebar>>')
    }
});

/* ============================================ */
/* imported js */
/*=====================================================*/
/* twine-user-script #88: "tooltip.js" */
/* eslint-disable no-new */
/* The main purpose for this jQuery plugin was to enable tooltips for dynamically created elements, by using jQuery
	However, I also added a [tooltip] attribute to be used with an html element, which is more flexible than the old tooltip.

	Example usage: (jquery)
	jqueryElement.tooltip({
		message: "Here is a tooltip",
		delay: 200,
		position: "cursor",
	});

	Enable or disable it:
	jqueryElement.tooltip("enable");
	jqueryElement.tooltip("disable");

	Change message to an already existing tooltip:
	jqueryElement.tooltip({ message: "New message" });


	Example usage: (html)
	<div tooltip="Here is a tooltip" id="someid" class="someclass">
		Content here
	</div>

	Example usage (with added span for separate styles for the tooltip - and sugarcube variable)
	<div tooltip="Here is a tooltip:<span class='yellow'>Current pepper sprays: $spray</span>">
		Pepper sprays
	</div>

	Example usage (with customised settings):
	<div tooltip="Tooltip text" tooltip-title="Title" tooltip-position="bottom">
		Pepper sprays
	</div>


	---------------------------------------------------
	Styling: (tooltip.css)
	.tooltip-popup - The container for the tooltip
	.tooltip-header - An optional title property
	.tooltip-body - The tooltip text
	- Anchor styling can be changed with the property "anchorStyle" (anchor = the object to hover over to display the tooltip)

	Settings:
		title: A bigger title text - default null
		message: The actual tooltip content
		anchorStyle: Optional css class for the anchor
		position: Position of the tooltip. Options: cursor, top, bottom, left, right, bottomRight, bottomLeft, topRight, topLeft
		cursor: Cursor styling when hovering over the anchor
		delay: Optional delay - default 150ms)
		width: Optional width of the tooltip. If set to null, it will resize itself based on the content
		maxWidth: Optional max width of the tooltip. When it reaches this width, text will wrap to the next row
*/

const tooltipRegistry = [];

/* Clears tooltips on passage start - in case a tooltip is displayed during passage change */
$(document).on(":passageinit", () => {
	tooltipRegistry.forEach(function (tooltipElement) {
		$(tooltipElement).trigger("mouseleave.tooltip");
	});
	tooltipRegistry.splice(0, tooltipRegistry.length);
});

$(document).on(":passageend", () => {
	initializeTooltips();
});

/*
  This is basically a failsafe for the shop (and other places with <<replace>>)
  If a popup is displayed while a <<replace>> widget is called, we remove it here
*/
function initializeTooltips() {
	$(".tooltip-popup").remove();
	$(() => {
		$("[tooltip]").each(function () {
			const message = $("<div>");
			new Wikifier(message, $(this).attr("tooltip"));

			// Default attribute settings
			const defaultSettings = {
				title: "",
				message,
				anchorStyle: null,
				position: "cursor",
				cursor: "help",
				delay: 150,
				width: null,
			};

			/*
			  Extracts the attributes that are prefixed with "tooltip", in order to customise the tooltips from html
			  Any of the above settings can be customised
			*/
			$.each(this.attributes, function () {
				if (!this.name.startsWith("tooltip-")) return;
				if (!Object.hasOwn(defaultSettings, this.name.substring(8))) return;

				const key = this.name.substring(8);
				if (isNaN(this.value)) return;
				defaultSettings[key] = parseFloat(this.value);
			});

			$(this).tooltip(defaultSettings);
		});
	});
}
window.initializeTooltips = initializeTooltips;

/*
  Extends jQuery to allow custom tooltips for any jQuery objects
*/
$.fn.tooltip = function (options = {}) {
	const initializeSettings = () => {
		const existingSettings = this.data("tooltip-settings");
		if (existingSettings) {
			$.extend(existingSettings, options);
			return existingSettings;
		}

		const defaults = {
			title: "",
			message: "",
			delay: 150,
			position: "cursor",
			cursor: "help",
			style: null,
			anchorStyle: null,
			width: null,
		};
		return $.extend({}, defaults, options);
	};

	const show = function () {
		const settings = initializeSettings.call(this);
		this.data("tooltip-settings", settings);
		const $this = $(this);
		const disabled = $this.data("tooltip-disabled");
		if (disabled) return;

		let tooltip = $this.data("tooltip-instance");

		if (settings.position.toLowerCase() === "cursor") {
			$this.on("mousemove.tooltip", function (event) {
				$this.data("cursorPosition", { x: event.pageX, y: event.pageY });
				updatePosition.call($this, tooltip);
			});
		}

		// Optionally delay the tooltip, if a delay is set
		clearTimeout($this.data("tooltip-timeout"));
		const timeout = setTimeout(() => {
			if (!$.contains(document, $this[0])) return;
			tooltip = $("<div>").addClass("tooltip-popup");
			const header = $("<div>").addClass("tooltip-header").html(settings.title);
			const body = $("<div>").addClass("tooltip-body");
			if (settings.message instanceof DocumentFragment) {
				body.append(settings.message);
			} else {
				body.html(settings.message);
			}
			if (settings.style) body.addClass(settings.style);
			tooltip.append(header, body);
			if (settings.width) tooltip.css("width", settings.width);
			$("body").append(tooltip);
			$this.data("tooltip-instance", tooltip);
			updatePosition.call($this, tooltip);
		}, settings.delay);
		$this.data("tooltip-timeout", timeout);

		// Handler to update the tooltip position
		const resizeHandler = () => {
			if (settings.position.toLowerCase() !== "cursor") {
				updatePosition.call($(this), tooltip);
			}
		};
		$(this).data("resizeHandler", resizeHandler);
		$(window).on("resize", resizeHandler);
		tooltipRegistry.push(this);
	};

	const hide = function () {
		const settings = this.data("tooltip-settings");
		const $this = $(this);
		const tooltip = $this.data("tooltip-instance");
		clearTimeout($this.data("tooltip-timeout"));
		if (tooltip) {
			tooltip.remove();
			$this.removeData("tooltip-instance");
			const index = tooltipRegistry.indexOf(this);
			if (index > -1) {
				tooltipRegistry.splice(index, 1);
			}
		}
		if (settings.position.toLowerCase() === "cursor") {
			$this.off("mousemove.tooltip");
		}

		const resizeHandler = $(this).data("resizeHandler");
		if (resizeHandler) {
			$(window).off("resize", resizeHandler);
		}
	};

	const updateTooltip = function () {
		const $this = $(this);
		const settings = $this.data("tooltip-settings");
		const tooltip = $this.data("tooltip-instance");
		if (settings && tooltip) {
			tooltip.find(".tooltip-header").html(settings.title);
			tooltip.find(".tooltip-body").html(settings.message);
			updatePosition.call($this, tooltip);
		}
	};

	const updatePosition = function (tooltipInstance) {
		if (!tooltipInstance) return;

		const windowWidth = $(window).width();
		const distance = 3;
		const { left: offsetLeft, top: offsetTop } = this.offset();
		const { width, height } = this.get(0).getBoundingClientRect();
		const { x: cursorX, y: cursorY } = this.data("cursorPosition") || {};
		const offsetX = 15;
		const offsetY = 15;
		const position = (this.data("tooltip-settings") || {}).position?.toLowerCase() || "cursor";

		// Max width for mobile devices to not go off-screen
		const maxWidth = Math.max(windowWidth - cursorX - offsetX - distance, 100);
		tooltipInstance.css("max-width", `${maxWidth}px`);

		let left = cursorX + offsetX;
		let top = cursorY + offsetY;

		if (position !== "cursor") {
			const tooltipWidth = tooltipInstance.outerWidth();
			const tooltipHeight = tooltipInstance.outerHeight();
			const centerHorizontal = offsetLeft + width / 2 - tooltipWidth / 2;
			const centerVertical = offsetTop + height / 2 - tooltipHeight / 2;

			switch (position) {
				case "top":
					left = centerHorizontal;
					top = offsetTop - tooltipHeight - distance;
					break;
				case "bottom":
					left = centerHorizontal;
					top = offsetTop + height + distance;
					break;
				case "left":
					left = offsetLeft - tooltipWidth - distance;
					top = centerVertical;
					break;
				case "right":
					left = offsetLeft + width + distance;
					top = centerVertical;
					break;
				case "bottomRight":
					left = offsetLeft + width - tooltipWidth - distance;
					top = offsetTop + height + distance;
					break;
				case "bottomLeft":
					left = offsetLeft + distance;
					top = offsetTop + height + distance;
					break;
				case "topRight":
					left = offsetLeft + width - tooltipWidth - distance;
					top = offsetTop - tooltipHeight - distance;
					break;
				case "topLeft":
					left = offsetLeft + distance;
					top = offsetTop - tooltipHeight - distance;
					break;
			}
		}

		// Adjust for window edges
		left = Math.min(left, windowWidth - tooltipInstance.outerWidth() - offsetX - distance);
		left = Math.max(left, distance);
		tooltipInstance.css("transform", `translate(${left}px, ${top}px)`);
	};

	// Enable or Disable tooltip
	if (options === "disable" || options === "enable") {
		this.each(function () {
			const $this = $(this);
			$this.data("tooltip-disabled", options === "disable");

			if (options === "disable") {
				$this.trigger("mouseleave.tooltip");
			} else if ($this.is(":hover")) {
				$this.trigger("mouseenter.tooltip");
				updateTooltip.call($this);
			}
		});
		return this;
	}

	// Event Handlers
	this.on("mouseenter.tooltip", function () {
		show.call($(this));
	}).on("mouseleave.tooltip", function () {
		hide.call($(this));
	});

	// Main logic
	this.each(function () {
		const $this = $(this);
		const settings = initializeSettings.call($this);
		$this.data("tooltip-settings", settings);

		if (settings.cursor) $this.css("cursor", settings.cursor);
		if (settings.anchorStyle) $this.addClass(settings.anchorStyle);
	});

	return this;
};


/* =======================================================  
notify.js, by chapel; for sugarcube 2
version 1.1.1
requires notify.css / notify.min.css
======================================================= 
*/
(function () {
    var DEFAULT_TIME = 2000; // default notification time (in MS)
    var isCssTime = /\d+m?s$/;

    $(document.body).append("<div id='notify'></div>");
    $(document).on(':notify', function (ev) {
        if (ev.message && typeof ev.message === 'string') {
            // trim message
            ev.message.trim();
            // classes
            if (ev.class) {
                if (typeof ev.class === 'string') {
                    ev.class = 'open macro-notify ' + ev.class;
                } else if (Array.isArray(ev.class)) {
                    ev.class = 'open macro-notify ' + ev.class.join(' ');
                } else {
                    ev.class = 'open macro-notify';
                }
            } else {
                ev.class = 'open macro-notify';
            }
            
            // delay
            if (ev.delay) {
                if (typeof ev.delay !== 'number') {
                    ev.delay = Number(ev.delay);
                }
                if (Number.isNaN(ev.delay)) {
                    ev.delay = DEFAULT_TIME;
                }
            } else {
                ev.delay = DEFAULT_TIME;
            }
            
            $('#notify')
                .empty()
                .wiki(ev.message)
                .addClass(ev.class);
                    
            setTimeout(function () {
                $('#notify').removeClass();
            }, ev.delay);
        }
    });

    function notify (message, time, classes) {
        if (typeof message !== 'string') {
            return;
        }

        if (typeof time !== 'number') {
            time = false;
        }

        $(document).trigger({
            type    : ':notify',
            message : message,
            delay   : time,
            class   : classes || ''
        });
    }

    // <<notify delay 'classes'>> message <</notify>>
    Macro.add('notify', {
           tags : null,
        handler : function () {
            
            // set up
            var msg     = this.payload[0].contents, 
                time    = false, 
                classes = false, i;
            
            // arguments
            if (this.args.length > 0) {
                var cssTime = isCssTime.test(this.args[0]);
                if (typeof this.args[0] === 'number' || cssTime) {
                    time    = cssTime ? Util.fromCssTime(this.args[0]) : this.args[0];
                    classes = (this.args.length > 1) ? this.args.slice(1).flat(Infinity) : false;
                } else {
                    classes = this.args.flat(Infinity).join(' ');
                }
            }
            
            // fire event
            notify(msg, time, classes);
            
        }
    });

    setup.notify = notify;
}());

/*====================================================== 
    typesim macro, by chapel; for sugarcube 2
    version 2.0.0
======================================================
*/
(function () {
    'use strict';

    function typeSim (content, $target, callback) {
        if (!content || typeof content !== 'string') {
            return;
        }

        if ($target && !($target instanceof $)) {
            $target = $($target);
        }

        var i = 0;
        var arrayify = content.split('');
        var message = [];

        var $textarea = $(document.createElement('textarea'))
            .addClass('type-sim')
            .on('input.type-sim', function () {
                var $self = $(this);
                i = message.push(arrayify[i]);
                $self.val(message.join(''));
                if (content.length === message.length) {
                    $self
                        .off('input.type-sim')
                        .ariaDisabled(true);
                    if (callback && typeof callback === 'function') {
                        callback(message.join(''));
                    }
                    $(document).trigger({ 
                        type : ':type-sim-end',
                        message : message.join('')
                    });
                }
            });

        if ($target && $target[0]) {
            $target.append($textarea);
        }

        return $textarea;
    }

    Macro.add('typesim', {
        tags : null,
        handler : function () {
            if (!this.args.length || !this.args[0] || typeof this.args[0] !== 'string') {
                return this.error('no text to type out was provided');
            }

            var $wrapper = $(document.createElement('span')).addClass('macro' + this.name);
            var $callbackOutput = $(document.createElement('div'));

            var wiki;
            if (this.payload[0].contents && this.payload[0].contents.trim()) {
                wiki = this.payload[0].contents;
            }

            function callback () {
                $callbackOutput.wiki(wiki);
            }

            typeSim(this.args[0], $wrapper, callback);

            $wrapper
                .append($callbackOutput)
                .appendTo($(this.output));
        }
    });

})();

/*======================================================
speech macro, by chapel; for sugarcube 2
v1.1.1
======================================================
*/
(function () {
    // v1.1.1
    'use strict';

    var characters = new Map();

    function addCharacter (name, displayname, icon) {
		if(icon === undefined && displayname){
			icon = displayname;
			displayname = null;
		}
        if (State.length) {
            throw new Error('addCharacter() -> must be called before story starts');
        }
        if (!name || !icon) {
            console.error('addCharacter() -> invalid arguments');
            return;
        }
        if (characters.has(name)) {
            console.error('addCharacter() -> overwriting character "' + name + '"');
        }
        characters.set(name, {displayName: displayname, image: icon});
    }

    function say ($output, character, text, imgSrc) {
        // 
        var $box = $(document.createElement('div'))
            .addClass(Util.slugify(character) + ' say');

			
        // portrait
        var _img = characters.has(character) ? characters.get(character).image : null;        
        var $img = $(document.createElement('img'))
            .attr('src', imgSrc || _img || '');

        if ($img.attr('src') && $img.attr('src').trim()) {
            $box.append($img);
        }

        // name and content boxes
		var _name =  character.toUpperFirst();
		if (characters.has(character) && characters.get(character).displayName) {
            _name = characters.get(character).displayName;
        }

        $box.append($(document.createElement('p'))
            .wiki(_name))
            .append($(document.createElement('p'))
                .wiki(text));

        if ($output) {
            if (!($output instanceof $)) {
                $output = $($output);
            }
            $box.appendTo($output);
        }

        return $box;
    }

    setup.say = say;
    setup.addCharacter = addCharacter;

    Macro.add('character', {
        // character macro
        handler : function () {
            addCharacter(this.args[0], this.args[1], this.args[2]);
        }
    });

    $(document).one(':passagestart', function () {
        // construct array of character names
        var names = Array.from(characters.keys());
        names.push('say');
        // generate macros
        Macro.add(names, {
            tags : null,
            handler : function () {
                if (this.name !== 'say') {
                    say(this.output, this.name, this.payload[0].contents);
                } else {
                    say(this.output, this.args[0], this.payload[0].contents, this.args[1]);
                }
            }
        });
    });
}());

/*======================================================
// dialog API macro set, by chapel; for sugarcube 2
// version 1.3.0
// see the documentation: https://github.com/ChapelR/custom-macros-for-sugarcube-2/blob/master/docs/dialog-api-macro-set.md
======================================================
*/
Macro.add('dialog', {
       tags : ['onopen', 'onclose'],
    handler : function () {
        
        // handle args (if any)
        var errors = [];
        var content = '', onOpen = null, onClose = null;
        var title = (this.args.length > 0) ? this.args[0] : '';
        var classes = (this.args.length > 1) ? this.args.slice(1).flat(Infinity) : [];

        this.payload.forEach( function (pl, idx) {
            if (idx === 0) {
                content = pl.contents;
            } else {
                if (pl.name === 'onopen') {
                    onOpen = onOpen ? onOpen + pl.contents : pl.contents;
                } else {
                    onClose = onClose ? onClose + pl.contents : pl.contents;
                }
            }
        });
        
        // add the macro- class
        classes.push('macro-' + this.name);
        
        // dialog box
        Dialog.setup(title, classes.join(' '));
        Dialog.wiki(content);

        // should these be shadowWrapper-aware?
        if (onOpen && typeof onOpen === 'string' && onOpen.trim()) {
            $(document).one(':dialogopened', function () {
                $.wiki(onOpen);
            });
        }

        if (onClose && typeof onClose === 'string' && onClose.trim()) {
            $(document).one(':dialogclosed', function () {
                $.wiki(onClose);
            });
        }

        Dialog.open();
        
    }

});

// <<popup>> macro
Macro.add('popup', {
    handler : function () {
        
        // errors
        if (this.args.length < 1) {
            return this.error('need at least one argument; the passage to display');
        }
        if (!Story.has(this.args[0])) {
            return this.error('the passage ' + this.args[0] + 'does not exist');
        }
        
        // passage name and title
        var psg   = this.args[0];
        var title = (this.args.length > 1) ? this.args[1] : '';
        var classes = (this.args.length > 2) ? this.args.slice(2).flat(Infinity) : [];
        
        // add the macro- class
        classes.push('macro-' + this.name);
        
        // dialog box
        Dialog.setup(title, classes.join(' '));
        Dialog.wiki(Story.get(psg).processText());
        Dialog.open();
        
    }

});

// <<dialogclose>> macro
Macro.add('dialogclose', { 
    skipArgs : true, 
    handler : function () {
        Dialog.close();
    } 
});