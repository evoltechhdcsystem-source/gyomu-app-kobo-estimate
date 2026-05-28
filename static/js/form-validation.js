function getInlineError(form) {
  let error = form.querySelector(".form-inline-error");
  if (error) return error;

  error = document.createElement("div");
  error.className = "form-inline-error";
  error.setAttribute("role", "alert");
  error.setAttribute("aria-live", "polite");
  error.innerHTML = `
    <span class="form-inline-error-icon" aria-hidden="true">!</span>
    <span class="form-inline-error-copy">
      <strong data-inline-error-title></strong>
      <span data-inline-error-message></span>
    </span>
  `;

  const actions = form.querySelector(".wizard-actions");
  if (actions) {
    form.insertBefore(error, actions);
  } else {
    form.prepend(error);
  }
  return error;
}

function showInlineError(form, message) {
  const error = getInlineError(form);
  const content = typeof message === "string"
    ? { title: "選択してください", detail: message }
    : message;

  error.querySelector("[data-inline-error-title]").textContent = content.title;
  error.querySelector("[data-inline-error-message]").textContent = content.detail;
  error.classList.add("is-visible");
  form.classList.add("has-inline-error");
  error.scrollIntoView({ block: "center", behavior: "smooth" });
}

function clearInlineError(form) {
  const error = form.querySelector(".form-inline-error");
  if (!error) return;
  error.classList.remove("is-visible");
  form.classList.remove("has-inline-error");
}

function focusNextButton(form) {
  const nextButton = form.querySelector('.wizard-actions button[type="submit"]');
  if (!nextButton) return;

  window.setTimeout(() => nextButton.focus(), 0);
}

function messageForField(field) {
  if (field.name === "device_type") {
    return {
      title: "端末を選ぶと次へ進めます",
      detail: "タブレット、スマートフォン、3タイプ対応の中から1つ選択してください。"
    };
  }
  if (field.name === "package_type") {
    return {
      title: "パックを選ぶと次へ進めます",
      detail: "現場で使いたい内容に近いパックを1つ選択してください。"
    };
  }
  if (field.name === "custom_screens") {
    return {
      title: "画面数を入力してください",
      detail: "作りたい画面数を1以上で入力してください。"
    };
  }
  return {
    title: "未入力の項目があります",
    detail: "必要な項目を入力してから次へ進んでください。"
  };
}

function bindWizardValidation() {
  document.querySelectorAll("form.wizard-form").forEach((form) => {
    form.addEventListener(
      "invalid",
      (event) => {
        const field = event.target;
        if (field.matches('[required]')) {
          event.preventDefault();
          showInlineError(form, messageForField(field));
        }
      },
      true
    );

    form.addEventListener("change", (event) => {
      clearInlineError(form);
      if (event.target.matches('input[type="radio"][name="device_type"], input[type="radio"][name="package_type"]')) {
        focusNextButton(form);
      }
    });
    form.addEventListener("input", () => clearInlineError(form));
  });
}

bindWizardValidation();
