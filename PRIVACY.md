# Privacy

There is nothing to collect.

- **No accounts.** No sign-up, no login, no email capture.
- **No analytics.** No Google Analytics, no Plausible, no counters, no pixels.
- **No cookies.** Reading progress, if any, is kept in your own browser's local
  storage and never leaves the device.
- **No third-party requests on a reading page.** The renderers (pdf.js,
  epub.js, JSZip) are vendored in this repository. Fonts are the one exception:
  they load from Google Fonts, and you can block that without losing anything
  but the exact typeface.
- **Server logs.** The site is served by GitHub Pages and book files by
  jsDelivr, so both see ordinary web requests (IP address, user agent) under
  their own privacy policies. That is the whole of it.

If you want a library that cannot see you at all, clone this repository and
open `index.html` locally — it works offline, which is the point.
