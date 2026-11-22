// Runs synchronously before the app styles. Bump the filename when changing this
// bootstrap: nginx serves JS assets with immutable caching.
(function () {
  var theme = 'light';
  try {
    var saved = window.localStorage.getItem('sahool-theme');
    if (saved === 'dark' || saved === 'light' || saved === 'cream') theme = saved;
  } catch {
    // A blocked or unavailable store must not prevent the page from opening.
  }
  document.documentElement.setAttribute('data-theme', theme);
})();
