/* Progressive enhancements for published Artefato pages (inlined by the
   publisher next to base.css). Display-only by contract: the DOM the renderer
   emitted is decorated, never reworded — and with scripts disabled the page
   reads exactly as before. Each enhancement no-ops when the page lacks the
   structure it keys on, so no report shape is ever required.
   NOTE: this file is inlined inside a script element — it must never contain
   a script tag literal, opening or closing (the publisher also escapes the
   closing sequence as defense in depth). */
(function () {
  'use strict';

  var article = document.querySelector('article.report');
  if (!article) return;

  /* --- Sumário: built from the section titles when the report is long
     enough to need navigation. Numbering mirrors the CSS section counter. --- */
  var sections = Array.prototype.slice.call(
    article.querySelectorAll('.section-title'));
  if (sections.length >= 3) {
    var toc = document.createElement('nav');
    toc.className = 'report-toc';
    var tocTitle = document.createElement('p');
    tocTitle.className = 'report-toc-title';
    var lang = (document.documentElement.lang || '').toLowerCase();
    tocTitle.textContent = lang.indexOf('pt') === 0 ? 'Sumário' : 'Contents';
    toc.appendChild(tocTitle);
    var list = document.createElement('ol');
    sections.forEach(function (h, i) {
      if (!h.id) h.id = 'secao-' + (i + 1);
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = '#' + h.id;
      a.textContent = h.textContent;
      li.appendChild(a);
      list.appendChild(li);
    });
    toc.appendChild(list);
    var meta = article.querySelector('.meta');
    if (meta) meta.insertAdjacentElement('afterend', toc);
    else article.insertBefore(toc, article.firstChild);
  }

  /* --- Diff tint: per-line coloring for plain-text <pre> blocks that look
     like unified diffs. Only text-only blocks are touched (a <pre> that
     already carries markup — e.g. the .diff-block palette — is left alone). --- */
  Array.prototype.slice.call(article.querySelectorAll('pre')).forEach(function (pre) {
    if (pre.children.length > 0) return;
    var lines = pre.textContent.split('\n');
    var adds = 0, dels = 0;
    lines.forEach(function (l) {
      if (l.charAt(0) === '+') adds += 1;
      if (l.charAt(0) === '-') dels += 1;
    });
    if (adds < 2 || dels < 1) return;
    pre.textContent = '';
    lines.forEach(function (l, i) {
      var cls = '';
      if (/^(\+\+\+|---|@@|diff )/.test(l)) cls = 'diff-line-meta';
      else if (l.charAt(0) === '+') cls = 'diff-line-add';
      else if (l.charAt(0) === '-') cls = 'diff-line-del';
      if (cls) {
        var span = document.createElement('span');
        span.className = cls;
        span.textContent = l;
        pre.appendChild(span);
      } else {
        pre.appendChild(document.createTextNode(l + (i < lines.length - 1 ? '\n' : '')));
      }
    });
  });

  /* --- Lightbox: click a figure image to inspect it full-screen (screenshots
     are evidence; the inline rendering is too small to read). --- */
  function closeLightbox() {
    var box = document.querySelector('.report-lightbox');
    if (box) box.remove();
  }
  article.addEventListener('click', function (e) {
    var img = e.target;
    if (!(img.tagName === 'IMG' && img.closest('figure'))) return;
    var box = document.createElement('div');
    box.className = 'report-lightbox';
    var full = document.createElement('img');
    full.src = img.src;
    full.alt = img.alt;
    box.appendChild(full);
    box.addEventListener('click', closeLightbox);
    document.body.appendChild(box);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeLightbox();
  });
})();
