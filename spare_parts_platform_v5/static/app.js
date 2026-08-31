/**
 * 全站前端增强脚本。
 *
 * 页面核心内容由 Flask/Jinja2 在服务器端生成；本文件只负责无需刷新页面的增强交互：
 * 英文文本兜底翻译、弹窗、移动菜单、确认框、表单联动、密码显示、演示账户登录，
 * 以及右侧 AI 助手的预警刷新和异步问答。即使 JavaScript 不可用，主要业务页面仍可阅读。
 */
document.addEventListener("DOMContentLoaded", () => {
  // ---------- 1. 英文模式兜底翻译 ----------
  // 服务端已完成主要翻译；这里继续处理浏览器中动态生成的文本和可见属性。
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
  // ---------- 2. 通用弹窗、移动导航和危险操作确认 ----------
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
  // ---------- 3. 业务表单联动 ----------
  // 选择备件后，把选项 data-* 中的规格、货位、库存等信息填入同一表单。
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
  // 只有确认换件时才展示领用备件区域，减少无关字段。
  document.querySelectorAll("[data-replacement-select]").forEach((select) => {
    const update = () => {
      const target = document.getElementById(select.dataset.replacementSelect);
      if (target) target.style.display = select.value === "yes" ? "grid" : "none";
    };
    select.addEventListener("change", update); update();
  });
  // ---------- 4. 登录页辅助功能 ----------
  // 切换 password/text 类型实现显示密码，并同步无障碍标签。
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
  // 演示账户按钮只填充当前表单并正常提交，认证仍由服务器完成。
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

  // ---------- 5. AI 助手面板 ----------
  // data-* 属性由 base.html 注入接口地址、CSRF 令牌和中英文提示。
  const assistantLayer = document.querySelector("[data-assistant-layer]");
  const assistantPanel = assistantLayer?.querySelector(".assistant-panel");
  const assistantMessages = assistantLayer?.querySelector("[data-assistant-messages]");
  const assistantForm = assistantLayer?.querySelector("[data-assistant-form]");
  const assistantInput = assistantLayer?.querySelector("[data-assistant-input]");
  const assistantSend = assistantLayer?.querySelector("[data-assistant-send]");
  // 将用户/助手消息安全写入 textContent，避免把模型输出当作 HTML 执行。
  const appendAssistantMessage = (text, kind, source = "") => {
    if (!assistantMessages) return null;
    const wrapper = document.createElement("div");
    wrapper.className = `assistant-message assistant-message-${kind}`;
    const paragraph = document.createElement("p");
    paragraph.textContent = text;
    wrapper.appendChild(paragraph);
    if (source) {
      const caption = document.createElement("small");
      caption.textContent = source;
      wrapper.appendChild(caption);
    }
    assistantMessages.appendChild(wrapper);
    assistantMessages.scrollTop = assistantMessages.scrollHeight;
    return wrapper;
  };
  // 用服务器返回的只读统计刷新缺货、故障、寿命和总预警数量。
  const updateAssistantSnapshot = (snapshot) => {
    if (!snapshot) return;
    const fields = [
      ["[data-alert-low]", snapshot.low_stock],
      ["[data-alert-faults]", snapshot.faults],
      ["[data-alert-lifecycle]", snapshot.lifecycle],
      ["[data-assistant-total]", snapshot.total],
    ];
    fields.forEach(([selector, value]) => {
      document.querySelectorAll(selector).forEach((element) => {
        element.textContent = value === null || value === undefined ? "-" : String(value);
      });
    });
  };
  // 异步刷新失败时保留服务端首屏数字，不影响用户继续操作。
  const refreshAssistantAlerts = async () => {
    if (!assistantPanel?.dataset.alertsUrl) return;
    try {
      const response = await fetch(assistantPanel.dataset.alertsUrl, {
        headers: { Accept: "application/json" }, credentials: "same-origin",
      });
      if (!response.ok) return;
      const payload = await response.json();
      updateAssistantSnapshot(payload.snapshot);
    } catch (_error) {
      // 刷新不可用时仍保留服务端已经渲染的预警数量。
    }
  };
  // 打开/关闭侧滑面板，并控制焦点和页面滚动。
  const openAssistant = () => {
    if (!assistantLayer) return;
    assistantLayer.classList.add("open");
    assistantLayer.setAttribute("aria-hidden", "false");
    document.body.classList.add("assistant-open");
    refreshAssistantAlerts();
    window.setTimeout(() => assistantInput?.focus(), 180);
  };
  const closeAssistant = () => {
    if (!assistantLayer) return;
    assistantLayer.classList.remove("open");
    assistantLayer.setAttribute("aria-hidden", "true");
    document.body.classList.remove("assistant-open");
  };
  document.querySelectorAll("[data-assistant-open]").forEach((button) => button.addEventListener("click", openAssistant));
  assistantLayer?.querySelectorAll("[data-assistant-close]").forEach((button) => button.addEventListener("click", closeAssistant));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && assistantLayer?.classList.contains("open")) closeAssistant();
  });
  assistantLayer?.querySelectorAll("[data-assistant-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!assistantInput || !assistantForm) return;
      assistantInput.value = button.dataset.assistantPrompt || button.textContent.trim();
      assistantForm.requestSubmit();
    });
  });
  assistantInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      assistantForm?.requestSubmit();
    }
  });
  // ---------- 6. AI 问答请求 ----------
  // JSON 请求携带同源凭据和 CSRF；服务器决定使用本地答案还是外部 API。
  assistantForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = assistantInput?.value.trim();
    if (!message || !assistantPanel?.dataset.chatUrl) return;
    appendAssistantMessage(message, "user");
    assistantInput.value = "";
    assistantInput.disabled = true;
    if (assistantSend) assistantSend.disabled = true;
    const thinking = appendAssistantMessage(assistantPanel.dataset.thinking || "…", "ai assistant-message-thinking");
    try {
      const response = await fetch(assistantPanel.dataset.chatUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-CSRF-Token": assistantPanel.dataset.csrfToken || "",
        },
        body: JSON.stringify({ message }),
      });
      const payload = await response.json().catch(() => ({}));
      thinking?.remove();
      if (!response.ok || !payload.answer) throw new Error("assistant request failed");
      const source = payload.source === "cloudflare"
        ? assistantPanel.dataset.cloudflareSource
        : assistantPanel.dataset.localSource;
      appendAssistantMessage(payload.answer, "ai", source || "");
      refreshAssistantAlerts();
    } catch (_error) {
      thinking?.remove();
      appendAssistantMessage(assistantPanel.dataset.error || "Unable to answer.", "ai");
    } finally {
      assistantInput.disabled = false;
      if (assistantSend) assistantSend.disabled = false;
      assistantInput.focus();
    }
  });
});
