# JavaScript Development Guide

This guide covers JavaScript patterns and components for this project.

The project uses vanilla JavaScript with IIFEs (no bundler), data-attribute auto-initialization, and custom events for cross-component communication.


## Module Pattern

This project uses IIFEs (Immediately Invoked Function Expressions) rather than ES modules:

```javascript
(function () {
  'use strict';
  // Module code here - all variables are scoped to this function
})();
```

**Why IIFEs instead of ES modules:**
- No bundler required - works with Django's `collectstatic`
- Simple `<script defer>` loading without `type="module"` complexity
- No import path management (ES modules require full URLs, not bare specifiers)
- Works everywhere without CORS considerations

For a low-JS project like this, IIFEs are the pragmatic choice. If the project grows to need significant JS sharing between modules, consider adding a bundler (esbuild) and switching to ES modules.


## Script Loading

Always use `defer` when including scripts:

```html
<script src="{% static 'core/my_script.js' %}" defer></script>
```


## Cross-Module Communication

When JS modules need to communicate, use custom DOM events rather than globals:

```javascript
// Dispatch event on a specific element (preferred) or document
container.dispatchEvent(new CustomEvent('maintainer:selected', {
  detail: { maintainer, input }
}));

// Listen for event
container.addEventListener('maintainer:selected', (e) => {
  console.log(e.detail.maintainer);
});
```

**Do not use global callbacks** like `window.onSomething = function() {...}` or `data-on-select="globalFunctionName"`. These pollute the global namespace and create hidden coupling between modules. Custom events are explicit, discoverable, and don't require the listener to exist when the event is dispatched.


## Visibility Pattern

When toggling element visibility with JavaScript, use the `.hidden` class instead of `style.display`:

```html
<!-- In template -->
<div id="my-element" class="hidden">...</div>
```

```javascript
// In JavaScript - show element
element.classList.remove('hidden');

// Hide element
element.classList.add('hidden');
```

This keeps styling in CSS and makes the pattern consistent across the codebase.


## Data-Attribute Auto-Init Pattern

Most components use data attributes for configuration-driven initialization. The standard pattern:

1. Mark the root element with a data attribute (e.g., `data-file-accumulator`)
2. Query for all matching elements on `DOMContentLoaded`
3. Initialize each instance

```javascript
(function () {
  'use strict';

  function initMyComponent(container) {
    // Component logic here
    // Read configuration from data attributes
    const apiUrl = container.dataset.apiUrl;
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-my-component]').forEach(initMyComponent);
  });
})();
```

This pattern allows multiple instances per page and keeps HTML declarative.


## Component Catalog

All JavaScript files are in `the_flip/static/core/`.

### Core

| File | Purpose |
|------|---------|
| core.js | Utilities, dropdowns, clickable cards, smart dates |

### Autocomplete

| File | Purpose |
|------|---------|
| machine_autocomplete.js | Machine search with API-backed results |
| maintainer_autocomplete.js | Maintainer search with prefetched results |
| maintainer_chip_input.js | Multi-select chip input for maintainer selection |

### File & Media

| File | Purpose |
|------|---------|
| file_accumulator.js | Multi-file upload that accumulates across selections |
| media_grid.js | Media gallery with upload and delete |
| video_transcode_poll.js | Poll server for video transcoding status |

### Inline Editing

| File | Purpose |
|------|---------|
| text_edit.js | Inline text editing with markdown preview |
| sidebar_card_edit.js | Sidebar dropdown editing (machine, problem) |

### Lists & Navigation

| File | Purpose |
|------|---------|
| infinite_scroll.js | Infinite scroll pagination for log entries |
| machine_filter.js | Client-side machine list filtering |

### Factories

These are utility functions called by other components rather than auto-initializing on page load. Import by including the script, then call the factory function.

| File | Purpose |
|------|---------|
| dropdown_keyboard.js | Keyboard navigation for dropdowns |
| searchable_dropdown.js | Searchable dropdown creation |

### Page-Specific

| File | Purpose |
|------|---------|
| log_entry_detail.js | Auto-save for log entry work date and maintainers |


## Custom Events

Events document the contract between components:

| Event | Dispatched by | Listened by | Purpose |
|-------|---------------|-------------|---------|
| `card:initialize` | infinite_scroll.js | core.js | Re-bind clickable cards after dynamic content |
| `maintainer:selected` | maintainer_autocomplete.js | log_entry_detail.js | Maintainer selected from autocomplete |
| `media:uploaded` | media_grid.js | video_transcode_poll.js | Video uploaded, start polling |
| `media:ready` | video_transcode_poll.js | media_grid.js | Video transcoding complete |
