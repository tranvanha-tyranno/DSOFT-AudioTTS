#pragma once

/**
 * CẤU HÌNH TRỰC TIẾP TRONG CODE — sửa các giá trị bên dưới rồi build/nạp lại.
 *
 * Điền WiFi và URL/token trong speaker_config.local.h (file riêng, không lên Git).
 * URL/token lấy từ Dashboard → Thiết bị. Không cần menuconfig cho loa.
 * sdkconfig.h bên dưới chỉ cung cấp thông tin chip/nền tảng của ESP-IDF.
 *
 * API TTS thật nằm ở backend, không đặt khóa nhà cung cấp trên ESP32.
 */
#include <cstddef>
#include "sdkconfig.h"
#include "esp_bit_defs.h"
#include "soc/soc_caps.h"

#if !CONFIG_IDF_TARGET_ESP32S3
#error "This speaker project targets ESP32-S3. Build with IDF_TARGET=esp32s3."
#endif

namespace speaker_config {

// 1-2. WIFI / SERVER - private values stay on the firmware build machine.
// Copy speaker_config.local.h.example to speaker_config.local.h, then fill in
// WiFi and the URL/token from Dashboard > Devices. The local file is gitignored.
#if __has_include("speaker_config.local.h")
#include "speaker_config.local.h"
#else
inline constexpr const char *wifi_ssid = "";
inline constexpr const char *wifi_password = "";
inline constexpr const char *backend_url = "";
inline constexpr const char *device_id = "speaker-01";
inline constexpr const char *device_token = "";
inline constexpr bool allow_http_for_development = false;
inline constexpr const char *provisioning_pop = "";
#endif
inline constexpr int poll_interval_ms = 1000;
inline constexpr const char *time_server = "pool.ntp.org";

// 3. CHÂN I2S — ESP32-S3 gửi dữ liệu âm thanh số sang MAX98357A.
// S3 không có GPIO22–25; giữ GPIO19/20 cho USB và tránh các chân flash/PSRAM.
inline constexpr int pin_bclk = 15;  // GPIO15 → BCLK của amp.
inline constexpr int pin_ws = 16;    // GPIO16 → LRCK/LRC/WS của amp.
inline constexpr int pin_dout = 7;   // GPIO7 → DIN của amp (TX only).

inline constexpr bool valid_i2s_gpio(int pin)
{
    return pin >= 0 && pin <= 48 && ((SOC_GPIO_VALID_OUTPUT_GPIO_MASK >> pin) & 1ULL);
}
static_assert(valid_i2s_gpio(pin_bclk) && valid_i2s_gpio(pin_ws) && valid_i2s_gpio(pin_dout),
              "I2S pins must be valid ESP32-S3 output GPIOs (GPIO22-25 do not exist).");
static_assert(pin_bclk != pin_ws && pin_bclk != pin_dout && pin_ws != pin_dout,
              "I2S BCLK, WS and DOUT must use different GPIOs.");

// 4. ĐỊNH DẠNG — backend phải trả đúng PCM16 mono 24 kHz.
// 24.000 mẫu/giây × 2 byte/mẫu × 1 kênh = 48.000 byte/giây.
// Đổi định dạng phải sửa cả backend và phần chuyển mẫu I2S.
inline constexpr int sample_rate_hz = 24000;
inline constexpr int pcm_bytes_per_sample = 2;
inline constexpr int max_audio_seconds = 60;
inline constexpr int max_audio_bytes = sample_rate_hz * pcm_bytes_per_sample * max_audio_seconds;

// 5. BUFFER — vùng RAM giữ audio giữa tác vụ tải và tác vụ phát.
inline constexpr std::size_t audio_buffer_bytes = 32 * 1024;
inline constexpr std::size_t prebuffer_bytes = 12 * 1024;
inline constexpr std::size_t download_chunk_bytes = 4096;
inline constexpr std::size_t playback_chunk_bytes = 1024;
static_assert(prebuffer_bytes < audio_buffer_bytes, "Prebuffer must fit in audio buffer");
static_assert(playback_chunk_bytes % pcm_bytes_per_sample == 0, "PCM chunks must fit whole samples");

// 6. THỜI GIAN CHỜ — đơn vị mili giây.
inline constexpr int http_timeout_ms = 5000;
inline constexpr int playback_deadline_ms = 120000;
inline constexpr int audio_data_wait_ms = 100;
inline constexpr int buffer_write_timeout_ms = 500;
inline constexpr int playback_finish_timeout_ms = 5000;
inline constexpr int i2s_write_timeout_ms = 1000;
inline constexpr int ack_attempts = 5;
inline constexpr int ack_retry_delay_ms = 2000;

// 7. TÁC VỤ PHÁT — ưu tiên hơn vòng lặp tải để cấp mẫu đều cho I2S.
inline constexpr int player_task_stack_bytes = 6144;
inline constexpr int player_task_priority = 6;
inline constexpr int dma_buffer_count = 6;
inline constexpr int dma_frames_per_buffer = 240;
inline constexpr int silence_tail_blocks = 8;

// 8. OTA — cập nhật firmware qua WiFi. URL trống: bỏ qua.
inline constexpr const char *ota_url = "";
inline constexpr int ota_timeout_ms = 10000;

}  // namespace speaker_config
