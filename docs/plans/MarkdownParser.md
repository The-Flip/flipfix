# CommonMark-Compliant Markdown Parser

Status: IMPLEMENTED.

## Overview

I'm not happy with how markdown is behaving.

The current markdown parser requires that people put a leading blank line in front of their lists for them to be transformed into `ul` and `ol`.

```
Some text

- list item MUST have blank line before it
- item 2
- item 3
```

People aren't doing that, and therefore they aren’t getting nice lists.

Some of these people not putting the blank line are long time software developers themselves. If THEY don't do correct markdown, I can't imagine most people do.

Heck, _I_ had to learn the blank line trick while building this system myself. I told myself I just didn't know markdown, but eventually I figured out it was a markdown library problem.

## Every Major System Supports This

All the systems that people use on a daily basis don't require a blank line for lists: Stack Overflow, Reddit, Discord, Slack, Notion, Obsidian, GitHub.

So Flipfix is the outlier; Flipfix should be fixed.

## We Want `CommonMark` Compliance

This project currently uses `Python-Markdown`. `Python-Markdown` intentionally requires blank lines before lists, following the original Gruber Markdown spec. Many of the platforms users actually interact with follow the [CommonMark](https://commonmark.org/) spec, which relaxes this rule. Reddit, Stack Overflow, GitHub, GitLab are all explicitly CommonMark-based.

We should switch to a CommonMark-compliant parser.

## Rejected Option: Custom Preprocessor

Instead of changing markdown libraries, we could write a preprocessor that inserts a blank line before lines starting with 1., - , or \* when the previous line is non-empty text. This is targeted and keeps the current stack.

We rejected this:

- It's finicky, trying to guess where users meant to start a list.
- Using a `CommonMark` compliant lib means every other CommonMark edge case people expect would just work.

## The Correct Parser: `markdown-it-py`

`markdown-it-py` is the main Python implementation of `CommonMark`. It supports everything done by the plugins we're currently using (`fenced_code`, `nl2br`, `smarty`).

### Extension mapping

| Python-Markdown | What it does                       | markdown-it-py equivalent                                    |
| --------------- | ---------------------------------- | ------------------------------------------------------------ |
| `fenced_code`   | Triple-backtick code blocks        | Built into `commonmark` preset                               |
| `nl2br`         | Single newlines become `<br>` tags | `breaks=True` constructor option                             |
| `smarty`        | Smart quotes, em dashes, ellipsis  | `typographer=True` + enable `smartquotes` and `replacements` |

## Other Benefits Of Using `markdown-it-py`

### URL Linkification

`markdown-it-py` has built-in linkification. Using it will be an improvement over what we have now.

The current linkification runs on the HTML output, which is inherently fragile. It uses `linkify-it-py` to find URLs in the HTML string, then tries to skip ones already inside `href=` attributes with a string prefix check. This approach has a structural problem: it can't distinguish between a bare URL a user typed in a paragraph vs. a URL that appears inside a `<code> `block or `<pre>` block. It would linkify URLs inside code blocks, which is wrong.

`markdown-it-py`'s built-in linkify runs during parsing, so it understands the document structure. It knows not to linkify URLs inside code spans, code blocks, or existing links. It also already uses `linkify-it-py` under the hood — same URL detection, but applied at the right stage of the pipeline.

### More Robust XSS Protection

`markdown-it-py` has built-in XSS protection: it refuses to render `javascript:` URLs as links at all, outputting the raw markdown text instead. This is better security than the current approach, where `Python-Markdown` would render the `<a>` tag, then `nh3` would strip the href.
