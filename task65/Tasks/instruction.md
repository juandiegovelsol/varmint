# Date & time utilities: missing duration format, and the current output has drifted

Our shared date & time utilities cover relative time, absolute time/date, and
combined date-and-time/range formatting. Two things need fixing.

## 1. Add a duration format

A duration format shows the absolute length of time (e.g. 2 seconds, 1 hour 30
minutes) — unlike relative time (e.g. "1 hour ago"). Add it alongside the
existing formatters, following their conventions: an options object with
`locale` and `style`, a sensible default style, exposed through the same
public surface consumers already import from. Wrap the platform's native
[`Intl.DurationFormat`](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DurationFormat).

For 1 hour, 23 minutes and 45 seconds in `en-US`, the expected outputs are:

| style | output |
| --- | --- |
| (default) | 1h 23m 45s |
| long | 1 hour, 23 minutes, 45 seconds |
| short | 1 hr, 23 min, 45 sec |
| narrow | 1h 23m 45s |
| digital | 1:23:45 |

The attached design-guidance table defines these conventions (reference
output, permitted variants, default per format) for the existing formatters —
it has no Duration row yet; that's the gap this fills.

<img alt="Design guidance: supported date & time formats" src="/app/.harbor_assets/date_time_formats_reference.png" />

## 2. Fix the drift from that guidance

Our internal demo pages, rendered against the current code, show several
formatters — across more than one utility — no longer matching that guidance.
The demos are self-checking: each row's caption states its own call/config,
and the same value is shown across several locales side by side — so wrong
output always sits next to a caption or locale column that shows what's
right.

<img alt="Date and time utilities, current rendered output" src="/app/.harbor_assets/datetime_utilities_current.png" />

<img alt="Tag overflow utility, current rendered behaviour" src="/app/.harbor_assets/tag_overflow_current.png" />

Done when the duration format matches the table above, and everything in the
demo screenshots renders the way the guidance table and each row's caption say
it should.
