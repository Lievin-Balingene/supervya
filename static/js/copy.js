(function () {
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        resolve();
      } catch (e) {
        reject(e);
      } finally {
        document.body.removeChild(ta);
      }
    });
  }

  function flash(btn) {
    const prev = btn.textContent;
    btn.textContent = "Copié ✓";
    btn.classList.add("copied");
    setTimeout(function () {
      btn.textContent = prev;
      btn.classList.remove("copied");
    }, 1600);
  }

  document.addEventListener("click", function (ev) {
    const btn = ev.target.closest("[data-copy-target]");
    if (btn) {
      const text = btn.getAttribute("data-copy-target") || "";
      copyText(text).then(function () {
        flash(btn);
      });
      return;
    }
    const code = ev.target.closest("code[data-copy], pre[data-copy]");
    if (code) {
      const text = code.getAttribute("data-copy") || code.textContent || "";
      copyText(text.trim());
    }
  });
})();
