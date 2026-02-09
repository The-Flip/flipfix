# JavaScript Testing Guide

For how to run tests and CI configuration, see [Testing.md](Testing.md).

JavaScript modules are tested with [Vitest](https://vitest.dev/). Tests run in Node, not in the browser.

## Setup

```bash
npm install              # One-time: installs vitest
make test-js             # Run JS tests
```

## Architecture

JS modules use an IIFE pattern that conditionally exports pure functions for testing:

```javascript
(function (exports) {
  'use strict';

  function myPureFunction(value, start, end) {
    // String manipulation, returns { value, selectionStart, selectionEnd }
  }

  // DOM wiring (browser only)
  if (typeof document !== 'undefined') {
    // Event listeners, DOMContentLoaded, etc.
  }

  // Test exports (Node only)
  if (exports) {
    exports.myPureFunction = myPureFunction;
  }
})(typeof module !== 'undefined' ? module.exports : null);
```

This keeps the production behavior identical (IIFE, no globals) while making pure logic testable. DOM wiring is excluded from Node — integration-level tests use jsdom where needed.

## Test File Location

Test files live alongside their source in `the_flip/static/core/`:

```text
the_flip/static/core/
├── markdown_shortcuts.js          # Source
├── markdown_shortcuts.test.js     # Tests
```

## Writing Tests

```javascript
import { describe, it, expect } from 'vitest';
const { myPureFunction } = require('./my_module.js');

describe('myPureFunction', () => {
  it('does the expected thing', () => {
    const result = myPureFunction('hello', 0, 5);
    expect(result.value).toBe('expected output');
  });
});
```

## Testability Guidance

Not all JS files benefit equally from unit tests. Prioritize based on code structure:

- **Pure functions** (string manipulation, date formatting, state calculations): High value. Import via `require()`, test with exact assertions. Examples: `checkbox_toggle.js`, `core.js` date utilities, `markdown_shortcuts.js`.
- **Factories with state** (dropdown creation, chip input logic): Medium value. Test with jsdom (`@vitest-environment jsdom` pragma). Examples: `dropdown_keyboard.js`.
- **DOM glue and fetch wiring** (event listeners, AJAX posts, polling): Low value for unit tests. These are better covered by browser-level or integration tests. Examples: `infinite_scroll.js`, `video_transcode_poll.js`, `media_grid.js`.

## Locale-Sensitive Tests

Functions that use `Intl.DateTimeFormat` produce output that varies by locale and environment (12h vs 24h, month abbreviations, etc.). Don't assert exact formatted strings. Instead, assert on:

- **Branch behavior** you control: presence of "Yesterday" prefix, inclusion of year digits, weekday abbreviation
- **Structural invariants**: result is lowercase, non-empty, contains expected digits (day number, year)
- **What not to assert**: exact time strings like `"2:30 PM"` or `"14:30"` — these differ across environments

Functions that don't use Intl APIs (like `toDateTimeLocalValue`, `isSameDay`) can use exact assertions.
