/** GIAO TIẾP BACKEND
 *  Xử lý HTTP và JSON. Không tạo giọng nói ở đây.
 *  Đổi đường dẫn API/hợp đồng job: sửa file này và backend tương ứng.
 */
#include "speaker_api.h"
#include "speaker_audio.h"
#include "speaker_config.h"

#include <cctype>
#include <cstdio>
#include <cstring>
#include "cJSON.h"
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "speaker_api";
static char authorization_header[256];
static bool backend_connected = false;

// ID đi vào URL/JSON nên chỉ cho phép chữ, số, dấu gạch ngang và gạch dưới.
static bool is_valid_id(const char *value)
{
    if (!value || !*value || strlen(value) > 64) {
        return false;
    }
    for (const char *character = value; *character; ++character) {
        if (!isalnum(static_cast<unsigned char>(*character)) && *character != '-' && *character != '_') {
            return false;
        }
    }
    return true;
}

bool speaker_api_init()
{
    const bool uses_https = strncmp(speaker_config::backend_url, "https://", 8) == 0;
    const bool uses_allowed_http = speaker_config::allow_http_for_development &&
                                  strncmp(speaker_config::backend_url, "http://", 7) == 0;
    const std::size_t token_length = strlen(speaker_config::device_token);

    if ((!uses_https && !uses_allowed_http) || !is_valid_id(speaker_config::device_id) ||
        token_length < 16 || token_length > 200) {
        ESP_LOGE(TAG, "Sua backend_url, device_id va device_token trong main/speaker_config.h");
        return false;
    }

    snprintf(authorization_header, sizeof(authorization_header), "Bearer %s", speaker_config::device_token);
    return true;
}

// body == nullptr: GET. Có body JSON: POST. Dùng xong phải close_request().
static esp_http_client_handle_t open_request(const char *path, const char *body = nullptr)
{
    char url[512];
    if (snprintf(url, sizeof(url), "%s%s", speaker_config::backend_url, path) >= sizeof(url)) {
        return nullptr;
    }

    esp_http_client_config_t config = {};
    config.url = url;
    config.timeout_ms = speaker_config::http_timeout_ms;
    config.crt_bundle_attach = esp_crt_bundle_attach;
    config.disable_auto_redirect = true;
    config.buffer_size = speaker_config::download_chunk_bytes;
    config.buffer_size_tx = 1024;

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        return nullptr;
    }
    esp_http_client_set_header(client, "Authorization", authorization_header);
    if (body) {
        esp_http_client_set_method(client, HTTP_METHOD_POST);
        esp_http_client_set_header(client, "Content-Type", "application/json");
    }
    if (esp_http_client_open(client, body ? strlen(body) : 0) != ESP_OK) {
        goto failed;
    }
    if (body) {
        const std::size_t length = strlen(body);
        std::size_t sent = 0;
        while (sent < length) {
            const int written = esp_http_client_write(client, body + sent, length - sent);
            if (written <= 0) {
                goto failed;
            }
            sent += written;
        }
    }
    if (esp_http_client_fetch_headers(client) < 0) {
        goto failed;
    }
    return client;

failed:
    esp_http_client_cleanup(client);
    return nullptr;
}

static void close_request(esp_http_client_handle_t client)
{
    esp_http_client_close(client);
    esp_http_client_cleanup(client);
}

// Đổi JSON thành struct dễ dùng. app_main không cần biết cJSON.
static bool parse_job(const cJSON *json, SpeakerJob &job)
{
    const cJSON *id = cJSON_GetObjectItemCaseSensitive(json, "id");
    const cJSON *lease = cJSON_GetObjectItemCaseSensitive(json, "lease");
    const cJSON *volume = cJSON_GetObjectItemCaseSensitive(json, "volume");
    const cJSON *bytes = cJSON_GetObjectItemCaseSensitive(json, "audio_bytes");
    const cJSON *rate = cJSON_GetObjectItemCaseSensitive(json, "sample_rate");

    if (!cJSON_IsString(id) || !is_valid_id(id->valuestring) ||
        !cJSON_IsString(lease) || !is_valid_id(lease->valuestring) ||
        !cJSON_IsNumber(volume) || volume->valuedouble < 0 || volume->valuedouble > 100 ||
        volume->valuedouble != volume->valueint ||
        !cJSON_IsNumber(bytes) || bytes->valuedouble <= 0 ||
        bytes->valuedouble > speaker_config::max_audio_bytes ||
        bytes->valuedouble != bytes->valueint ||
        bytes->valueint % speaker_config::pcm_bytes_per_sample != 0 ||
        !cJSON_IsNumber(rate) || rate->valuedouble != speaker_config::sample_rate_hz) {
        return false;
    }

    strlcpy(job.id, id->valuestring, sizeof(job.id));
    strlcpy(job.lease, lease->valuestring, sizeof(job.lease));
    job.volume_percent = volume->valueint;
    job.audio_bytes = bytes->valueint;
    return true;
}

bool speaker_api_next_job(SpeakerJob &job)
{
    job = {};  // Xóa dữ liệu câu cũ trước mỗi lần hỏi backend.
    char path[160];
    snprintf(path, sizeof(path), "/v1/devices/%s/next", speaker_config::device_id);
    esp_http_client_handle_t client = open_request(path);
    if (!client) {
        backend_connected = false;
        ESP_LOGW(TAG, "Chua ket noi duoc backend");
        return false;
    }

    const int status = esp_http_client_get_status_code(client);
    if (status == 200 || status == 204) {
        if (!backend_connected) {
            ESP_LOGI(TAG, "Da ket noi backend (HTTP %d)", status);
        }
        backend_connected = true;
    } else {
        backend_connected = false;
    }
    bool has_job = false;
    if (status == 200) {
        char response[1536];
        std::size_t used = 0;
        while (used < sizeof(response) - 1) {
            const int received = esp_http_client_read(client, response + used, sizeof(response) - 1 - used);
            if (received <= 0) {
                break;
            }
            used += received;
        }
        response[used] = '\0';

        if (esp_http_client_is_complete_data_received(client)) {
            cJSON *json = cJSON_Parse(response);
            has_job = parse_job(json, job);
            cJSON_Delete(json);
        }
        if (!has_job) {
            ESP_LOGW(TAG, "Bo qua job sai dinh dang");
        }
    } else if (status != 204) {
        // 204 là bình thường: backend chưa có câu nào để phát.
        ESP_LOGW(TAG, "Lay job that bai, HTTP %d", status);
    }

    close_request(client);
    return has_job;
}

bool speaker_api_play_job(const SpeakerJob &job)
{
    char path[240];
    snprintf(path, sizeof(path), "/v1/devices/%s/audio/%s?lease=%s",
             speaker_config::device_id, job.id, job.lease);
    esp_http_client_handle_t client = open_request(path);
    if (!client) {
        return false;
    }

    const int64_t content_length = esp_http_client_get_content_length(client);
    if (esp_http_client_get_status_code(client) != 200 || content_length != job.audio_bytes) {
        close_request(client);
        return false;
    }

    speaker_audio_begin(job.volume_percent);
    uint8_t chunk[speaker_config::download_chunk_bytes];
    std::size_t downloaded = 0;
    bool download_ok = true;
    const int64_t deadline = esp_timer_get_time() +
                             static_cast<int64_t>(speaker_config::playback_deadline_ms) * 1000;

    // Chỉ giữ một phần audio trong RAM; tác vụ I2S đọc buffer song song.
    while (downloaded < static_cast<std::size_t>(job.audio_bytes)) {
        if (esp_timer_get_time() > deadline) {
            download_ok = false;
            break;
        }
        const int received = esp_http_client_read(client, reinterpret_cast<char *>(chunk), sizeof(chunk));
        if (received <= 0 || downloaded + received > static_cast<std::size_t>(job.audio_bytes)) {
            download_ok = false;
            break;
        }
        if (speaker_audio_push(chunk, received) != ESP_OK) {
            download_ok = false;
            break;
        }
        downloaded += received;
    }

    download_ok = download_ok && downloaded == static_cast<std::size_t>(job.audio_bytes) &&
                  esp_http_client_is_complete_data_received(client);
    close_request(client);

    // Tải xong chưa có nghĩa là phát xong: đợi phần còn trong buffer ra hết I2S.
    const bool abort_playback = !download_ok;
    const esp_err_t playback_result = speaker_audio_end(abort_playback);
    return download_ok && playback_result == ESP_OK;
}

static bool send_ack_once(const SpeakerJob &job, bool played)
{
    char path[160];
    char body[256];
    snprintf(path, sizeof(path), "/v1/devices/%s/ack", speaker_config::device_id);
    snprintf(body, sizeof(body), "{\"id\":\"%s\",\"lease\":\"%s\",\"status\":\"%s\"}",
             job.id, job.lease, played ? "played" : "failed");

    esp_http_client_handle_t client = open_request(path, body);
    if (!client) {
        return false;
    }
    const int status = esp_http_client_get_status_code(client);
    close_request(client);

    // 404/409: job không còn hoặc lease đã hết; gửi lại ACK không giải quyết được.
    return status == 200 || status == 409 || status == 404;
}

void speaker_api_report_result(const SpeakerJob &job, bool played)
{
    for (int attempt = 0; attempt < speaker_config::ack_attempts; ++attempt) {
        if (send_ack_once(job, played)) {
            return;
        }
        vTaskDelay(pdMS_TO_TICKS(speaker_config::ack_retry_delay_ms));
    }
    ESP_LOGW(TAG, "Chua gui duoc ACK cho job %s; khong phat lai cau", job.id);
}
