#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

// Khởi tạo I2S, buffer RAM và tác vụ phát. Gọi một lần khi boot.
esp_err_t speaker_audio_init(void);

// Bắt đầu một câu mới; volume từ 0 (im lặng) đến 100 (mức gốc).
void speaker_audio_begin(unsigned volume);

// Thêm một phần PCM vào buffer. Tác vụ phát sẽ đọc buffer song song.
esp_err_t speaker_audio_push(const uint8_t *data, size_t size);

// Đánh dấu đã tải xong, đợi phát hết. abort_playback=true nếu tải bị lỗi.
esp_err_t speaker_audio_end(bool abort_playback);
