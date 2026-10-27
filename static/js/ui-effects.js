/**
 * ui-effects.js — ReactBits-inspired Vanilla JS effects
 *
 * Implements the following patterns from reactbits.dev (ported to vanilla):
 *   - Aurora animated mesh background
 *   - ShinyText shimmer sweep on heading
 *   - Magnetic hover on buttons
 *   - Ripple click on primary buttons
 *   - Animated counter for badge
 *   - Tilt card effect on job cards
 */

(function () {
  'use strict';

  // =========================================================================
  // Aurora Background (inspired by ReactBits Aurora component)
  // Creates layered animated blobs in a fixed canvas behind the UI
  // =========================================================================
  function initAurora() {
    const canvas = document.getElementById('aurora-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let W, H, blobs, frame;

    const BLOBS = [
      { hue: 265, x: 0.15, y: 0.2,  r: 0.45, speed: 0.00012, phase: 0 },
      { hue: 180, x: 0.85, y: 0.75, r: 0.42, speed: 0.00009, phase: 2.1 },
      { hue: 290, x: 0.5,  y: 0.5,  r: 0.35, speed: 0.00015, phase: 1.0 },
      { hue: 200, x: 0.2,  y: 0.8,  r: 0.3,  speed: 0.00011, phase: 3.5 },
      { hue: 320, x: 0.8,  y: 0.15, r: 0.28, speed: 0.00013, phase: 0.7 },
    ];

    function resize() {
      W = canvas.width  = window.innerWidth;
      H = canvas.height = window.innerHeight;
    }

    function drawBlob(b, t) {
      const cx = (b.x + Math.sin(t * b.speed + b.phase) * 0.12) * W;
      const cy = (b.y + Math.cos(t * b.speed * 1.3 + b.phase) * 0.1) * H;
      const r  = b.r * Math.max(W, H);
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
      grad.addColorStop(0,   `hsla(${b.hue}, 80%, 60%, 0.18)`);
      grad.addColorStop(0.5, `hsla(${b.hue}, 70%, 50%, 0.07)`);
      grad.addColorStop(1,   `hsla(${b.hue}, 60%, 40%, 0)`);
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();
    }

    function render(t) {
      ctx.clearRect(0, 0, W, H);
      BLOBS.forEach(b => drawBlob(b, t));
      frame = requestAnimationFrame(render);
    }

    resize();
    window.addEventListener('resize', resize);
    frame = requestAnimationFrame(render);
  }

  // =========================================================================
  // ShinyText — shimmer sweep across the heading (ReactBits pattern)
  // =========================================================================
  function initShinyText() {
    const els = document.querySelectorAll('.shiny-text');
    if (!els.length) return;
    // Already handled by pure CSS @keyframes shiny-sweep
    // This function just marks them ready
    els.forEach(el => el.classList.add('shiny-text--ready'));
  }

  // =========================================================================
  // Magnetic Button — subtle attraction to cursor (ReactBits Magnet pattern)
  // =========================================================================
  function initMagneticButtons() {
    if (window.matchMedia('(pointer: coarse)').matches) return;
    const buttons = document.querySelectorAll('.btn--primary, .btn--download');
    buttons.forEach(btn => {
      btn.addEventListener('mousemove', (e) => {
        const rect = btn.getBoundingClientRect();
        const x = e.clientX - rect.left - rect.width / 2;
        const y = e.clientY - rect.top - rect.height / 2;
        const strength = 0.22;
        btn.style.transform = `translate(${x * strength}px, ${y * strength}px)`;
      });
      btn.addEventListener('mouseleave', () => {
        btn.style.transform = '';
        btn.style.transition = 'transform 0.4s cubic-bezier(0.23, 1, 0.32, 1)';
        setTimeout(() => { btn.style.transition = ''; }, 400);
      });
    });
  }

  // =========================================================================
  // Ripple on click (Material/ReactBits Ripple pattern)
  // =========================================================================
  function initRipple() {
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn--primary, .btn--download, .btn--retry, .tab');
      if (!btn || btn.disabled) return;
      const ripple = document.createElement('span');
      ripple.className = 'ripple-effect';
      const rect = btn.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height) * 1.8;
      ripple.style.cssText = `
        width:${size}px; height:${size}px;
        left:${e.clientX - rect.left - size / 2}px;
        top:${e.clientY - rect.top - size / 2}px;
      `;
      btn.style.position = 'relative';
      btn.style.overflow = 'hidden';
      btn.appendChild(ripple);
      ripple.addEventListener('animationend', () => ripple.remove());
    });
  }

  // =========================================================================
  // Animated counter for the active-count badge
  // =========================================================================
  let lastCount = 0;
  function animateCounter(el, to) {
    const from = lastCount;
    lastCount = to;
    if (from === to) return;
    const diff = to - from;
    const steps = Math.min(Math.abs(diff), 20);
    const dur = 400;
    let i = 0;
    const id = setInterval(() => {
      i++;
      const val = Math.round(from + diff * (i / steps));
      el.textContent = val;
      if (i >= steps) {
        clearInterval(id);
        el.textContent = to;
      }
    }, dur / steps);
  }

  // Observe badge value changes
  function initCounterBadge() {
    const badge = document.getElementById('active-count');
    if (!badge) return;
    const obs = new MutationObserver(() => {
      const newVal = parseInt(badge.textContent, 10) || 0;
      if (newVal !== lastCount) animateCounter(badge, newVal);
    });
    obs.observe(badge, { childList: true, characterData: true, subtree: true });
  }

  // =========================================================================
  // Card tilt on hover (ReactBits TiltCard pattern)
  // =========================================================================
  function initCardTilt() {
    // Apply to job cards dynamically via event delegation
    const list = document.getElementById('jobs-list');
    if (!list) return;

    list.addEventListener('mousemove', (e) => {
      const card = e.target.closest('.job-card');
      if (!card) return;
      const rect = card.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width  - 0.5;
      const y = (e.clientY - rect.top)  / rect.height - 0.5;
      card.style.transform = `perspective(600px) rotateY(${x * 4}deg) rotateX(${-y * 4}deg) scale(1.01)`;
    });

    list.addEventListener('mouseleave', (e) => {
      const card = e.target.closest?.('.job-card');
      if (!card) return;
      card.style.transform = '';
      card.style.transition = 'transform 0.45s cubic-bezier(0.23, 1, 0.32, 1)';
      setTimeout(() => { card.style.transition = ''; }, 450);
    }, true);
  }

  // =========================================================================
  // Spotlight hover on cards (ReactBits Spotlight pattern)
  // =========================================================================
  function initSpotlight() {
    const list = document.getElementById('jobs-list');
    if (!list) return;

    list.addEventListener('mousemove', (e) => {
      const card = e.target.closest('.job-card');
      if (!card) return;
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      card.style.setProperty('--spotlight-x', `${x}px`);
      card.style.setProperty('--spotlight-y', `${y}px`);
      card.classList.add('spotlight-active');
    });

    list.addEventListener('mouseleave', () => {
      document.querySelectorAll('.job-card.spotlight-active').forEach(c => {
        c.classList.remove('spotlight-active');
      });
    }, true);
  }

  // =========================================================================
  // URL input — animated border glow on focus (ReactBits GlowBorder)
  // =========================================================================
  function initInputGlow() {
    const input = document.getElementById('url-input');
    if (!input) return;
    // Handled by CSS :focus-within on .input-row
  }

  // =========================================================================
  // Page-load stagger animation for cards
  // =========================================================================
  function initStaggerObserver() {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('stagger-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1 });

    // Re-observe any new cards added to the DOM
    const list = document.getElementById('jobs-list');
    if (!list) return;
    const mo = new MutationObserver(() => {
      list.querySelectorAll('.job-card:not(.stagger-visible)').forEach(c => observer.observe(c));
    });
    mo.observe(list, { childList: true, subtree: false });
  }

  // =========================================================================
  // Tab underline slide animation
  // =========================================================================
  function initTabUnderline() {
    const tabs = document.querySelector('.tabs');
    if (!tabs) return;
    const indicator = document.createElement('span');
    indicator.className = 'tabs__indicator';
    tabs.appendChild(indicator);

    function updateIndicator() {
      const active = tabs.querySelector('.tab.active');
      if (!active) return;
      const rect = active.getBoundingClientRect();
      const parentRect = tabs.getBoundingClientRect();
      indicator.style.left  = `${rect.left - parentRect.left}px`;
      indicator.style.width = `${rect.width}px`;
    }

    tabs.addEventListener('click', () => requestAnimationFrame(updateIndicator));
    updateIndicator();
  }

  // =========================================================================
  // Clipboard Paste Helper for #btn-paste-url
  // =========================================================================
  function initPasteAction() {
    const pasteBtn = document.getElementById('btn-paste-url');
    const input = document.getElementById('url-input');
    if (!pasteBtn || !input) return;

    pasteBtn.addEventListener('click', async () => {
      try {
        const text = await navigator.clipboard.readText();
        if (text) {
          input.value = text.trim();
          input.dispatchEvent(new Event('input', { bubbles: true }));
          input.focus();
          const orig = pasteBtn.innerHTML;
          pasteBtn.innerHTML = '<span>✓</span> Pasted!';
          pasteBtn.style.borderColor = 'var(--status-completed)';
          pasteBtn.style.color = 'var(--status-completed)';
          setTimeout(() => {
            pasteBtn.innerHTML = orig;
            pasteBtn.style.borderColor = '';
            pasteBtn.style.color = '';
          }, 1200);
        }
      } catch (err) {
        input.focus();
      }
    });
  }

  // =========================================================================
  // Boot
  // =========================================================================
  function boot() {
    initAurora();
    initShinyText();
    initMagneticButtons();
    initRipple();
    initCounterBadge();
    initCardTilt();
    initSpotlight();
    initInputGlow();
    initStaggerObserver();
    initTabUnderline();
    initPasteAction();
    initMobileMenu();
  }

  // =========================================================================
  // Mobile Navigation Menu Toggle
  // =========================================================================
  function initMobileMenu() {
    const btn = document.getElementById('mobile-menu-btn');
    const drawer = document.getElementById('mobile-nav-drawer');
    if (!btn || !drawer) return;

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = !drawer.hidden;
      drawer.hidden = isOpen;
      btn.setAttribute('aria-expanded', String(!isOpen));
      btn.classList.toggle('active', !isOpen);
    });

    document.addEventListener('click', (e) => {
      if (!drawer.hidden && !drawer.contains(e.target) && !btn.contains(e.target)) {
        drawer.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
        btn.classList.toggle('active', false);
      }
    });

    // Close drawer when a link is clicked
    drawer.querySelectorAll('.mobile-nav-link').forEach(link => {
      link.addEventListener('click', () => {
        drawer.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
        btn.classList.toggle('active', false);
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
