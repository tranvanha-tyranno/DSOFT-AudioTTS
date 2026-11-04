#pragma once
// Khởi tạo WiFi: dùng SSID cấu hình, WiFi đã lưu hoặc mở provisioning.
void speaker_network_init(void);

// Chặn tác vụ hiện tại tới khi có WiFi/IP. Không chạy vòng lặp bận.
void speaker_network_wait(void);

// Lấy giờ qua SNTP để kiểm tra thời hạn chứng chỉ HTTPS.
void speaker_network_sync_clock(void);
