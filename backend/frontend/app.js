const $ = (selector) => document.querySelector(selector);
const conversation = $("#conversation");
const question = $("#question");
const sendButton = $("#send-button");
const indexButton = $("#index-button");
const providerSelect = $("#provider-select");
const projectSelect = $("#project-select");
const newProjectButton = $("#new-project-button");
const removeProjectButton = $("#remove-project-button");
const themeToggle = $("#theme-toggle");
const sidebarNewChatButton = $("#sidebar-new-chat");
const toast = $("#toast");
let activeProvider = localStorage.getItem("documind-provider") || "gemini";
let activeProject = localStorage.getItem("documind-project") || "general";
let activeChat = localStorage.getItem(`documind-chat-${activeProject}`) || "";
let currentStatus = null;

function providerLabel(provider) {
  return { gemini: "Gemini", openai: "OpenAI GPT", claude_cli: "Claude Pro / CLI" }[provider] || provider;
}

function providerSetup(provider) {
  return { gemini: "GEMINI_API_KEY", openai: "OPENAI_API_KEY", claude_cli: "a signed-in Claude Code CLI" }[provider];
}

function projectUrl(action) {
  return `/api/projects/${encodeURIComponent(activeProject)}/${action}`;
}

function chatUrl(chatId, action = "") {
  const base = `${projectUrl("chats")}/${encodeURIComponent(chatId)}`;
  return action ? `${base}/${action}` : base;
}

function renderProjects(projects) {
  if (!projects.some((project) => project.id === activeProject)) activeProject = "general";
  projectSelect.replaceChildren();
  projects.forEach((project) => {
    const option = document.createElement("option");
    option.value = project.id;
    option.textContent = project.name;
    projectSelect.append(option);
  });
  projectSelect.value = activeProject;
}

function resetConversation(name) {
  conversation.replaceChildren();
  const welcome = document.createElement("article");
  welcome.className = "welcome-card";
  welcome.id = "welcome-card";
  welcome.innerHTML = `<div class="orb">✦</div><p class="eyebrow">Project workspace</p><h2></h2><p>Only documents in this project are used for indexing and answers. Add files, index this project, then ask a focused question.</p>`;
  welcome.querySelector("h2").textContent = name;
  conversation.append(welcome);
}

function renderChats(chats) {
  const list = $("#chat-list");
  list.replaceChildren();
  if (!chats.length) {
    list.innerHTML = '<p class="empty-list">No saved chats yet.</p>';
  }
  chats.forEach((chat) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `chat-item${chat.id === activeChat ? " active" : ""}`;
    item.textContent = chat.title;
    item.title = chat.title;
    item.addEventListener("click", () => openChat(chat.id));
    list.append(item);
  });
}

async function refreshChats() {
  const data = await request(projectUrl("chats"));
  renderChats(data.chats);
  return data.chats;
}

async function createChat() {
  const data = await request(projectUrl("chats"), { method: "POST", body: "{}" });
  activeChat = data.chat.id;
  localStorage.setItem(`documind-chat-${activeProject}`, activeChat);
  renderChats(data.chats);
  resetConversation(data.chat.title);
  return data.chat;
}

async function openChat(chatId) {
  try {
    const data = await request(chatUrl(chatId));
    activeChat = data.chat.id;
    localStorage.setItem(`documind-chat-${activeProject}`, activeChat);
    renderChats(await refreshChats());
    conversation.replaceChildren();
    if (!data.chat.messages.length) resetConversation(data.chat.title);
    data.chat.messages.forEach((message) => {
      if (message.role === "user") addUserMessage(message.content);
      else addAnswer({ answer: message.content, sources: message.sources || [], evaluation: message.evaluation });
    });
  } catch (error) { showToast(error.message, true); }
}

function bytes(value) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function showToast(message, error = false) {
  toast.textContent = message;
  toast.className = `toast show${error ? " error" : ""}`;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => { toast.className = "toast"; }, 4200);
}

function appendInlineMarkdown(target, text) {
  const pattern = /(\*\*([^*]+)\*\*|`([^`]+)`)/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    target.append(document.createTextNode(text.slice(cursor, match.index)));
    const element = document.createElement(match[2] ? "strong" : "code");
    element.textContent = match[2] || match[3];
    target.append(element);
    cursor = match.index + match[0].length;
  }
  target.append(document.createTextNode(text.slice(cursor)));
}

function makeTextElement(tagName, text) {
  const element = document.createElement(tagName);
  appendInlineMarkdown(element, text);
  return element;
}

function renderMarkdown(markdown, target) {
  target.replaceChildren();
  const lines = String(markdown).replace(/\r\n/g, "\n").split("\n");
  let index = 0;
  const isBlockStart = (line) => /^(#{1,4}\s+|[-*+]\s+|\d+\.\s+|```|---\s*$)/.test(line);

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index += 1; continue; }
    if (line.startsWith("```")) {
      const codeLines = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) codeLines.push(lines[index++]);
      if (index < lines.length) index += 1;
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      code.textContent = codeLines.join("\n");
      pre.append(code);
      target.append(pre);
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      target.append(makeTextElement(`h${heading[1].length}`, heading[2]));
      index += 1;
      continue;
    }
    if (/^---\s*$/.test(line)) {
      target.append(document.createElement("hr"));
      index += 1;
      continue;
    }
    const bullet = line.match(/^[-*+]\s+(.+)$/);
    const numbered = line.match(/^\d+\.\s+(.+)$/);
    if (bullet || numbered) {
      const list = document.createElement(bullet ? "ul" : "ol");
      const pattern = bullet ? /^[-*+]\s+(.+)$/ : /^\d+\.\s+(.+)$/;
      while (index < lines.length) {
        const item = lines[index].match(pattern);
        if (!item) break;
        list.append(makeTextElement("li", item[1]));
        index += 1;
      }
      target.append(list);
      continue;
    }
    const paragraph = [line.trim()];
    index += 1;
    while (index < lines.length && lines[index].trim() && !isBlockStart(lines[index])) paragraph.push(lines[index++].trim());
    target.append(makeTextElement("p", paragraph.join(" ")));
  }
}

async function request(url, options = {}) {
  const response = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

function renderLibrary(data) {
  currentStatus = data;
  const project = data.project || { id: activeProject, name: "General library" };
  activeProject = project.id;
  localStorage.setItem("documind-project", activeProject);
  $("#project-heading").textContent = project.name;
  $("#library-title").textContent = `${project.name} library`;
  removeProjectButton.disabled = activeProject === "general";
  removeProjectButton.title = removeProjectButton.disabled ? "The general library can't be removed." : `Remove ${project.name}`;
  const providers = data.providers || {};
  if (!(activeProvider in providers)) activeProvider = "gemini";
  providerSelect.value = activeProvider;
  const library = data.library || [];
  $("#document-count").textContent = library.length;
  const container = $("#documents");
  container.replaceChildren();
  if (!library.length) {
    container.innerHTML = '<p class="empty-list">Add a PDF, Markdown, or text file to get started.</p>';
  } else {
    library.forEach((file) => {
      const suffix = file.name.split(".").pop().toUpperCase();
      const item = document.createElement("div");
      item.className = "document";
      item.innerHTML = `<span class="file-icon">${suffix}</span><div><div class="document-name"></div><div class="document-size">${bytes(file.size)}</div></div>`;
      const name = item.querySelector(".document-name");
      name.textContent = file.name;
      name.title = file.name;
      container.append(item);
    });
  }
  const indexStatus = $("#index-status");
  const configured = providers[activeProvider] === true;
  const providerName = providerLabel(activeProvider);
  if (data.indexed) {
    if (data.provider === activeProvider) {
      indexStatus.classList.add("ready");
      indexStatus.lastElementChild.textContent = `${data.chunks} passages indexed with ${providerName} · ready to ask`;
    } else {
      indexStatus.classList.remove("ready");
      indexStatus.lastElementChild.textContent = `Indexed with ${providerLabel(data.provider)} · select it or reindex`;
    }
  } else {
    indexStatus.classList.remove("ready");
    indexStatus.lastElementChild.textContent = !configured ? `Configure ${providerSetup(activeProvider)}` : library.length ? "Library needs indexing" : "Add documents to begin";
  }
  indexButton.disabled = configured === false;
  indexButton.title = configured === false ? `Configure ${providerSetup(activeProvider)}, then refresh this page.` : "";
}

function scrollToBottom() { conversation.scrollTop = conversation.scrollHeight; }

function addUserMessage(text) {
  $("#welcome-card")?.remove();
  const message = document.createElement("article");
  message.className = "message user";
  message.textContent = text;
  conversation.append(message);
  scrollToBottom();
}

function webSearchUrl(source) {
  const name = source.source.replace(/\.[^./]+$/, "");
  const snippet = (source.text || "").trim().split(/\s+/).slice(0, 12).join(" ");
  return `https://www.google.com/search?q=${encodeURIComponent(`${name} ${snippet}`)}`;
}

function addSource(container, source) {
  const item = document.createElement("div");
  item.className = "source";
  item.tabIndex = 0;
  item.innerHTML = '<span></span><a class="source-link" target="_blank" rel="noopener noreferrer">Search the web ↗</a><div class="source-excerpt"></div>';
  item.querySelector("span").textContent = `${source.source} · passage ${source.index + 1}`;
  item.querySelector(".source-link").href = webSearchUrl(source);
  item.querySelector(".source-excerpt").textContent = source.text?.trim() || "No excerpt available for this passage.";
  container.append(item);
}

function addAnswer(data) {
  const message = document.createElement("article");
  message.className = "message answer-card";
  message.innerHTML = '<div class="answer-label"><span>✦</span> DocuMind answer</div><div class="answer-body"></div><div class="sources"><span class="source-title">Retrieved sources</span></div>';
  renderMarkdown(data.answer, message.querySelector(".answer-body"));
  const sourcesEl = message.querySelector(".sources");
  data.sources.forEach((source) => addSource(sourcesEl, source));
  conversation.append(message);
  scrollToBottom();
}

function setBusy(button, busy, label) {
  button.disabled = busy;
  if (busy) { button.dataset.label = button.textContent; button.textContent = label; }
  else if (button.dataset.label) button.textContent = button.dataset.label;
}

async function refreshStatus() {
  try { renderLibrary(await request(projectUrl("status"))); }
  catch { showToast("Could not connect to the local portal server.", true); }
}

function parseSseEvents(buffer) {
  const events = [];
  let boundary;
  while ((boundary = buffer.indexOf("\n\n")) !== -1) {
    const raw = buffer.slice(0, boundary);
    buffer = buffer.slice(boundary + 2);
    let name = "message";
    let dataLine = "";
    for (const line of raw.split("\n")) {
      if (line.startsWith("event:")) name = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLine += line.slice(5).trim();
    }
    if (dataLine) events.push([name, JSON.parse(dataLine)]);
  }
  return [events, buffer];
}

async function streamAnswer(text, onFirstToken) {
  const response = await fetch(chatUrl(activeChat, "messages"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: text, provider: activeProvider }),
  });
  if (!response.ok || !response.body) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || "Something went wrong.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let messageEl = null;
  let bodyEl = null;
  let answerText = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const [events, remainder] = parseSseEvents(buffer);
    buffer = remainder;
    for (const [name, data] of events) {
      if (name === "token") {
        if (!messageEl) {
          onFirstToken();
          messageEl = document.createElement("article");
          messageEl.className = "message answer-card";
          messageEl.innerHTML = '<div class="answer-label"><span>✦</span> DocuMind answer</div><div class="answer-body"></div>';
          conversation.append(messageEl);
          bodyEl = messageEl.querySelector(".answer-body");
        }
        answerText += data.text;
        bodyEl.textContent = answerText;
        scrollToBottom();
      } else if (name === "done") {
        messageEl?.remove();
        addAnswer(data);
        renderChats(data.chats);
      } else if (name === "error") {
        throw new Error(data.error || "Something went wrong.");
      }
    }
  }
}

$("#question-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = question.value.trim();
  if (!text) return;
  setBusy(sendButton, true, "…");
  try {
    if (!activeChat) await createChat();
  } catch (error) {
    showToast(error.message, true);
    setBusy(sendButton, false);
    return;
  }
  addUserMessage(text);
  question.value = "";
  question.style.height = "auto";
  const typing = document.createElement("div");
  typing.className = "typing";
  typing.innerHTML = "DocuMind is searching your library <i></i><i></i><i></i>";
  conversation.append(typing);
  scrollToBottom();
  try {
    await streamAnswer(text, () => typing.remove());
  }
  catch (error) { showToast(error.message, true); }
  finally { typing.remove(); setBusy(sendButton, false); }
});

async function indexLibrary() {
  if (indexButton.disabled) {
    showToast(`Configure ${providerSetup(activeProvider)}, then refresh the page to re-index your library.`, true);
    return;
  }
  setBusy(indexButton, true, "Indexing…");
  try { const data = await request(projectUrl("index"), { method: "POST", body: JSON.stringify({ provider: activeProvider }) }); renderLibrary(data); showToast(`Project re-indexed with ${providerLabel(activeProvider)}: ${data.chunks} passages are ready.`); }
  catch (error) { showToast(error.message, true); }
  finally { setBusy(indexButton, false); }
}

indexButton.addEventListener("click", indexLibrary);

$("#file-input").addEventListener("change", async (event) => {
  const [file] = event.target.files;
  if (!file) return;
  if (file.size > 25 * 1024 * 1024) { showToast("Documents must be 25 MB or smaller.", true); return; }
  const reader = new FileReader();
  reader.onload = async () => {
    try {
      const content = String(reader.result).split(",")[1];
      const data = await request(projectUrl("documents"), { method: "POST", body: JSON.stringify({ name: file.name, content }) });
      renderLibrary(data);
      showToast(data.message);
    } catch (error) { showToast(error.message, true); }
  };
  reader.readAsDataURL(file);
  event.target.value = "";
});

document.querySelectorAll("[data-question]").forEach((button) => button.addEventListener("click", () => {
  question.value = button.dataset.question;
  question.focus();
}));

providerSelect.addEventListener("change", () => {
  activeProvider = providerSelect.value;
  localStorage.setItem("documind-provider", activeProvider);
  if (currentStatus) renderLibrary(currentStatus);
});

projectSelect.addEventListener("change", async () => {
  activeProject = projectSelect.value;
  localStorage.setItem("documind-project", activeProject);
  await refreshStatus();
  try { await createChat(); } catch (error) { showToast(error.message, true); }
});

newProjectButton.addEventListener("click", async () => {
  const name = window.prompt("Name your new project");
  if (!name?.trim()) return;
  try {
    const data = await request("/api/projects", { method: "POST", body: JSON.stringify({ name }) });
    activeProject = data.project.id;
    localStorage.setItem("documind-project", activeProject);
    activeChat = "";
    renderProjects(data.projects);
    resetConversation(data.project.name);
    renderLibrary(data);
    renderChats([]);
    showToast(`Created ${data.project.name}. Add project documents to begin.`);
  } catch (error) { showToast(error.message, true); }
});

removeProjectButton.addEventListener("click", async () => {
  if (removeProjectButton.disabled) return;
  const projectName = $("#project-heading").textContent;
  if (!window.confirm(`Remove "${projectName}"? This deletes its documents, index, and chat history. This can't be undone.`)) return;
  try {
    const data = await request(`/api/projects/${encodeURIComponent(activeProject)}`, { method: "DELETE" });
    activeProject = "general";
    localStorage.setItem("documind-project", activeProject);
    activeChat = "";
    renderProjects(data.projects);
    resetConversation("General library");
    await refreshStatus();
    await refreshChats();
    showToast(`Removed ${projectName}.`);
  } catch (error) { showToast(error.message, true); }
});

sidebarNewChatButton.addEventListener("click", () => createChat().catch((error) => showToast(error.message, true)));

question.addEventListener("input", () => { question.style.height = "auto"; question.style.height = `${Math.min(question.scrollHeight, 180)}px`; });
question.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); $("#question-form").requestSubmit(); } });

async function initializePortal() {
  try {
    const data = await request("/api/projects");
    renderProjects(data.projects);
    await refreshStatus();
    const chats = await refreshChats();
    if (activeChat && chats.some((chat) => chat.id === activeChat)) await openChat(activeChat);
  } catch {
    showToast("Could not connect to the local portal server.", true);
  }
}

const THEME_KEY = "documind-theme";

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  themeToggle.textContent = theme === "light" ? "☀️" : "🌙";
  themeToggle.title = theme === "light" ? "Switch to dark mode" : "Switch to light mode";
  themeToggle.setAttribute("aria-label", themeToggle.title);
}

function initTheme() {
  const stored = localStorage.getItem(THEME_KEY);
  applyTheme(stored || (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));
}

themeToggle.addEventListener("click", () => {
  const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
});

initTheme();
initializePortal();
