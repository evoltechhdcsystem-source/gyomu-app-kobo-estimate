const estimateFormatter = new Intl.NumberFormat("ja-JP");

function setCurrentTotal(total) {
  document.querySelectorAll("[data-current-total]").forEach((element) => {
    element.textContent = `${estimateFormatter.format(total)}円`;
  });
  document.querySelectorAll("[data-estimate-total]").forEach((element) => {
    element.innerHTML = `${estimateFormatter.format(total)}円<span class="tax-note">（税抜）</span>`;
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
  const packageFeatureTotals = window.estimateConfig?.packageFeatureTotals || {};

  function update() {
    const selected = form.querySelector('input[name="package_type"]:checked');
    if (!selected) {
      setCurrentTotal(0);
      return;
    }

    const screens = Number(selected.dataset.screens || 0);
    const featureTotal = Number(packageFeatureTotals[selected.value] || 0);
    const total = (unitPrice * screens) + featureTotal;
    setCurrentTotal(total);
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

function bindFeatureDetailModal() {
  const modalElement = document.getElementById("featureDetailPopover");
  const triggers = Array.from(document.querySelectorAll("[data-feature-detail-trigger]"));
  if (!modalElement || !triggers.length) return;

  const fields = {
    name: modalElement.querySelector("[data-feature-modal-name]"),
    price: modalElement.querySelector("[data-feature-modal-price]"),
    condition: modalElement.querySelector("[data-feature-modal-condition]"),
    description: modalElement.querySelector("[data-feature-modal-description]")
  };
  let activeTrigger = null;
  let closeTimer = null;

  function setText(element, value) {
    if (element) element.textContent = value || "";
  }

  function showFor(trigger) {
    activeTrigger = trigger;
    window.clearTimeout(closeTimer);
    setText(fields.name, trigger.dataset.featureName);
    setText(fields.price, trigger.dataset.featurePrice);
    setText(fields.condition, trigger.dataset.featureCondition);
    setText(fields.description, trigger.dataset.featureDescription);
    modalElement.hidden = false;
    positionNearTrigger(trigger);
  }

  function positionNearTrigger(trigger) {
    const gap = 10;
    const rect = trigger.getBoundingClientRect();
    const modalRect = modalElement.getBoundingClientRect();
    const viewportWidth = document.documentElement.clientWidth;
    const viewportHeight = document.documentElement.clientHeight;
    const left = Math.min(
      Math.max(rect.left, gap),
      viewportWidth - modalRect.width - gap
    );
    let top = rect.bottom + gap;
    if (top + modalRect.height > viewportHeight - gap) {
      top = Math.max(rect.top - modalRect.height - gap, gap);
    }
    modalElement.style.left = `${left}px`;
    modalElement.style.top = `${top}px`;
  }

  function scheduleClose() {
    window.clearTimeout(closeTimer);
    closeTimer = window.setTimeout(() => {
      if (activeTrigger?.matches(":hover") || modalElement.matches(":hover")) return;
      modalElement.hidden = true;
    }, 120);
  }

  triggers.forEach((trigger) => {
    trigger.addEventListener("mousedown", (event) => event.stopPropagation());
    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      showFor(trigger);
    });
    trigger.addEventListener("focus", () => showFor(trigger));
    trigger.addEventListener("blur", scheduleClose);
    trigger.addEventListener("mouseenter", () => showFor(trigger));
    trigger.addEventListener("mouseleave", scheduleClose);
  });

  modalElement.addEventListener("mouseenter", () => window.clearTimeout(closeTimer));
  modalElement.addEventListener("mouseleave", scheduleClose);
  window.addEventListener("scroll", () => {
    if (!modalElement.hidden && activeTrigger) positionNearTrigger(activeTrigger);
  }, { passive: true });
  window.addEventListener("resize", () => {
    if (!modalElement.hidden && activeTrigger) positionNearTrigger(activeTrigger);
  });
}

bindPackageEstimate();
bindCustomEstimate();
bindFeatureDetailModal();
