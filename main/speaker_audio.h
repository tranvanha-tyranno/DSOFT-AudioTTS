#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

// Khởi tạo I2S và tác vụ phát. Chưa cấp phát buffer audio khi boot.
esp_err_t speaker_audio_init(void);

// Bắt đầu một câu mới; volume từ 0 (im lặng) đến 100 (mức gốc).
esp_err_t speaker_audio_begin(unsigned volume);

// Thêm một phần PCM vào buffer. Tác vụ phát sẽ đọc buffer song song.
esp_err_t speaker_audio_push(const uint8_t *data, size_t size);

// Số byte PCM đang chờ phát trong RAM, dùng để theo dõi tiến độ.
size_t speaker_audio_buffered_bytes(void);

// Đánh dấu đã tải xong, đợi phát hết rồi giải phóng buffer RAM.
// abort_playback=true nếu tải bị lỗi; vẫn giải phóng sau khi I2S dừng.
esp_err_t speaker_audio_end(bool abort_playback);
