(() => {
  const form = document.querySelector('.maintenance-option-form');
  const checkbox = form?.querySelector('input[name="maintenance"]');
  if (!checkbox || checkbox.disabled) return;

  const feedback = form.querySelector('[data-maintenance-feedback]');
  const status = form.querySelector('[data-maintenance-status]');
  const retry = form.querySelector('[data-maintenance-retry]');
  const price = form.querySelector('[data-maintenance-price]');
  const printRow = document.querySelector('[data-maintenance-print]');
  const printPrice = document.querySelector('[data-maintenance-print-price]');
  const dependentLinks = document.querySelectorAll('[data-maintenance-dependent]');
  let savedSelection = checkbox.checked;
  let requestedSelection = savedSelection;
  let busy = false;
  let unresolved = false;

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
      if (typeof result.selected !== 'boolean' || typeof result.price_label !== 'string' || typeof result.available !== 'boolean') {
        throw new Error('Invalid response');
      }
      savedSelection = result.selected;
      checkbox.checked = savedSelection;
      checkbox.disabled = !result.available && !savedSelection;
      price.textContent = result.price_label;
      if (printRow) printRow.hidden = !savedSelection;
      if (printPrice) printPrice.textContent = `${result.price_label}（初期費用には含みません）`;
      unresolved = false;
      feedback.hidden = true;
      blockNavigation(false);
    } catch {
      checkbox.checked = savedSelection;
      checkbox.disabled = true;
      unresolved = true;
      status.textContent = '保存結果を確認できませんでした。再試行してください。';
      retry.hidden = false;
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
