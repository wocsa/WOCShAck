/* community_engagement/js/leveling.js */

document.addEventListener('DOMContentLoaded', () => {

  // ── Tabs ────────────────────────────────────────────────────────
  const tabs    = document.querySelectorAll('.lv-tab');
  const contents = document.querySelectorAll('.lv-tab-content');

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;

      tabs.forEach(t => t.classList.remove('lv-tab--active'));
      tab.classList.add('lv-tab--active');

      contents.forEach(c => {
        const id = c.id.replace('tab-', '');
        c.classList.toggle('lv-tab-content--hidden', id !== target);
      });
    });
  });

  // ── Auto-dismiss toast after 5s ────────────────────────────────
  const toast = document.getElementById('login-reward-toast');
  if (toast) {
    setTimeout(() => {
      toast.style.transition = 'opacity 0.4s ease';
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 400);
    }, 5000);
  }

  // ── Animate progress bar on load ───────────────────────────────
  // Le CSS gère l'animation via la custom property --pct,
  // mais on force un reflow pour déclencher la transition
  document.querySelectorAll('.lv-progress-bar-fill').forEach(bar => {
    const pct = bar.parentElement.style.getPropertyValue('--pct');
    bar.style.width = '0%';
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        bar.style.width = pct;
      });
    });
  });

});
