(() => {
  const copyButtons = document.querySelectorAll("[data-copy]");
  copyButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const text = button.getAttribute("data-copy");
      if (!text) return;
      const label = button.querySelector("[data-copy-label]");
      const original = label ? label.textContent : button.textContent;
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text);
        } else {
          const field = document.createElement("textarea");
          field.value = text;
          field.setAttribute("readonly", "");
          field.style.position = "fixed";
          field.style.opacity = "0";
          document.body.appendChild(field);
          field.select();
          const copied = document.execCommand("copy");
          field.remove();
          if (!copied) throw new Error("Clipboard unavailable");
        }
        if (label) label.textContent = "Copied";
        button.setAttribute("aria-label", "Copied to clipboard");
        window.setTimeout(() => {
          if (label) label.textContent = original;
          button.setAttribute("aria-label", original);
        }, 1400);
      } catch (error) {
        if (label) label.textContent = "Copy failed";
        window.setTimeout(() => {
          if (label) label.textContent = original;
        }, 1600);
      }
    });
  });

  const year = document.querySelector("[data-year]");
  if (year) year.textContent = String(new Date().getFullYear());
})();