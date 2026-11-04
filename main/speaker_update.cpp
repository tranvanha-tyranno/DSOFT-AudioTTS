/** OTA = cập nhật firmware qua mạng.
 *  Đặt ota_url trong speaker_config.h. Tăng VERSION ở CMakeLists.txt cho bản mới.
 */
#include "speaker_update.h"
#include "speaker_config.h"

#include <cstring>
#include "esp_app_desc.h"
#include "esp_crt_bundle.h"
#include "esp_https_ota.h"
#include "esp_log.h"
#include "esp_ota_ops.h"

static const char *TAG = "speaker_update";

void speaker_update_confirm_boot()
{
    const esp_partition_t *running = esp_ota_get_running_partition();
    esp_ota_img_states_t state;
    if (esp_ota_get_state_partition(running, &state) == ESP_OK && state == ESP_OTA_IMG_PENDING_VERIFY) {
        ESP_ERROR_CHECK(esp_ota_mark_app_valid_cancel_rollback());
    }
}

void speaker_update_check()
{
    if (strlen(speaker_config::ota_url) == 0) {
        return;
    }
    if (strncmp(speaker_config::ota_url, "https://", 8) != 0) {
        ESP_LOGE(TAG, "OTA chi chap nhan HTTPS");
        return;
    }

    esp_http_client_config_t http = {};
    http.url = speaker_config::ota_url;
    http.crt_bundle_attach = esp_crt_bundle_attach;
    http.timeout_ms = speaker_config::ota_timeout_ms;
    http.disable_auto_redirect = true;
    esp_https_ota_config_t config = {};
    config.http_config = &http;

    esp_https_ota_handle_t update = nullptr;
    if (esp_https_ota_begin(&config, &update) != ESP_OK) {
        ESP_LOGW(TAG, "Khong mo duoc URL cap nhat");
        return;
    }

    esp_app_desc_t incoming;
    if (esp_https_ota_get_img_desc(update, &incoming) != ESP_OK ||
        strncmp(incoming.version, esp_app_get_description()->version, sizeof(incoming.version)) == 0) {
        // Bỏ qua nếu image lỗi hoặc cùng version với bản đang chạy.
        esp_https_ota_abort(update);
        return;
    }

    esp_err_t result;
    do {
        result = esp_https_ota_perform(update);
    } while (result == ESP_ERR_HTTPS_OTA_IN_PROGRESS);

    if (result == ESP_OK && esp_https_ota_is_complete_data_received(update)) {
        if (esp_https_ota_finish(update) == ESP_OK) {
            esp_restart();
        }
    } else {
        esp_https_ota_abort(update);
    }
}
