const form = document.querySelector("#chat-form");
const input = document.querySelector("#prompt-input");
const messages = document.querySelector("#messages");
const sendButton = document.querySelector("#send-button");
const statusPill = document.querySelector("#status-pill");
const baseUrl = document.querySelector("#base-url");
const modelName = document.querySelector("#model-name");
const promptButtons = document.querySelectorAll("[data-prompt]");

const conversation = [];

async function loadConfig() {
  try {
    const response = await fetch("/api/config");
    const config = await response.json();
    baseUrl.textContent = config.sentinelguard_base_url;
    modelName.textContent = config.chat_model;
  } catch {
    baseUrl.textContent = "unavailable";
    modelName.textContent = "unavailable";
  }
}

function setStatus(text, isError = false) {
  statusPill.textContent = text;
  statusPill.classList.toggle("error", isError);
}

function appendMessage(role, content, isError = false) {
  const article = document.createElement("article");
  article.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "You" : "SG";

  const bubble = document.createElement("div");
  bubble.className = `bubble${isError ? " error" : ""}`;
  bubble.textContent = content;

  article.append(avatar, bubble);
  messages.append(article);
  messages.scrollTop = messages.scrollHeight;
}

function summarizeGatewayError(data) {
  const error = data?.gateway?.error || data?.detail || {};
  const type = error.type || "gateway_error";
  const failed = Array.isArray(error.failed_scanners)
    ? `\nFailed scanners: ${error.failed_scanners.join(", ")}`
    : "";
  const risk = error.risk ? `\nRisk: ${error.risk}` : "";
  const message = error.message || "SentinelGuard rejected or failed the request.";
  return `${message}\nType: ${type}${risk}${failed}`;
}

async function sendPrompt(prompt) {
  const content = prompt.trim();
  if (!content) {
    return;
  }

  appendMessage("user", content);
  conversation.push({ role: "user", content });
  input.value = "";
  sendButton.disabled = true;
  setStatus("Scanning");

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: conversation }),
    });
    const data = await response.json();

    if (!data.ok) {
      conversation.pop();
      appendMessage("assistant", summarizeGatewayError(data), true);
      setStatus("Blocked", true);
      return;
    }

    const answer = data.message || "The gateway returned an empty response.";
    conversation.push({ role: "assistant", content: answer });
    appendMessage("assistant", answer);
    setStatus("Passed");
  } catch (error) {
    conversation.pop();
    appendMessage("assistant", `Chatbot backend error: ${error.message}`, true);
    setStatus("Error", true);
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendPrompt(input.value);
});

promptButtons.forEach((button) => {
  button.addEventListener("click", () => {
    input.value = button.dataset.prompt || "";
    input.focus();
  });
});

loadConfig();
