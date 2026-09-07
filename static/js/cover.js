(() => {
  "use strict";

  const hero = document.getElementById("coverHero");
  const canvas = document.getElementById("livingArtwork");
  if (!hero || !canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const photo = new Image();
  const pointer = { x: 0, y: 0, currentX: 0, currentY: 0 };
  let width = 0;
  let height = 0;
  let loaded = false;
  let visible = true;
  let frame = 0;
  let previousTime = 0;
  let elapsed = 0;
  let sweep = -1;
  let artBounds = null;
  let layout = { size: 0, x: 0, y: 0 };

  const isMoving = () => visible && !document.hidden;

  function paint() {
    ctx.clearRect(0, 0, width, height);
    if (!loaded) return;

    const size = layout.size;
    const floatY = Math.sin(elapsed * 0.0012) * 5;
    const x = layout.x + pointer.currentX * (width <= 860 ? 5 : 22);
    const y = layout.y + pointer.currentY * (width <= 860 ? 4 : 13) + floatY;
    artBounds = { x, y, size };

    ctx.drawImage(photo, x, y, size, size);

    // Re-light slices of the original photo, keeping its actual artwork intact.
    const scan = sweep >= 0 ? sweep : (elapsed % 8500) / 1800;
    if (scan <= 1) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(x, y + scan * size, size, size * 0.045);
      ctx.clip();
      ctx.globalCompositeOperation = "screen";
      ctx.globalAlpha = sweep >= 0 ? 0.64 : 0.22;
      ctx.drawImage(photo, x, y, size, size);
      ctx.restore();
    }

    // Pulse the luminous face region already present in the logo.
    ctx.save();
    ctx.beginPath();
    ctx.ellipse(x + size * 0.557, y + size * 0.374, size * 0.075, size * 0.028, 0.17, 0, Math.PI * 2);
    ctx.clip();
    ctx.globalCompositeOperation = "screen";
    ctx.globalAlpha = 0.10 + (Math.sin(elapsed * 0.003) + 1) * 0.11;
    ctx.drawImage(photo, x, y, size, size);
    ctx.restore();
  }

  function animate(now) {
    frame = 0;
    if (!isMoving()) return;
    const delta = previousTime ? Math.min(now - previousTime, 50) : 16;
    previousTime = now;
    elapsed += delta;
    const ease = 1 - Math.exp(-delta / 140);
    pointer.currentX += (pointer.x - pointer.currentX) * ease;
    pointer.currentY += (pointer.y - pointer.currentY) * ease;
    if (sweep >= 0) {
      sweep += delta / 850;
      if (sweep > 1) sweep = -1;
    }
    paint();
    frame = requestAnimationFrame(animate);
  }

  function updateMotion() {
    cancelAnimationFrame(frame);
    frame = 0;
    previousTime = 0;
    paint();
    if (loaded && isMoving()) frame = requestAnimationFrame(animate);
  }

  function resize() {
    const bounds = hero.getBoundingClientRect();
    width = bounds.width;
    height = bounds.height;
    const imageBounds = hero.querySelector(".art-fallback").getBoundingClientRect();
    layout = { size: imageBounds.width, x: imageBounds.left - bounds.left, y: imageBounds.top - bounds.top };
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    paint();
  }

  hero.addEventListener("pointermove", (event) => {
    if (!isMoving()) return;
    const bounds = hero.getBoundingClientRect();
    pointer.x = Math.max(-1, Math.min(1, (event.clientX - bounds.left) / width * 2 - 1));
    pointer.y = Math.max(-1, Math.min(1, (event.clientY - bounds.top) / height * 2 - 1));
  }, { passive: true });
  hero.addEventListener("pointerleave", () => { pointer.x = pointer.y = 0; });
  hero.addEventListener("pointercancel", () => { pointer.x = pointer.y = 0; });
  hero.addEventListener("pointerdown", (event) => {
    if (!isMoving() || !artBounds || event.target.closest("a, input, label, button, form")) return;
    const bounds = hero.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    const y = event.clientY - bounds.top;
    if (x >= artBounds.x && x <= artBounds.x + artBounds.size && y >= artBounds.y && y <= artBounds.y + artBounds.size) sweep = 0;
  }, { passive: true });
  document.addEventListener("visibilitychange", updateMotion);
  new ResizeObserver(resize).observe(hero);
  new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; updateMotion(); }).observe(hero);

  photo.onload = () => {
    loaded = true;
    resize();
    hero.querySelector(".hero-art").classList.add("is-ready");
    updateMotion();
  };
  photo.src = hero.querySelector(".art-fallback").src;
})();
