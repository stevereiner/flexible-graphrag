/*
 * Open external navigation links in a new tab.
 *
 * Zensical's nav accepts an external URL ("any string that cannot be resolved to a Markdown
 * page is treated as a URL") but exposes no target option, so the Blog entry would otherwise
 * navigate away from the docs in the same tab. Anything pointing at another origin gets
 * target=_blank here, plus rel=noopener (a _blank link grants the opened page window.opener
 * without it).
 *
 * Re-applied on navigation.instant page swaps, which replace the nav without a full reload.
 */
(function () {
  function markExternalLinks() {
    document.querySelectorAll('a[href^="http"]').forEach(function (a) {
      if (a.hostname && a.hostname !== window.location.hostname && !a.target) {
        a.target = '_blank';
        a.rel = (a.rel ? a.rel + ' ' : '') + 'noopener';
      }
    });
  }

  document.addEventListener('DOMContentLoaded', markExternalLinks);
  // navigation.instant swaps the DOM without firing DOMContentLoaded again.
  new MutationObserver(markExternalLinks).observe(document.documentElement, {
    childList: true,
    subtree: true
  });
})();
