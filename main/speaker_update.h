#pragma once

// Self-test tối thiểu: driver âm thanh + WiFi khởi tạo được, chưa kiểm tra tiếng thật.
void speaker_update_confirm_boot();

// Kiểm tra OTA URL một lần khi boot. URL trống: bỏ qua.
void speaker_update_check();
