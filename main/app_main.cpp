/**
 * BẮT ĐẦU ĐỌC DỰ ÁN TỪ FILE NÀY.
 *
 * Loa chạy theo 4 bước: chờ WiFi → nhận câu → phát âm thanh → báo kết quả.
 * ESP32 không tạo giọng nói; backend tạo TTS và giao file PCM cho ESP32.
 *
 * Muốn sửa gì, mở file tương ứng:
 *   speaker_config.h   : cấu hình, chân loa, buffer, thời gian chờ.
 *   speaker_api.cpp    : nhận job / tải audio / báo kết quả cho backend.
 *   speaker_audio.cpp  : phát âm thanh ra MAX98357A qua I2S.
 *   speaker_network.cpp: WiFi và đồng bộ đồng hồ.
 *   speaker_update.cpp : OTA (cập nhật firmware qua WiFi).
 *
 * Hướng dẫn từng bước: docs/DOC_CODE_TU_DAU.md.
 */
#include "speaker_api.h"
#include "speaker_audio.h"
#include "speaker_config.h"
#include "speaker_network.h"
#include "speaker_update.h"

#include <cstring>
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"

static const char *TAG = "speaker_main";

// NVS là vùng flash giữ thông tin WiFi sau khi mất nguồn.
static void initialize_storage()
{
    esp_err_t result = nvs_flash_init();
    if (result == ESP_ERR_NVS_NO_FREE_PAGES || result == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        result = nvs_flash_init();
    }
    ESP_ERROR_CHECK(result);
}

// ESP-IDF gọi app_main khi ESP32 khởi động: đây là điểm bắt đầu chương trình.
extern "C" void app_main(void)
{
    // PHẦN 1 — CHUẨN BỊ: chỉ chạy một lần sau khi bật nguồn.
    ESP_LOGI(TAG, "DSOFT WiFi Speaker / ESP32-S3");
    initialize_storage();
    if (!speaker_api_init()) {
        return;  // Điền URL/token trong speaker_config.h theo hướng dẫn trong log.
    }

    ESP_ERROR_CHECK(speaker_audio_init());
    speaker_network_init();
    speaker_network_wait();

    // HTTPS cần giờ đúng để kiểm tra thời hạn chứng chỉ của máy chủ.
    const bool uses_https = strncmp(speaker_config::backend_url, "https://", 8) == 0;
    if (uses_https || strlen(speaker_config::ota_url) > 0) {
        speaker_network_sync_clock();
    }
    speaker_update_confirm_boot();
    speaker_update_check();
    ESP_LOGI(TAG, "Loa %s da san sang", speaker_config::device_id);

    // PHẦN 2 — VÒNG LẶP: mỗi lần xử lý một câu, nên không phát chồng.
    while (true) {
        // Bước 1: nếu WiFi mất, đợi tới khi kết nối lại.
        speaker_network_wait();

        // Bước 2: hỏi backend xem có câu mới không.
        SpeakerJob job;
        if (speaker_api_next_job(job)) {
            // Bước 3: tải từng phần âm thanh và phát ra loa.
            ESP_LOGI(TAG, "Dang phat job %s, volume %d%%", job.id, job.volume_percent);
            const bool played = speaker_api_play_job(job);

            // Bước 4: báo backend đã phát xong hay gặp lỗi (ACK).
            speaker_api_report_result(job, played);
            ESP_LOGI(TAG, "Job %s: %s; heap con %lu byte", job.id,
                     played ? "played" : "failed", static_cast<unsigned long>(esp_get_free_heap_size()));
        }

        // Nghỉ giữa hai lần hỏi; cấu hình mặc định là 1 giây.
        vTaskDelay(pdMS_TO_TICKS(speaker_config::poll_interval_ms));
    }
}
