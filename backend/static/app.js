"use strict";
const $ = (id) => document.getElementById(id);
const names = {
  play: "Phát theo ID",
  users: "Người dùng",
  devices: "Thiết bị",
  settings: "Cấu hình TTS",
};
const statuses = {
  queued: "Chờ loa nhận",
  playing: "Loa đang xử lý",
  played: "Loa báo hoàn tất",
  failed: "Thất bại",
};
const state = {
  authenticated: false,
  key: "",
  users: [],
  devices: [],
  aliases: [],
  settings: null,
  editing: null,
  autoSelected: false,
  refreshing: false,
  lastDirectory: 0,
  job: null,
  audioUrl: null,
  previewVersion: 0,
  connectionCode: "",
  signatures: {},
  noticeTimer: null,
  connectionNotice: null,
  view: "play",
};
const defaultTemplate = {
  text: "{{text}}",
  voice: "{{voice}}",
  format: "pcm_s16le",
  sample_rate: 24000,
};

function element(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function notify(message, error = false) {
  clearTimeout(state.noticeTimer);
  $("notice").textContent = message;
  $("notice").classList.toggle("error", error);
  $("notice").hidden = false;
  if (!error)
    state.noticeTimer = setTimeout(() => {
      $("notice").hidden = true;
    }, 8000);
}
function serverStatus(text, connected) {
  $("serverStatus").replaceChildren(
    element("i", undefined, `dot${connected ? "" : " offline"}`),
    document.createTextNode(text),
  );
}
function errorMessage(detail) {
  if (Array.isArray(detail))
    return detail
      .map(
        (item) => `${item.loc?.slice(1).join(".") || "Dữ liệu"}: ${item.msg}`,
      )
      .join(" · ");
  const messages = {
    "Invalid operator token": "Khóa quản trị chưa đúng.",
    "Bearer token required": "Nhập khóa quản trị để kết nối.",
    "Device queue is full": "Hàng đợi loa đã đầy. Chờ xử lý xong rồi gửi tiếp.",
    "TTS connection failed":
      "Không kết nối được API TTS. Kiểm tra cấu hình và mạng của backend.",
    "TTS provider rejected request":
      "Dịch vụ TTS từ chối yêu cầu. Kiểm tra khóa, model và JSON gửi đi.",
    "This adapter expects binary audio, not a JSON audio URL":
      "Dịch vụ TTS cần trả binary audio trực tiếp.",
  };
  return messages[detail] || String(detail || "Có lỗi xảy ra.");
}
async function api(path, { method = "GET", body, binary = false } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method,
      cache: "no-store",
      credentials: "same-origin",
      headers: {
        ...(state.key ? { Authorization: `Bearer ${state.key}` } : {}),
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (_) {
    throw new Error(
      "Mất kết nối backend. Kiểm tra lịch sử trước khi gửi lại lệnh phát.",
    );
  }
  if (!response.ok) {
    let detail;
    try {
      detail = (await response.json()).detail;
    } catch (_) {
      detail = `Backend hoặc proxy trả HTTP ${response.status}. Kiểm tra log máy chủ.`;
    }
    if (response.status === 401 && state.authenticated) lockDashboard();
    throw new Error(errorMessage(detail));
  }
  if (binary) return response.blob();
  return response.status === 204 ? null : response.json();
}
async function busy(button, action, label) {
  if (button.hasAttribute("aria-busy")) return;
  const original = button.textContent;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  if (label) button.textContent = label;
  try {
    await action();
  } catch (error) {
    notify(error.message, true);
  } finally {
    button.removeAttribute("aria-busy");
    if (label) button.textContent = original;
    button.disabled = false;
    syncAvailability();
  }
}
function selectedUser() {
  return state.users.find(
    (user) => String(user.user_id) === $("playUser").value,
  );
}
function showView(view) {
  if (!names[view]) return;
  if (view !== "play") clearPreview();
  if (view !== "devices") hideConnection();
  state.view = view;
  for (const section of document.querySelectorAll(".view"))
    section.hidden = section.id !== `view-${view}`;
  for (const button of document.querySelectorAll(".nav-button")) {
    const active = button.dataset.view === view;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  $("viewName").textContent = names[view];
}
function syncAvailability() {
  const user = selectedUser();
  const device = state.devices.find((item) => item.id === user?.device_id);
  const authenticated = state.authenticated;
  const flags = {
    playButton:
      authenticated &&
      !!user &&
      !!state.settings?.provider &&
      device?.configured,
    previewButton: authenticated && !!user && !!state.settings?.provider,
    editSelectedUser: authenticated && !!user,
    saveUserButton: authenticated && state.devices.length > 0,
    saveAliasButton: authenticated && state.devices.length > 0,
    saveDeviceButton: authenticated,
    saveSettingsButton: authenticated,
    reloadSettingsButton: authenticated,
    refreshButton: authenticated,
    refreshUsersButton: authenticated,
    loadConnectionButton: authenticated && !!$("connectionDevice").value,
  };
  for (const [id, enabled] of Object.entries(flags))
    if (!$(id).hasAttribute("aria-busy")) $(id).disabled = !enabled;
  if (!authenticated)
    $("playHint").textContent = "Kết nối bảng điều khiển để bắt đầu.";
  else if (!state.users.length)
    $("playHint").textContent =
      "Mở Người dùng để đăng ký user_id, lời chào và loa trước khi phát.";
  else if (!user) $("playHint").textContent = "Chọn một người dùng đã đăng ký.";
  else if (!state.settings?.provider)
    $("playHint").textContent =
      "Mở Cấu hình TTS và lưu nguồn âm thanh trước khi phát.";
  else if (!device?.configured)
    $("playHint").textContent =
      "Loa của người dùng chưa có cấu hình kết nối hợp lệ.";
  else if (!device.online)
    $("playHint").textContent =
      `Loa ${device.id} đang offline. Gửi lệnh sẽ xếp hàng chờ loa kết nối.`;
  else
    $("playHint").textContent =
      `Loa ${device.id} đang kết nối. Mỗi lần bấm tạo một lượt phát mới.`;
}
function updateSelectedUser() {
  const user = selectedUser();
  const previousText = $("savedText").textContent;
  $("selectedUserName").textContent = user
    ? `${user.name || "Người dùng"} · ID ${user.user_id}`
    : "Chưa chọn người dùng";
  $("selectedDevice").textContent = user?.device_id || "Chưa có loa";
  $("savedText").textContent =
    user?.text_to_speech || "Lời chào đã lưu sẽ xuất hiện ở đây.";
  if (previousText !== $("savedText").textContent) clearPreview();
  $("detectBody").textContent = JSON.stringify(
    { user_id: user?.user_id || 1 },
    null,
    2,
  );
  syncAvailability();
}
function options(select, entries, placeholder) {
  const signature = JSON.stringify(entries);
  if (state.signatures[select.id] === signature) return;
  state.signatures[select.id] = signature;
  const previous = select.value;
  select.replaceChildren(
    new Option(placeholder, ""),
    ...entries.map(([id, title]) => new Option(title, String(id))),
  );
  if (entries.some(([id]) => String(id) === previous)) select.value = previous;
}
function emptyRow(body, columns, text) {
  const row = element("tr");
  const cell = element("td", text, "empty");
  cell.colSpan = columns;
  row.append(cell);
  body.replaceChildren(row);
}
function renderUsers() {
  options(
    $("playUser"),
    state.users.map((user) => [
      user.user_id,
      `${user.user_id} · ${user.name || "Người dùng"}`,
    ]),
    "Chọn người dùng đã đăng ký",
  );
  if (!state.autoSelected && state.users.length) {
    $("playUser").value = String(state.users[0].user_id);
    state.autoSelected = true;
  }
  $("userCount").textContent = state.users.length;
  $("usersTotal").textContent = `${state.users.length} người dùng`;
  updateSelectedUser();
  const signature = JSON.stringify(state.users);
  if (state.signatures.users === signature) return;
  state.signatures.users = signature;
  const body = $("usersBody");
  body.replaceChildren();
  for (const user of state.users) {
    const row = element("tr");
    const identity = element("td");
    identity.append(
      element("strong", user.name || "Chưa đặt tên"),
      element("small", `user_id: ${user.user_id}`),
    );
    const content = element("td");
    content.append(
      element("div", user.text_to_speech, "cell-text"),
      element("small", user.device_id),
    );
    const actions = element("td");
    const group = element("div", undefined, "row-actions");
    for (const [label, action] of [
      ["Chọn phát", "select-user"],
      ["Sửa", "edit-user"],
      ["Xóa", "delete-user"],
    ]) {
      const button = element(
        "button",
        label,
        `text-button${action === "delete-user" ? " danger" : ""}`,
      );
      button.type = "button";
      button.dataset.action = action;
      button.dataset.id = user.user_id;
      button.setAttribute("aria-label", `${label} người dùng ${user.user_id}`);
      group.append(button);
    }
    actions.append(group);
    row.append(identity, content, actions);
    body.append(row);
  }
  if (!state.users.length)
    emptyRow(body, 3, "Chưa có người dùng. Đăng ký ở biểu mẫu bên cạnh.");
}
function renderDevices() {
  const entries = state.devices.map((device) => [device.id, device.id]);
  for (const id of ["userDevice", "aliasDevice", "connectionDevice"])
    options($(id), entries, "Chọn thiết bị");
  if (!$("userDevice").value && !state.editing && entries.length)
    $("userDevice").value = entries[0][0];
  if (!$("aliasDevice").value && entries.length)
    $("aliasDevice").value = entries[0][0];
  if (!$("connectionDevice").value && entries.length)
    $("connectionDevice").value = entries[0][0];
  $("onlineCount").textContent = state.devices.filter(
    (device) => device.online,
  ).length;
  const list = $("deviceList");
  list.replaceChildren();
  for (const device of state.devices) {
    const item = element("div", undefined, "device-item");
    const label = element("div");
    label.append(
      element("strong", device.id),
      element(
        "small",
        device.last_seen
          ? `Kết nối gần nhất: ${formatTime(device.last_seen)}`
          : "Chưa nhận kết nối từ loa",
      ),
    );
    item.append(
      label,
      element(
        "span",
        device.online ? "Online" : "Offline",
        `badge${device.online ? " online" : ""}`,
      ),
    );
    list.append(item);
  }
  if (!state.devices.length)
    list.append(
      element("p", "Chưa có thiết bị. Đăng ký loa bên dưới.", "muted"),
    );
}
function renderAliases() {
  const list = $("aliasList");
  list.replaceChildren();
  for (const alias of state.aliases) {
    const row = element("div", undefined, "alias-row");
    row.append(element("code", `${alias.alias} → ${alias.device_id}`));
    const button = element("button", "Xóa", "text-button danger");
    button.type = "button";
    button.dataset.action = "delete-alias";
    button.dataset.id = alias.alias;
    button.setAttribute("aria-label", `Xóa ánh xạ ${alias.alias}`);
    row.append(button);
    list.append(row);
  }
  if (!state.aliases.length)
    list.append(element("p", "Chưa có ánh xạ mã loa.", "field-help"));
}
function formatTime(timestamp) {
  return new Date(timestamp * 1000).toLocaleString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    day: "2-digit",
    month: "2-digit",
  });
}
function renderHistory(jobs) {
  const signature = JSON.stringify(jobs);
  if (state.signatures.history === signature) return;
  state.signatures.history = signature;
  const body = $("historyBody");
  body.replaceChildren();
  for (const job of jobs) {
    const row = element("tr");
    const content = element("td");
    const text = element("span", job.text || "Không có nội dung", "job-text");
    text.title = job.text;
    content.append(text, element("small", job.id));
    const status = element("td");
    status.append(
      element(
        "span",
        statuses[job.status] || job.status,
        `badge ${job.status}`,
      ),
    );
    row.append(
      content,
      element("td", job.device),
      status,
      element("td", formatTime(job.created)),
    );
    body.append(row);
  }
  if (!jobs.length) emptyRow(body, 4, "Chưa có yêu cầu phát nào.");
}
function renderJob(job) {
  $("jobResult").hidden = false;
  $("jobStatus").textContent = statuses[job.status] || job.status;
  $("jobDevice").textContent = job.device_id || job.device || "";
  $("jobId").textContent = `ID: ${job.id}`;
  const explanations = {
    queued: "Backend đã xếp hàng. Đang chờ loa nhận yêu cầu.",
    playing: "Loa đã nhận yêu cầu và đang tải hoặc phát audio.",
    played:
      "Firmware báo đã gửi xong audio qua I2S. Kiểm tra âm thanh thực tế tại loa.",
    failed:
      "Yêu cầu không hoàn tất hoặc hết hạn chờ. Kiểm tra monitor của ESP32 và log backend.",
  };
  $("jobExplanation").textContent = explanations[job.status] || "";
}
async function loadDirectory() {
  const [users, aliases] = await Promise.all([
    api("/v1/users"),
    api("/v1/device-aliases"),
  ]);
  if (!state.authenticated) return;
  state.users = users.users;
  state.aliases = aliases.device_aliases;
  state.lastDirectory = Date.now();
  renderUsers();
  renderAliases();
  syncAvailability();
}
async function refresh(force = false) {
  if (!state.authenticated || state.refreshing) return;
  state.refreshing = true;
  try {
    const overview = await api("/v1/dashboard/overview");
    if (!state.authenticated) return;
    state.devices = overview.devices;
    $("queuedCount").textContent = overview.totals.queued || 0;
    renderDevices();
    renderHistory(overview.jobs);
    if (force || Date.now() - state.lastDirectory > 9000) await loadDirectory();
    if (state.job && ["queued", "playing"].includes(state.job.status)) {
      const job = await api(`/v1/jobs/${encodeURIComponent(state.job.id)}`);
      if (state.authenticated) {
        state.job = job;
        renderJob(job);
      }
    }
    if (state.authenticated) {
      serverStatus("Backend đã kết nối", true);
      if (state.connectionNotice === $("notice").textContent) {
        $("notice").hidden = true;
      }
      state.connectionNotice = null;
      syncAvailability();
    }
  } finally {
    state.refreshing = false;
  }
}
function providerFields() {
  $("httpSettings").hidden = $("ttsProvider").value !== "http";
  $("httpSettings").disabled = $("ttsProvider").value !== "http";
  $("ttsUrl").required = $("ttsProvider").value === "http";
  $("ttsVoice").required = $("ttsProvider").value === "http";
  $("providerHelp").textContent =
    $("ttsProvider").value === "tone"
      ? "Âm mẫu phát tiếng beep, không đọc nội dung người dùng."
      : "API TTS đọc lời chào; âm mẫu chỉ dùng kiểm tra đường âm thanh.";
}
function applySettings(settings) {
  state.settings = settings;
  const fields = {
    ttsProvider: "provider",
    ttsUrl: "tts_url",
    ttsVoice: "voice",
    ttsModel: "model",
    ttsFormat: "format",
    authHeader: "auth_header",
    authPrefix: "auth_prefix",
  };
  for (const [id, key] of Object.entries(fields))
    $(id).value = settings[key] ?? "";
  $("bodyTemplate").value = JSON.stringify(
    settings.body_template || defaultTemplate,
    null,
    2,
  );
  $("ttsApiKey").value = "";
  $("clearApiKey").checked = false;
  $("keyStatus").textContent = settings.has_api_key
    ? "Đã lưu khóa. Để trống để giữ nguyên."
    : "Chưa lưu khóa API.";
  $("providerBadge").textContent = {
    http: "TTS · API đã cấu hình",
    tone: "Âm mẫu · beep",
    "": "TTS chưa cấu hình",
  }[settings.provider];
  $("settingsState").textContent = "Đã tải cấu hình lưu trên backend";
  providerFields();
  syncAvailability();
}
function resetUserForm() {
  state.editing = null;
  $("userForm").reset();
  $("userId").readOnly = false;
  $("userFormTitle").textContent = "Đăng ký người dùng";
  $("saveUserButton").textContent = "Đăng ký người dùng";
  $("cancelUserEdit").hidden = true;
  updateTextCount();
  if (state.devices.length) $("userDevice").value = state.devices[0].id;
}
function editUser(id) {
  const user = state.users.find((item) => item.user_id === id);
  if (!user) return;
  state.editing = id;
  $("userId").value = id;
  $("userId").readOnly = true;
  $("userName").value = user.name;
  $("userText").value = user.text_to_speech;
  $("userDevice").value = user.device_id;
  $("userFormTitle").textContent = `Chỉnh sửa người dùng ${id}`;
  $("saveUserButton").textContent = "Lưu thay đổi";
  $("cancelUserEdit").hidden = false;
  updateTextCount();
  showView("users");
  $("userName").focus();
}
function updateTextCount() {
  $("userTextCount").textContent =
    `${Array.from($("userText").value).length} / 1.000`;
}
function clearPreview() {
  state.previewVersion++;
  const audio = $("previewAudio");
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  if (state.audioUrl) URL.revokeObjectURL(state.audioUrl);
  state.audioUrl = null;
  $("previewPanel").hidden = true;
}
function hideConnection() {
  state.connectionCode = "";
  $("connectionCode").textContent = "";
  $("connectionPanel").hidden = true;
}
function lockDashboard() {
  state.authenticated = false;
  state.key = "";
  state.users = [];
  state.devices = [];
  state.aliases = [];
  state.settings = null;
  state.job = null;
  state.autoSelected = false;
  state.signatures = {};
  clearPreview();
  hideConnection();
  resetUserForm();
  $("settingsForm").reset();
  $("bodyTemplate").value = "";
  $("newDeviceToken").value = "";
  $("jobResult").hidden = true;
  $("loginPanel").hidden = false;
  $("logoutButton").hidden = true;
  $("onlineCount").textContent = "—";
  $("queuedCount").textContent = "—";
  $("providerBadge").textContent = "Chưa tải TTS";
  $("settingsState").textContent = "Chưa tải cấu hình";
  $("keyStatus").textContent = "Chưa tải trạng thái khóa.";
  renderUsers();
  renderDevices();
  renderAliases();
  emptyRow($("historyBody"), 4, "Kết nối để xem lịch sử.");
  providerFields();
  serverStatus("Chưa kết nối", false);
  syncAvailability();
}
async function connect() {
  await api("/v1/dashboard/session", { method: "POST" });
  state.key = "";
  state.authenticated = true;
  $("operatorKey").value = "";
  $("loginPanel").hidden = true;
  $("logoutButton").hidden = false;
  const settings = await api("/v1/dashboard/tts");
  if (!state.authenticated) return;
  applySettings(settings);
  await refresh(true);
}

document
  .querySelectorAll("[data-view]")
  .forEach((button) =>
    button.addEventListener("click", () => showView(button.dataset.view)),
  );
$("loginForm").addEventListener("submit", (event) => {
  event.preventDefault();
  busy(
    $("loginButton"),
    async () => {
      state.key = $("operatorKey").value.trim();
      try {
        await connect();
        $("notice").hidden = true;
      } finally {
        state.key = "";
      }
    },
    "Đang kết nối…",
  );
});
$("logoutButton").addEventListener("click", () =>
  busy($("logoutButton"), async () => {
    await api("/v1/dashboard/session", { method: "DELETE" });
    lockDashboard();
  }),
);
$("playUser").addEventListener("change", () => {
  clearPreview();
  updateSelectedUser();
});
$("editSelectedUser").addEventListener("click", () => {
  const user = selectedUser();
  if (user) editUser(user.user_id);
});
$("playForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const user = selectedUser();
  if (!user || !state.authenticated) return;
  busy(
    $("playButton"),
    async () => {
      const result = await api("/v1/detect", {
        method: "POST",
        body: { user_id: user.user_id },
      });
      if (!state.authenticated) return;
      state.job = result;
      renderJob(result);
      notify(`Đã xếp hàng lời chào của người dùng ${result.user_id}.`);
      await refresh();
    },
    "Đang tạo audio…",
  );
});
$("previewButton").addEventListener("click", () => {
  const user = selectedUser();
  if (!user) return;
  clearPreview();
  const version = state.previewVersion;
  busy(
    $("previewButton"),
    async () => {
      const blob = await api("/v1/dashboard/preview", {
        method: "POST",
        body: { text: user.text_to_speech },
        binary: true,
      });
      if (version !== state.previewVersion || !state.authenticated) return;
      state.audioUrl = URL.createObjectURL(blob);
      $("previewAudio").src = state.audioUrl;
      $("previewPanel").hidden = false;
      try {
        await $("previewAudio").play();
      } catch (_) {
        notify("Audio đã sẵn sàng. Bấm nút phát trên trình nghe thử.");
      }
    },
    "Đang tải audio…",
  );
});
$("previewAudio").addEventListener("ended", clearPreview);
$("closePreview").addEventListener("click", clearPreview);
$("copyApiButton").addEventListener("click", () =>
  busy($("copyApiButton"), async () => {
    const body = JSON.stringify({ user_id: selectedUser()?.user_id || 1 });
    await navigator.clipboard.writeText(
      `curl -X POST '${location.origin}/v1/detect' \\\n  -H 'Authorization: Bearer YOUR_ADMIN_KEY' \\\n  -H 'Content-Type: application/json' \\\n  -d '${body}'`,
    );
    notify("Đã sao chép lệnh cURL. Điền khóa quản trị của bạn trước khi gọi.");
  }),
);
$("refreshButton").addEventListener("click", () =>
  busy($("refreshButton"), () => refresh(true)),
);
$("refreshUsersButton").addEventListener("click", () =>
  busy($("refreshUsersButton"), loadDirectory),
);
$("userText").addEventListener("input", updateTextCount);
$("cancelUserEdit").addEventListener("click", resetUserForm);
$("userForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const editing = state.editing;
  busy($("saveUserButton"), async () => {
    const userId = Number($("userId").value);
    const details = {
      name: $("userName").value.trim(),
      text_to_speech: $("userText").value.trim(),
      device_id: $("userDevice").value,
    };
    if (!details.text_to_speech)
      throw new Error("Nhập lời chào cho người dùng.");
    await api(editing === null ? "/v1/users" : `/v1/users/${editing}`, {
      method: editing === null ? "POST" : "PUT",
      body: editing === null ? { user_id: userId, ...details } : details,
    });
    resetUserForm();
    await loadDirectory();
    notify(`Đã lưu người dùng ${userId}. Có thể chọn ID này để phát.`);
  });
});
$("usersBody").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || !state.authenticated) return;
  const id = Number(button.dataset.id);
  if (button.dataset.action === "edit-user") editUser(id);
  else if (button.dataset.action === "select-user") {
    $("playUser").value = String(id);
    updateSelectedUser();
    showView("play");
    $("playUser").focus();
  } else if (
    button.dataset.action === "delete-user" &&
    confirm(`Xóa người dùng ${id} khỏi database?`)
  )
    busy(button, async () => {
      await api(`/v1/users/${id}`, { method: "DELETE" });
      if (state.editing === id) resetUserForm();
      await loadDirectory();
      notify(`Đã xóa người dùng ${id}.`);
    });
});
$("deviceForm").addEventListener("submit", (event) => {
  event.preventDefault();
  busy($("saveDeviceButton"), async () => {
    const id = $("newDeviceId").value.trim();
    await api("/v1/dashboard/devices", {
      method: "PUT",
      body: { device_id: id, token: $("newDeviceToken").value },
    });
    $("deviceForm").reset();
    hideConnection();
    await refresh(true);
    notify(`Đã lưu loa ${id}.`);
  });
});
$("aliasForm").addEventListener("submit", (event) => {
  event.preventDefault();
  busy($("saveAliasButton"), async () => {
    const id = $("aliasId").value.trim();
    await api(`/v1/device-aliases/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: { device_id: $("aliasDevice").value },
    });
    $("aliasId").value = "";
    await loadDirectory();
    notify(`Đã lưu ánh xạ ${id}.`);
  });
});
$("aliasList").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || !state.authenticated) return;
  const id = button.dataset.id;
  if (confirm(`Xóa ánh xạ ${id}? Loa thật và người dùng vẫn được giữ.`))
    busy(button, async () => {
      await api(`/v1/device-aliases/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      await loadDirectory();
    });
});
$("connectionDevice").addEventListener("change", () => {
  hideConnection();
  syncAvailability();
});
$("hideConnectionButton").addEventListener("click", hideConnection);
$("loadConnectionButton").addEventListener("click", () =>
  busy($("loadConnectionButton"), async () => {
    const deviceId = $("connectionDevice").value;
    const data = await api(
      `/v1/dashboard/devices/${encodeURIComponent(deviceId)}/connection`,
    );
    if (
      !state.authenticated ||
      state.view !== "devices" ||
      $("connectionDevice").value !== deviceId
    )
      return;
    state.connectionCode = `inline constexpr const char *backend_url = ${JSON.stringify(data.backend_url)};\ninline constexpr const char *device_id = ${JSON.stringify(data.device_id)};\ninline constexpr const char *device_token = ${JSON.stringify(data.device_token)};\ninline constexpr bool allow_http_for_development = ${data.allow_http};`;
    $("connectionCode").textContent = state.connectionCode;
    $("connectionPanel").hidden = false;
  }),
);
$("copyConnectionButton").addEventListener("click", () =>
  busy($("copyConnectionButton"), async () => {
    await navigator.clipboard.writeText(state.connectionCode);
    notify("Đã sao chép cấu hình firmware.");
  }),
);
$("ttsProvider").addEventListener("change", providerFields);
$("settingsForm").addEventListener("input", () => {
  $("settingsState").textContent = "Có thay đổi chưa lưu";
});
$("reloadSettingsButton").addEventListener("click", () =>
  busy($("reloadSettingsButton"), async () => {
    applySettings(await api("/v1/dashboard/tts"));
    notify("Đã tải lại cấu hình đã lưu.");
  }),
);
$("settingsForm").addEventListener("submit", (event) => {
  event.preventDefault();
  busy(
    $("saveSettingsButton"),
    async () => {
      let template;
      try {
        template = JSON.parse($("bodyTemplate").value);
      } catch (_) {
        throw new Error("JSON gửi tới TTS chưa hợp lệ.");
      }
      if (!template || Array.isArray(template) || typeof template !== "object")
        throw new Error("JSON gửi tới TTS phải là object.");
      const result = await api("/v1/dashboard/tts", {
        method: "PUT",
        body: {
          provider: $("ttsProvider").value,
          tts_url: $("ttsUrl").value.trim(),
          api_key: $("ttsApiKey").value,
          clear_api_key: $("clearApiKey").checked,
          voice: $("ttsVoice").value.trim() || "default",
          model: $("ttsModel").value.trim(),
          format: $("ttsFormat").value,
          auth_header: $("authHeader").value.trim() || "Authorization",
          auth_prefix: $("authPrefix").value,
          body_template: template,
        },
      });
      if (state.authenticated) {
        applySettings(result);
        notify("Đã lưu cấu hình TTS.");
      }
    },
    "Đang lưu…",
  );
});

$("detectEndpoint").textContent = `${location.origin}/v1/detect`;
$("bodyTemplate").value = JSON.stringify(defaultTemplate, null, 2);
providerFields();
syncAvailability();
(async () => {
  const fragment = new URLSearchParams(location.hash.slice(1));
  state.key =
    fragment.get("key") || sessionStorage.getItem("dsoft_operator_key") || "";
  sessionStorage.removeItem("dsoft_operator_key");
  if (fragment.has("key"))
    history.replaceState(null, "", location.pathname + location.search);
  try {
    await connect();
  } catch (error) {
    const hadKey = !!state.key;
    lockDashboard();
    if (hadKey) notify(error.message, true);
  } finally {
    state.key = "";
  }
})();
setInterval(() => {
  if (!document.hidden)
    refresh().catch((error) => {
      if (state.authenticated) {
        serverStatus("Mất kết nối backend", false);
        state.connectionNotice = error.message;
        notify(error.message, true);
      }
    });
}, 3000);
