# Triage placeholder UI notes

Route `/triage` is structure only. There is no styling: no classes, CSS, inline
styles or colors. Tailwind is not installed yet. Each component carries a
`TODO(design)` comment. All card text renders as React text nodes.

## Layout blocks

- Queue list: one `article` per card, in API rank order (`GET /cards/queue`).
- Card detail: `h2` title, wildcard/snoozed markers, source link, what happened,
  why it matters, a `dl` of angle, gap, format and scores.
- Page-level key field: one editor key password input above the list, memory only.
- Decision bar: reason tags, note,
  Accept / Reject / Snooze buttons, status line.
- Reason tags: checkboxes for the nine tags mirrored from `REASON_TAGS`.

## States

- Loading: `loading.tsx` shows "Loading the queue...".
- Empty queue: message pointing at the cards stage.
- Error: `role="alert"` message when the server-side fetch or parse fails.
- Wrong key: 401 shows "Wrong or missing editor key."
- API not configured: the proxy returns 503 `not_configured`; the page shows a failed state.
- Validation failure: a 422 from the API shows the failed state with its message.
- Saving: buttons and tags disabled, "Saving...".
- Saved: "Saved: <decision>". Failed: status, code and message.

## Writes

Browsers post to the same-origin route `/api/cards/{id}/decision`, which
forwards to the API (no CORS on the API). The key is never stored, logged or put
in a URL. `decision_ms` is measured from when the card component rendered.

## Keyboard map (documented, NOT implemented)

| Key | Action              |
| --- | ------------------- |
| `a` | accept focused card |
| `r` | reject focused card |
| `s` | snooze focused card |
| `j` | next card           |
| `k` | previous card       |

## Pending design decisions (design references and global.css)

Spacing scale, type scale, color tokens, focus rings, wildcard treatment, and
dark mode.
