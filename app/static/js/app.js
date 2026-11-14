// Small interactions. No inline scripts anywhere, so the Content-Security-Policy can forbid them.
document.querySelectorAll('[data-toggle-pw]').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var input = btn.parentElement.querySelector('input');
    var show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    btn.setAttribute('aria-pressed', show ? 'true' : 'false');
    btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    btn.querySelector('[data-eye]').classList.toggle('hidden', show);
    btn.querySelector('[data-eye-off]').classList.toggle('hidden', !show);
  });
});
document.querySelectorAll('form[data-loading]').forEach(function (form) {
  var btn = form.querySelector('button[type=submit]'), label = btn.querySelector('[data-label]'), text = label.textContent;
  form.addEventListener('submit', function () { btn.disabled = true; label.textContent = btn.dataset.loadingText; });
  window.addEventListener('pageshow', function () { btn.disabled = false; label.textContent = text; });
});
document.querySelectorAll('form[data-confirm]').forEach(function (form) {
  form.addEventListener('submit', function (e) { if (!window.confirm(form.dataset.confirm)) e.preventDefault(); });
});
document.querySelectorAll('[data-google]').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var note = document.querySelector('[data-google-note]');
    if (note) note.hidden = false;
  });
});

document.querySelectorAll('[data-copy]').forEach(function (btn) {
  var label = btn.textContent;
  btn.addEventListener('click', function () {
    var done = function () { btn.textContent = btn.dataset.copied || 'Copied'; setTimeout(function () { btn.textContent = label; }, 1800); };
    var fallback = function () {
      var el = document.getElementById('track-code');
      if (el && window.getSelection) { var r = document.createRange(); r.selectNodeContents(el); var s = window.getSelection(); s.removeAllRanges(); s.addRange(r); }
      btn.textContent = 'Press Ctrl+C';
    };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(btn.dataset.copy).then(done, fallback); else fallback();
  });
});

// Public navbar: mobile menu and Services dropdown (click for touch, hover/focus handled in CSS)
(function () {
  var burger = document.querySelector('[data-burger]'), menu = document.getElementById('m-menu');
  if (burger && menu) burger.addEventListener('click', function () {
    var open = menu.classList.toggle('open');
    burger.setAttribute('aria-expanded', open ? 'true' : 'false');
    burger.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
  });
  var dd = document.querySelector('[data-dd]');
  if (dd) {
    var btn = dd.querySelector('button');
    var set = function (open) { dd.classList.toggle('open', open); btn.setAttribute('aria-expanded', open ? 'true' : 'false'); };
    btn.addEventListener('click', function () { set(!dd.classList.contains('open')); });
    document.addEventListener('click', function (e) { if (!dd.contains(e.target)) set(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { set(false); btn.focus(); } });
  }
})();
