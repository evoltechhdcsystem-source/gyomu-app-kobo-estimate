(() => {
  const form = document.querySelector('.maintenance-option-form');
  const checkbox = form?.querySelector('input[name="maintenance"]');
  const detailTrigger = document.querySelector('[data-maintenance-detail-trigger]');
  const detailPopover = document.getElementById('maintenanceDetailPopover');
  const detailPrice = detailPopover?.querySelector('[data-maintenance-detail-price]');

  if (detailTrigger && detailPopover) {
    let closeTimer;

    function positionPopover() {
      const gap = 10;
      const triggerRect = detailTrigger.getBoundingClientRect();
      const popoverRect = detailPopover.getBoundingClientRect();
      const width = document.documentElement.clientWidth;
      const height = document.documentElement.clientHeight;
      const left = Math.min(Math.max(triggerRect.left, gap), width - popoverRect.width - gap);
      let top = triggerRect.bottom + gap;
      if (top + popoverRect.height > height - gap) {
        top = Math.max(triggerRect.top - popoverRect.height - gap, gap);
      }
      detailPopover.style.left = `${left}px`;
      detailPopover.style.top = `${top}px`;
    }

    function showPopover() {
      window.clearTimeout(closeTimer);
      detailPopover.hidden = false;
      detailTrigger.setAttribute('aria-expanded', 'true');
      positionPopover();
    }

    function hidePopover() {
      window.clearTimeout(closeTimer);
      detailPopover.hidden = true;
      detailTrigger.setAttribute('aria-expanded', 'false');
    }

    function scheduleClose() {
      window.clearTimeout(closeTimer);
      closeTimer = window.setTimeout(() => {
        if (detailTrigger.matches(':hover, :focus') || detailPopover.matches(':hover')) return;
        hidePopover();
      }, 120);
    }

    detailTrigger.addEventListener('mouseenter', showPopover);
    detailTrigger.addEventListener('mouseleave', scheduleClose);
    detailTrigger.addEventListener('focus', showPopover);
    detailTrigger.addEventListener('blur', scheduleClose);
    detailTrigger.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      showPopover();
    });
    detailPopover.addEventListener('mouseenter', () => window.clearTimeout(closeTimer));
    detailPopover.addEventListener('mouseleave', scheduleClose);
    document.addEventListener('click', event => {
      if (!detailTrigger.contains(event.target) && !detailPopover.contains(event.target)) hidePopover();
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !detailPopover.hidden) {
        hidePopover();
      }
    });
    window.addEventListener('scroll', () => {
      if (!detailPopover.hidden) positionPopover();
    }, { passive: true });
    window.addEventListener('resize', () => {
      if (!detailPopover.hidden) positionPopover();
    });
  }

  if (!checkbox || checkbox.disabled) return;

  const feedback = form.querySelector('[data-maintenance-feedback]');
  const status = form.querySelector('[data-maintenance-status]');
  const retry = form.querySelector('[data-maintenance-retry]');
  const price = form.querySelector('[data-maintenance-price]');
  const monthlyTotal = document.querySelector('[data-monthly-total]');
  const monthlyTotalNote = document.querySelector('[data-monthly-total-note]');
  const printRow = document.querySelector('[data-maintenance-print]');
  const printPrice = document.querySelector('[data-maintenance-print-price]');
  const dependentLinks = document.querySelectorAll('[data-maintenance-dependent]');
  let savedSelection = checkbox.checked;
  let requestedSelection = savedSelection;
  let busy = false;
  let unresolved = false;
  const withoutMonthlySuffix = value => value.replace(/／月$/, '');

  dependentLinks.forEach(link => link.addEventListener('click', event => {
    if (busy || unresolved) event.preventDefault();
  }));

  function blockNavigation(blocked) {
    dependentLinks.forEach(link => {
      if (blocked) link.setAttribute('aria-disabled', 'true');
      else link.removeAttribute('aria-disabled');
    });
  }

  async function save() {
    if (busy) return;
    busy = true;
    const data = new FormData(form);
    data.set('maintenance', requestedSelection ? '1' : '0');
    checkbox.disabled = true;
    form.setAttribute('aria-busy', 'true');
    feedback.classList.add('visually-hidden');
    feedback.hidden = false;
    retry.hidden = true;
    status.textContent = '保存中…';
    blockNavigation(true);
    try {
      const response = await fetch(form.action, {
        method: 'POST', body: data, credentials: 'same-origin',
        headers: {Accept: 'application/json'},
      });
      if (!response.ok) throw new Error('Save failed');
      const result = await response.json();
      if (typeof result.selected !== 'boolean' || typeof result.price_label !== 'string' || typeof result.available !== 'boolean' || typeof result.monthly_total_label !== 'string' || typeof result.monthly_total_note !== 'string') {
        throw new Error('Invalid response');
      }
      savedSelection = result.selected;
      checkbox.checked = savedSelection;
      checkbox.disabled = !result.available && !savedSelection;
      price.textContent = withoutMonthlySuffix(result.price_label);
      if (detailPrice) detailPrice.textContent = withoutMonthlySuffix(result.price_label);
      if (monthlyTotal) monthlyTotal.textContent = withoutMonthlySuffix(result.monthly_total_label);
      if (monthlyTotalNote) {
        monthlyTotalNote.textContent = result.monthly_total_note;
        monthlyTotalNote.hidden = !result.monthly_total_note;
      }
      if (printRow) printRow.hidden = !savedSelection;
      if (printPrice) printPrice.textContent = `${withoutMonthlySuffix(result.price_label)}（初期費用には含みません）`;
      unresolved = false;
      feedback.hidden = true;
      blockNavigation(false);
    } catch {
      checkbox.checked = savedSelection;
      checkbox.disabled = true;
      unresolved = true;
      status.textContent = '保存結果を確認できませんでした。再試行してください。';
      retry.hidden = false;
      feedback.classList.remove('visually-hidden');
    } finally {
      busy = false;
      form.removeAttribute('aria-busy');
    }
  }

  checkbox.addEventListener('change', () => {
    requestedSelection = checkbox.checked;
    save();
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    requestedSelection = checkbox.checked;
    save();
  });
  retry.addEventListener('click', save);
})();
