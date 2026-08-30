document.addEventListener("DOMContentLoaded", () => {
  const dictionary = window.PAGE_TRANSLATIONS || {};
  if (Object.keys(dictionary).length) {
    const orderedTranslations = Object.entries(dictionary).sort((a, b) => b[0].length - a[0].length);
    const translateString = (source) => {
      if (!source) return source;
      const key = source.trim();
      if (dictionary[key]) return source.replace(key, dictionary[key]);
      let translated = source;
      orderedTranslations.forEach(([from, to]) => {
        if (translated.includes(from)) translated = translated.split(from).join(to);
      });
      return translated;
    };
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach((node) => {
      if (["SCRIPT", "STYLE"].includes(node.parentElement?.tagName)) return;
      const source = node.nodeValue || "";
      node.nodeValue = translateString(source);
    });
    document.querySelectorAll("[placeholder], [aria-label], [title], [alt], [data-confirm]").forEach((element) => {
      ["placeholder", "aria-label", "title", "alt", "data-confirm"].forEach((attribute) => {
        if (element.hasAttribute(attribute)) element.setAttribute(attribute, translateString(element.getAttribute(attribute)));
      });
    });
    document.title = translateString(document.title);
  }
  document.querySelectorAll("[data-modal-open]").forEach((button) => {
    button.addEventListener("click", () => document.getElementById(button.dataset.modalOpen)?.classList.add("open"));
  });
  document.querySelectorAll("[data-modal-close]").forEach((button) => {
    button.addEventListener("click", () => button.closest(".modal")?.classList.remove("open"));
  });
  document.querySelectorAll(".modal").forEach((modal) => {
    modal.addEventListener("click", (event) => { if (event.target === modal) modal.classList.remove("open"); });
  });
  document.querySelector("[data-mobile-menu]")?.addEventListener("click", () => document.querySelector(".sidebar")?.classList.toggle("open"));
  document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => { if (!window.confirm(form.dataset.confirm)) event.preventDefault(); });
  });
  document.querySelectorAll(".flash").forEach((item) => setTimeout(() => item.remove(), 4200));
  document.querySelectorAll("[data-part-select]").forEach((select) => {
    const update = () => {
      const option = select.selectedOptions[0];
      const scope = select.closest("form");
      if (!option || !scope) return;
      scope.querySelectorAll("[data-part-field]").forEach((field) => {
        const key = field.dataset.partField;
        field.value = option.dataset[key] || "";
      });
    };
    select.addEventListener("change", update); update();
  });
  document.querySelectorAll("[data-replacement-select]").forEach((select) => {
    const update = () => {
      const target = document.getElementById(select.dataset.replacementSelect);
      if (target) target.style.display = select.value === "yes" ? "grid" : "none";
    };
    select.addEventListener("change", update); update();
  });
  document.querySelector("[data-toggle-password]")?.addEventListener("click", (event) => {
    const button = event.currentTarget;
    const input = document.querySelector("[data-login-password]");
    if (!input) return;
    const showing = input.type === "text";
    input.type = showing ? "password" : "text";
    button.textContent = showing ? button.dataset.showLabel : button.dataset.hideLabel;
    button.setAttribute("aria-label", button.textContent);
    input.focus();
  });
  document.querySelectorAll("[data-demo-login]").forEach((button) => {
    button.addEventListener("click", () => {
      const form = document.querySelector("[data-login-form]");
      const username = document.querySelector("[data-login-username]");
      const password = document.querySelector("[data-login-password]");
      if (!form || !username || !password) return;
      username.value = button.dataset.demoUsername || "";
      password.value = button.dataset.demoPassword || "";
      form.requestSubmit();
    });
  });
});
