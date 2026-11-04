/* Logic dashboard: cùng backend với firmware, không có trạng thái thiết bị giả. */
"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  authenticated: false,
  key: "",
  settings: null,
  devices: [],
  connection: null,
  view: "play",
  refreshing: false,
  pendingRequest: null,
  audioUrl: null,
  noticeTimer: null,
};
const viewNames = {
  play: "Phát thử",
  settings: "Cấu hình TTS",
  devices: "Kết nối ESP32",
};
const statusNames = {
  queued: "Chờ loa",
  playing: "Đang xử lý",
  played: "Đã phát",
  failed: "Thất bại",
};
const defaultTemplate = {
  text: "{{text}}",
  voice: "{{voice}}",
  format: "pcm_s16le",
  sample_rate: 24000,
};

function notify(message, isError = false) {
  clearTimeout(state.noticeTimer);
  $("notice").textContent = message;
  $("notice").classList.toggle("error", isError);
  $("notice").hidden = false;
  if (!isError)
    state.noticeTimer = setTimeout(() => {
      $("notice").hidden = true;
    }, 8000);
}

function explainError(detail) {
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join(" · ");
  const messages = {
    "Invalid operator token": "Khóa quản trị chưa đúng. Vui lòng kiểm tra lại.",
    "Bearer token required": "Vui lòng kết nối bằng khóa quản trị.",
    "Device queue is full":
      "Hàng đợi của loa đã đầy. Đợi loa xử lý rồi thử lại.",
    "TTS connection failed":
      "Không kết nối được API TTS. Kiểm tra URL và kết nối mạng.",
    "TTS provider rejected request":
      "API TTS từ chối yêu cầu. Kiểm tra khóa, header và JSON request.",
    "This adapter expects binary audio, not a JSON audio URL":
      "API trả JSON. Adapter hiện cần binary audio; xem hướng dẫn trong cấu hình TTS.",
    "Install ffmpeg to convert MP3/noncanonical WAV":
      "Máy chủ cần cài ffmpeg để chuyển định dạng âm thanh này.",
    "Idempotency key reused with a different payload":
      "Yêu cầu phát đã thay đổi. Làm mới trang rồi thử lại.",
  };
  return (
    messages[detail] || String(detail || "Có lỗi xảy ra. Vui lòng thử lại.")
  );
}

async function api(
  path,
  { method = "GET", body, binary = false, headers = {} } = {},
) {
  let response;
  try {
    response = await fetch(path, {
      method,
      cache: "no-store",
      headers: {
        ...(state.key ? { Authorization: `Bearer ${state.key}` } : {}),
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (_) {
    throw new Error(
      "Chưa kết nối được backend. Kiểm tra máy chủ còn đang chạy.",
    );
  }
  if (!response.ok) {
    let detail;
    try {
      detail = (await response.json()).detail;
    } catch (_) {
      detail = `Backend trả lỗi HTTP ${response.status}`;
    }
    if (response.status === 401 && state.authenticated) lockDashboard();
    throw new Error(explainError(detail));
  }
  if (binary) return response.blob();
  return response.status === 204 ? null : response.json();
}

async function busy(button, action) {
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    await action();
  } catch (error) {
    notify(error.message, true);
  } finally {
    button.removeAttribute("aria-busy");
    button.disabled = false;
    syncAvailability();
  }
}

function showView(view) {
  state.view = view;
  for (const element of document.querySelectorAll(".view"))
    element.hidden = element.id !== `view-${view}`;
  for (const button of document.querySelectorAll(".nav-button")) {
    button.classList.toggle("active", button.dataset.view === view);
    if (button.dataset.view === view)
      button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  $("breadcrumbView").textContent = viewNames[view];
  if (view === "devices" && state.authenticated)
    loadConnection().catch((error) => notify(error.message, true));
}

function syncAvailability() {
  const configured = Boolean(state.settings?.provider);
  const device = state.devices.find(
    (item) => item.id === $("speakerSelect").value,
  );
  for (const [id, enabled] of [
    ["previewButton", state.authenticated && configured],
    ["sendButton", state.authenticated && configured && device?.configured],
    ["saveSettingsButton", state.authenticated],
    ["saveDeviceButton", state.authenticated],
    ["refreshButton", state.authenticated],
    [
      "copyConnectionButton",
      state.authenticated && Boolean(state.connection?.device_token),
    ],
  ]) {
    if (!$(id).hasAttribute("aria-busy")) $(id).disabled = !enabled;
  }
  if (!state.authenticated)
    $("composerHint").textContent = "Kết nối bảng điều khiển để bắt đầu.";
  else if (!configured)
    $("composerHint").textContent =
      "Mở Cấu hình TTS và lưu một nguồn âm thanh trước khi phát.";
  else if (!device?.configured)
    $("composerHint").textContent =
      "Mở Kết nối ESP32 để đăng ký loa và tạo device token.";
  else if (!device.online)
    $("composerHint").textContent =
      "Loa chưa kết nối. Yêu cầu sẽ chờ đến khi ESP32 gọi về backend.";
  else
    $("composerHint").textContent =
      "Loa đã kết nối. Yêu cầu sẽ được phát theo thứ tự và mức ưu tiên.";
}

function renderProvider() {
  const provider = state.settings?.provider || "";
  $("providerBadge").textContent =
    provider === "tone"
      ? "Âm mẫu · beep"
      : provider === "http"
        ? "API TTS đã cấu hình"
        : "TTS chưa cấu hình";
  $("providerBadge").className =
    `pill ${provider === "tone" ? "tone" : provider ? "ready" : "neutral"}`;
}

function fillSettings(settings) {
  state.settings = settings;
  $("ttsProvider").value = settings.provider;
  $("ttsUrl").value = settings.tts_url || "";
  $("ttsApiKey").value = "";
  $("ttsApiKey").placeholder = settings.has_api_key
    ? "Đã lưu khóa · để trống để giữ nguyên"
    : "Nhập khóa của nhà cung cấp";
  $("keyStatus").textContent = settings.has_api_key
    ? "Khóa đang được lưu ở backend."
    : "Chưa lưu khóa API.";
  $("clearApiKey").checked = false;
  $("ttsVoice").value = settings.voice || "default";
  $("ttsModel").value = settings.model || "";
  $("ttsFormat").value = settings.format || "pcm";
  $("authHeader").value = settings.auth_header || "Authorization";
  $("authPrefix").value = settings.auth_prefix ?? "Bearer";
  $("bodyTemplate").value = JSON.stringify(
    settings.body_template || defaultTemplate,
    null,
    2,
  );
  $("settingsState").textContent = "Cấu hình đã lưu";
  updateProviderFields();
  renderProvider();
  syncAvailability();
}

function updateProviderFields() {
  const provider = $("ttsProvider").value;
  $("httpSettings").hidden = provider !== "http";
  $("httpSettings").disabled = provider !== "http";
  $("ttsUrl").required = provider === "http";
  $("toneNote").hidden = provider !== "tone";
}

function setDeviceOptions(select, devices, withStatus = false) {
  const previous = select.value;
  select.replaceChildren();
  for (const device of devices) {
    const suffix = withStatus
      ? device.online
        ? " · Đang kết nối"
        : " · Chưa kết nối"
      : "";
    select.add(new Option(device.id + suffix, device.id));
  }
  if (!devices.length) select.add(new Option("Chưa có thiết bị", ""));
  else if (devices.some((device) => device.id === previous))
    select.value = previous;
}

// Dữ liệu từ server luôn được đặt bằng textContent, không đưa vào HTML trực tiếp.
function element(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}

function formatTime(timestamp) {
  return new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "Asia/Ho_Chi_Minh",
  }).format(new Date(timestamp * 1000));
}

function renderOverview(data) {
  state.devices = data.devices;
  $("onlineCount").textContent = data.devices.filter(
    (device) => device.online,
  ).length;
  $("deviceCount").textContent = `/ ${data.devices.length} thiết bị`;
  $("queuedCount").textContent = data.totals.queued || 0;
  $("playedCount").textContent = data.totals.played || 0;
  setDeviceOptions($("speakerSelect"), data.devices, true);
  setDeviceOptions($("connectionDevice"), data.devices);

  $("deviceList").replaceChildren();
  if (!data.devices.length)
    $("deviceList").append(
      element("p", "muted", "Chưa có loa. Thêm thiết bị ở bên dưới."),
    );
  for (const device of data.devices) {
    const item = element("div", "device-item");
    const info = element("div");
    info.append(element("strong", "", device.id));
    info.append(
      element(
        "p",
        "",
        !device.configured
          ? "Chưa cấu hình token"
          : device.last_seen
            ? `Lần gần nhất ${formatTime(device.last_seen)}`
            : "Chưa nhận kết nối từ ESP32",
      ),
    );
    const status = element(
      "span",
      `device-state ${device.online ? "online" : ""}`,
    );
    status.append(
      element("span", "status-dot"),
      document.createTextNode(device.online ? "Đang kết nối" : "Chưa kết nối"),
    );
    item.append(info, status);
    $("deviceList").append(item);
  }

  $("emptyHistory").hidden = data.jobs.length > 0;
  $("historyWrapper").hidden = data.jobs.length === 0;
  $("historyBody").replaceChildren();
  for (const job of data.jobs) {
    const row = element("tr");
    const content = element("td");
    const text = element(
      "span",
      "job-text",
      job.text || "Yêu cầu từ phiên bản trước",
    );
    text.title = job.text || "";
    content.append(
      text,
      element(
        "span",
        "job-kind",
        job.audio_kind === "test_tone"
          ? "Âm mẫu · beep"
          : `Ưu tiên ${job.priority}`,
      ),
    );
    const status = element("td");
    const knownStatus = Object.hasOwn(statusNames, job.status)
      ? job.status
      : "failed";
    status.append(
      element("span", `job-status ${knownStatus}`, statusNames[knownStatus]),
    );
    row.append(
      content,
      element("td", "", job.device),
      status,
      element("td", "", `${job.volume}%`),
      element("td", "time-cell", formatTime(job.created)),
    );
    $("historyBody").append(row);
  }
  syncAvailability();
}

async function refreshOverview() {
  if (!state.authenticated || state.refreshing) return;
  state.refreshing = true;
  try {
    renderOverview(await api("/v1/dashboard/overview"));
    $("serverStatus").classList.add("connected");
    $("serverStatus").replaceChildren(
      element("span", "status-dot"),
      document.createTextNode("Backend đã kết nối"),
    );
  } finally {
    state.refreshing = false;
  }
}

async function unlockDashboard(key) {
  state.key = key;
  try {
    if (key) await api("/v1/dashboard/session", { method: "POST" });
    const [settings, overview] = await Promise.all([
      api("/v1/dashboard/tts"),
      api("/v1/dashboard/overview"),
    ]);
    state.authenticated = true;
    sessionStorage.setItem("dsoft-operator-key", key);
    $("operatorKey").value = "";
    $("loginPanel").hidden = true;
    $("logoutButton").hidden = false;
    fillSettings(settings);
    renderOverview(overview);
    $("serverStatus").classList.add("connected");
    $("serverStatus").replaceChildren(
      element("span", "status-dot"),
      document.createTextNode("Backend đã kết nối"),
    );
    if (state.view === "devices") await loadConnection();
  } catch (error) {
    state.authenticated = false;
    sessionStorage.removeItem("dsoft-operator-key");
    syncAvailability();
    throw error;
  }
}

function lockDashboard() {
  sessionStorage.removeItem("dsoft-operator-key");
  state.authenticated = false;
  state.key = "";
  state.settings = null;
  state.connection = null;
  state.devices = [];
  $("previewAudio").pause();
  $("previewAudio").removeAttribute("src");
  $("previewAudio").hidden = true;
  if (state.audioUrl) URL.revokeObjectURL(state.audioUrl);
  state.audioUrl = null;
  $("loginPanel").hidden = false;
  $("logoutButton").hidden = true;
  $("connectionToken").value = "";
  $("connectionUrl").value = "";
  $("ttsApiKey").value = "";
  $("serverStatus").classList.remove("connected");
  $("serverStatus").replaceChildren(
    element("span", "status-dot"),
    document.createTextNode("Chưa kết nối"),
  );
  renderOverview({ devices: [], jobs: [], totals: {} });
  renderProvider();
}

async function loadConnection() {
  const id = $("connectionDevice").value;
  if (!id) return;
  state.connection = await api(
    `/v1/dashboard/devices/${encodeURIComponent(id)}/connection`,
  );
  $("connectionUrl").value = state.connection.backend_url;
  $("connectionToken").value = state.connection.device_token;
  $("connectionToken").type = "password";
  $("revealTokenButton").textContent = "Hiện";
  $("httpInstruction").textContent = state.connection.allow_http
    ? "Trong speaker_config.h, đặt allow_http_for_development = true cho demo HTTP trong LAN."
    : "Backend dùng HTTPS: giữ kiểm tra chứng chỉ ở trạng thái bật.";
  syncAvailability();
}

function requestId() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

// Gắn các thao tác sau khi HTML đã tải (script dùng defer).
document
  .querySelectorAll("[data-view]")
  .forEach((button) =>
    button.addEventListener("click", () => showView(button.dataset.view)),
  );
document.querySelectorAll("[data-sample]").forEach((button) =>
  button.addEventListener("click", () => {
    $("speechText").value = button.dataset.sample;
    $("speechText").dispatchEvent(new Event("input"));
    $("speechText").focus();
  }),
);
$("speechText").addEventListener("input", () => {
  $("characterCount").textContent = `${$("speechText").value.length} / 1.000`;
});
$("volumeRange").addEventListener("input", () => {
  $("volumeValue").value = `${$("volumeRange").value}%`;
});
$("speakerSelect").addEventListener("change", syncAvailability);
$("ttsProvider").addEventListener("change", updateProviderFields);
$("settingsForm").addEventListener("input", () => {
  $("settingsState").textContent = "Có thay đổi chưa lưu";
});
$("connectionDevice").addEventListener("change", () =>
  loadConnection().catch((error) => notify(error.message, true)),
);
$("logoutButton").addEventListener("click", async () => {
  try {
    await api("/v1/dashboard/session", { method: "DELETE" });
  } finally {
    lockDashboard();
  }
});
$("refreshButton").addEventListener("click", () =>
  refreshOverview().catch((error) => notify(error.message, true)),
);

$("loginForm").addEventListener("submit", (event) => {
  event.preventDefault();
  busy(event.submitter, () => unlockDashboard($("operatorKey").value.trim()));
});

$("settingsForm").addEventListener("submit", (event) => {
  event.preventDefault();
  busy($("saveSettingsButton"), async () => {
    let template = state.settings?.body_template || defaultTemplate;
    if ($("ttsProvider").value === "http") {
      try {
        template = JSON.parse(
          $("bodyTemplate").value || JSON.stringify(defaultTemplate),
        );
      } catch (_) {
        throw new Error(
          "JSON request chưa hợp lệ. Kiểm tra dấu phẩy và dấu nháy.",
        );
      }
    }
    const settings = await api("/v1/dashboard/tts", {
      method: "PUT",
      body: {
        provider: $("ttsProvider").value,
        tts_url: $("ttsUrl").value.trim(),
        api_key: $("ttsApiKey").value || null,
        clear_api_key: $("clearApiKey").checked,
        voice: $("ttsVoice").value.trim() || "default",
        model: $("ttsModel").value.trim(),
        format: $("ttsFormat").value,
        auth_header: $("authHeader").value.trim() || "Authorization",
        auth_prefix: $("authPrefix").value,
        body_template: template,
      },
    });
    fillSettings(settings);
    notify(
      settings.provider === "tone"
        ? "Đã lưu âm mẫu. Bạn có thể thử beep trên web hoặc gửi tới ESP32."
        : "Đã lưu cấu hình TTS. Quay lại Phát thử để kiểm tra giọng nói.",
    );
  });
});

$("previewButton").addEventListener("click", () => {
  if (!$("speechText").reportValidity()) return;
  busy($("previewButton"), async () => {
    const audio = await api("/v1/dashboard/preview", {
      method: "POST",
      body: { text: $("speechText").value },
      binary: true,
    });
    if (state.audioUrl) URL.revokeObjectURL(state.audioUrl);
    state.audioUrl = URL.createObjectURL(audio);
    $("previewAudio").src = state.audioUrl;
    $("previewAudio").hidden = false;
    try {
      await $("previewAudio").play();
    } catch (_) {
      notify("Âm thanh đã sẵn sàng. Nhấn nút Play trên thanh nghe thử.");
    }
  });
});

$("speakForm").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!$("speechText").value.trim())
    return notify("Vui lòng nhập nội dung cần đọc.", true);
  busy($("sendButton"), async () => {
    const payload = {
      device_id: $("speakerSelect").value,
      text: $("speechText").value,
      volume: Number($("volumeRange").value),
      priority: Number($("prioritySelect").value),
    };
    const fingerprint = JSON.stringify(payload);
    // Nếu mất phản hồi HTTP, bấm thử lại cùng nội dung dùng lại key để tránh phát trùng.
    if (state.pendingRequest?.fingerprint !== fingerprint)
      state.pendingRequest = { fingerprint, key: requestId() };
    await api("/v1/speak", {
      method: "POST",
      body: payload,
      headers: { "Idempotency-Key": state.pendingRequest.key },
    });
    state.pendingRequest = null;
    await refreshOverview();
    notify("Đã xếp hàng cho ESP32. Theo dõi kết quả tại Lịch sử phát.");
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
    $("newDeviceToken").value = "";
    await refreshOverview();
    $("connectionDevice").value = id;
    $("speakerSelect").value = id;
    await loadConnection();
    notify("Đã lưu thiết bị. Dùng thông tin bên phải để cấu hình ESP32.");
  });
});

$("revealTokenButton").addEventListener("click", () => {
  const reveal = $("connectionToken").type === "password";
  $("connectionToken").type = reveal ? "text" : "password";
  $("revealTokenButton").textContent = reveal ? "Ẩn" : "Hiện";
});
$("copyConnectionButton").addEventListener("click", async () => {
  if (!state.connection) return;
  const config = state.connection;
  const snippet = [
    `inline constexpr const char *backend_url = ${JSON.stringify(config.backend_url)};`,
    `inline constexpr const char *device_id = ${JSON.stringify(config.device_id)};`,
    `inline constexpr const char *device_token = ${JSON.stringify(config.device_token)};`,
    `inline constexpr bool allow_http_for_development = ${config.allow_http ? "true" : "false"};`,
  ].join("\n");
  try {
    if (navigator.clipboard?.writeText)
      await navigator.clipboard.writeText(snippet);
    else {
      const input = document.createElement("textarea");
      input.value = snippet;
      document.body.append(input);
      input.select();
      const copied = document.execCommand("copy");
      input.remove();
      if (!copied) throw new Error("Clipboard unavailable");
    }
    notify(
      "Đã sao chép code C++. Thay các dòng tương ứng trong main/speaker_config.h rồi build lại.",
    );
  } catch (_) {
    notify(
      "Trình duyệt chưa cho phép sao chép. Nhập URL, ID và token vào main/speaker_config.h.",
      true,
    );
  }
});

// URL demo mang khóa qua fragment (#key), không gửi khóa trong URL tới server.
const fragment = new URLSearchParams(location.hash.slice(1));
const initialKey =
  fragment.get("key") || sessionStorage.getItem("dsoft-operator-key");
if (fragment.has("key"))
  history.replaceState(null, "", location.pathname + location.search);
$("bodyTemplate").value = JSON.stringify(defaultTemplate, null, 2);
updateProviderFields();
syncAvailability();
unlockDashboard(initialKey || "").catch((error) => {
  if (initialKey) notify(error.message, true);
});
setInterval(() => {
  if (!document.hidden)
    refreshOverview().catch(() => {
      $("serverStatus").classList.remove("connected");
      $("serverStatus").replaceChildren(
        element("span", "status-dot"),
        document.createTextNode("Đang chờ backend"),
      );
    });
}, 3000);
