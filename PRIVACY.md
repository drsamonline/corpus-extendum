# Privacy

There is nothing to collect.

- **No accounts.** No sign-up, no login, no email capture.
- **No analytics.** No Google Analytics, no Plausible, no counters, no pixels.
- **No cookies.** Your reading position is kept in your browser's local storage,
  under the key `corpus-extendum:progress`, and never leaves the device. Clearing
  it is one button on the shelf, or your browser's site-data settings.
- **No third-party requests on a reading page.** The renderers (pdf.js,
  epub.js, JSZip) are vendored in this repository. Fonts are the one exception:
  they load from Google Fonts, and you can block that without losing anything
  but the exact typeface.
- **Server logs.** The site is served by GitHub Pages and book files by
  jsDelivr, so both see ordinary web requests (IP address, user agent) under
  their own privacy policies. That is the whole of it.

If you want a library that cannot see you at all, clone this repository and
open `index.html` locally — it works offline, which is the point.
