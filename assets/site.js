(() => {
  "use strict";

  const copyButtons = document.querySelectorAll("[data-copy]");
  copyButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const value = button.getAttribute("data-copy");
      const label = button.querySelector("[data-copy-label]");
      if (!value || button.disabled) return;

      const original = label ? label.textContent : "Copy";
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      button.classList.remove("is-success", "is-error");
      if (label) label.textContent = "Copying…";

      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(value);
        } else {
          const field = document.createElement("textarea");
          field.value = value;
          field.setAttribute("readonly", "");
          field.setAttribute("aria-hidden", "true");
          field.style.position = "fixed";
          field.style.left = "-9999px";
          document.body.appendChild(field);
          field.select();
          const copied = document.execCommand("copy");
          field.remove();
          if (!copied) throw new Error("Clipboard unavailable");
        }

        if (label) label.textContent = "Copied";
        button.setAttribute("aria-label", "Copied to clipboard");
        button.classList.add("is-success");
        window.setTimeout(() => {
          if (label) label.textContent = original;
          button.setAttribute("aria-label", "Copy GlassDock installation command");
          button.classList.remove("is-success");
          button.removeAttribute("aria-busy");
          button.disabled = false;
        }, 1300);
      } catch {
        if (label) label.textContent = "Copy failed";
        button.setAttribute("aria-label", "Copy failed. Select the command and copy it manually.");
        button.classList.add("is-error");
        button.removeAttribute("aria-busy");
        button.disabled = false;
        window.setTimeout(() => {
          if (label) label.textContent = original;
          button.setAttribute("aria-label", "Copy GlassDock installation command");
          button.classList.remove("is-error");
        }, 1800);
      }
    });
  });

  const year = document.querySelector("[data-year]");
  if (year) year.textContent = String(new Date().getFullYear());

  const art = document.querySelector(".hero-art");
  const layers = art ? [...art.querySelectorAll(".parallax-layer[data-depth]")] : [];
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
  let pointerX = 0;
  let pointerY = 0;
  let scrollY = 0;
  let frame = 0;

  const renderParallax = () => {
    frame = 0;
    layers.forEach((layer) => {
      const depth = Number(layer.dataset.depth || 0);
      layer.style.setProperty("--parallax-x", `${(pointerX * depth * 26).toFixed(2)}px`);
      layer.style.setProperty("--parallax-y", `${(pointerY * depth * 18 + scrollY * depth * 0.12).toFixed(2)}px`);
    });
  };

  const scheduleParallax = () => {
    if (!frame) frame = window.requestAnimationFrame(renderParallax);
  };

  const resetPointer = () => {
    pointerX = 0;
    pointerY = 0;
    scheduleParallax();
  };

  if (art && layers.length && !reducedMotion.matches) {
    if (finePointer.matches) {
      art.addEventListener("pointermove", (event) => {
        const bounds = art.getBoundingClientRect();
        if (!bounds.width || !bounds.height) return;
        pointerX = ((event.clientX - bounds.left) / bounds.width - 0.5) * 2;
        pointerY = ((event.clientY - bounds.top) / bounds.height - 0.5) * 2;
        scheduleParallax();
      });
      art.addEventListener("pointerleave", resetPointer);
    }

    window.addEventListener("scroll", () => {
      const bounds = art.getBoundingClientRect();
      scrollY = Math.max(-80, Math.min(80, window.innerHeight / 2 - (bounds.top + bounds.height / 2)));
      scheduleParallax();
    }, { passive: true });

    reducedMotion.addEventListener?.("change", (event) => {
      if (event.matches) {
        pointerX = 0;
        pointerY = 0;
        scrollY = 0;
        layers.forEach((layer) => {
          layer.style.removeProperty("--parallax-x");
          layer.style.removeProperty("--parallax-y");
        });
      }
    });
  }
})();

document.documentElement.classList.add("js");
const revealTargets = document.querySelectorAll(".hero, .section, .site-footer");
revealTargets.forEach((target) => target.classList.add("scroll-reveal"));
if ("IntersectionObserver" in window) {
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      entry.target.classList.toggle("is-visible", entry.isIntersecting);
    });
  }, { threshold: 0.12 });
  revealTargets.forEach((target) => revealObserver.observe(target));
} else {
  revealTargets.forEach((target) => target.classList.add("is-visible"));
}
