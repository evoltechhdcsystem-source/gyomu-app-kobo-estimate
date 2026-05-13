const estimateFormatter = new Intl.NumberFormat("ja-JP");

function setCurrentTotal(total) {
  document.querySelectorAll("[data-current-total]").forEach((element) => {
    element.textContent = `${estimateFormatter.format(total)}円`;
  });
}

function bindPackageEstimate() {
  const form = document.querySelector('form.wizard-form input[name="package_type"]')?.form;
  if (!form) return;

  const unitPrice = Number(window.estimateConfig?.unitPrice || 0);

  function update() {
    const selected = form.querySelector('input[name="package_type"]:checked');
    if (!selected) {
      setCurrentTotal(0);
      return;
    }

    const screens = Number(selected.dataset.screens || 0);
    setCurrentTotal(unitPrice * screens);
  }

  form.addEventListener("change", update);
  update();
}

function bindCustomEstimate() {
  const form = document.getElementById("customEstimateForm");
  if (!form) return;

  const unitPrice = Number(window.estimateConfig?.unitPrice || 0);
  const screensInput = form.querySelector("#custom_screens");

  function update() {
    const screens = Math.max(Number(screensInput?.value || 0), 0);
    const featureTotal = Array.from(form.querySelectorAll('input[name="features"]:checked'))
      .reduce((sum, item) => sum + Number(item.dataset.price || 0), 0);

    setCurrentTotal((unitPrice * screens) + featureTotal);
  }

  form.addEventListener("change", update);
  form.addEventListener("input", update);
  update();
}

bindPackageEstimate();
bindCustomEstimate();
