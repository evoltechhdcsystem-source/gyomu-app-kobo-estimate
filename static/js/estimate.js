const estimateFormatter = new Intl.NumberFormat("ja-JP");

function setCurrentTotal(total) {
  document.querySelectorAll("[data-current-total]").forEach((element) => {
    element.textContent = `${estimateFormatter.format(total)}円`;
  });
  document.querySelectorAll("[data-estimate-total]").forEach((element) => {
    element.textContent = `${estimateFormatter.format(total)}円`;
  });
}

function setFeatureTotal(total) {
  document.querySelectorAll("[data-feature-total]").forEach((element) => {
    element.textContent = `${estimateFormatter.format(total)}円`;
  });
}

function setScreenTotal(total) {
  document.querySelectorAll("[data-screen-total]").forEach((element) => {
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
  const quantityInputs = Array.from(form.querySelectorAll('input[name^="feature_quantities["]'));

  function quantityInputFor(feature) {
    return quantityInputs.find((input) => input.name === `feature_quantities[${feature}]`);
  }

  function featureInputFor(feature) {
    return form.querySelector(`input[name="features"][value="${CSS.escape(feature)}"]`);
  }

  function uncheckZeroQuantityFeatures() {
    quantityInputs.forEach((input) => {
      if (Number(input.value) > 0) return;

      const feature = input.name.replace(/^feature_quantities\[(.*)\]$/, "$1");
      const featureInput = featureInputFor(feature);
      if (featureInput?.checked) {
        featureInput.checked = false;
      }
      input.value = "1";
    });
  }

  function update() {
    uncheckZeroQuantityFeatures();

    const screens = Math.max(Number(screensInput?.value || 0), 0);
    const screenTotal = unitPrice * screens;
    const featureTotal = Array.from(form.querySelectorAll('input[name="features"]:checked'))
      .reduce((sum, item) => {
        const quantityInput = quantityInputFor(item.value);
        const quantity = item.dataset.quantityEnabled === "true"
          ? Math.max(Number(quantityInput?.value || 1), 1)
          : 1;
        return sum + (Number(item.dataset.price || 0) * quantity);
      }, 0);

    quantityInputs.forEach((input) => {
      const feature = input.name.replace(/^feature_quantities\[(.*)\]$/, "$1");
      const checked = Array.from(form.querySelectorAll('input[name="features"]:checked'))
        .some((item) => item.value === feature);
      input.disabled = !checked;
    });

    setScreenTotal(screenTotal);
    setFeatureTotal(featureTotal);
    setCurrentTotal(screenTotal + featureTotal);
  }

  form.addEventListener("change", update);
  form.addEventListener("input", update);
  form.addEventListener("submit", (event) => {
    const featureInputs = Array.from(form.querySelectorAll('input[name="features"]'));
    const hasFeature = featureInputs.some((item) => item.checked);
    if (!hasFeature) {
      event.preventDefault();
      showInlineError(form, {
        title: "追加機能を選ぶと結果へ進めます",
        detail: "カスタムパックでは、必要な機能を1つ以上選択してください。"
      });
    }
  });
  update();
}

bindPackageEstimate();
bindCustomEstimate();
