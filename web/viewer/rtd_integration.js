// ReadTheDocs-only integration for the MSI viewer.
(() => {
  'use strict';

  function initializeReadTheDocsFlyoutGuard() {
    const viewer = document.getElementById('msi-viewer-app');
    if (!viewer) return;

    let animationFrame = null;
    let flyout = null;
    let flyoutBox = null;
    let shadowObserver = null;

    function scheduleUpdate() {
      if (animationFrame !== null) return;
      animationFrame = window.requestAnimationFrame(update);
    }

    const resizeObserver = typeof ResizeObserver === 'undefined'
      ? null
      : new ResizeObserver(scheduleUpdate);

    function rectanglesOverlap(first, second) {
      return (
        first.width > 0 &&
        first.height > 0 &&
        second.width > 0 &&
        second.height > 0 &&
        first.left < second.right &&
        first.right > second.left &&
        first.top < second.bottom &&
        first.bottom > second.top
      );
    }

    function setFlyoutBox(nextBox) {
      if (nextBox === flyoutBox) return;

      if (flyoutBox && resizeObserver) {
        resizeObserver.unobserve(flyoutBox);
      }
      flyoutBox = nextBox;
      if (flyoutBox && resizeObserver) {
        resizeObserver.observe(flyoutBox);
      }
    }

    function bindFlyout() {
      const nextFlyout = document.querySelector('readthedocs-flyout');
      if (nextFlyout !== flyout) {
        setFlyoutBox(null);
        if (shadowObserver) {
          shadowObserver.disconnect();
          shadowObserver = null;
        }
        flyout = nextFlyout;
      }

      if (!flyout) return;

      const shadowRoot = flyout.shadowRoot;
      if (shadowRoot && !shadowObserver) {
        shadowObserver = new MutationObserver(() => {
          bindFlyout();
          scheduleUpdate();
        });
        shadowObserver.observe(shadowRoot, {
          attributes: true,
          attributeFilter: ['class', 'style'],
          childList: true,
          subtree: true,
        });
      }

      setFlyoutBox(
        shadowRoot?.querySelector('.container') ||
        shadowRoot?.firstElementChild ||
        flyout
      );
    }

    function update() {
      animationFrame = null;
      bindFlyout();
      if (!flyout) return;

      let overlaps = viewer.classList.contains('fullscreen-mode');
      if (!overlaps && flyoutBox) {
        overlaps = rectanglesOverlap(
          viewer.getBoundingClientRect(),
          flyoutBox.getBoundingClientRect()
        );
      }
      flyout.toggleAttribute('data-pymsi-overlaps-viewer', overlaps);
    }

    if (resizeObserver) {
      resizeObserver.observe(viewer);
    }

    // ReadTheDocs injects the flyout as a direct child of <body>.
    const bodyObserver = new MutationObserver(() => {
      bindFlyout();
      scheduleUpdate();
    });
    bodyObserver.observe(document.body, { childList: true });

    window.addEventListener('resize', scheduleUpdate, { passive: true });
    window.addEventListener('scroll', scheduleUpdate, {
      capture: true,
      passive: true,
    });
    document.addEventListener('readthedocs-addons-data-ready', scheduleUpdate);

    if (window.customElements) {
      window.customElements.whenDefined('readthedocs-flyout').then(() => {
        bindFlyout();
        scheduleUpdate();
      });
    }

    bindFlyout();
    scheduleUpdate();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeReadTheDocsFlyoutGuard);
  } else {
    initializeReadTheDocsFlyoutGuard();
  }
})();
