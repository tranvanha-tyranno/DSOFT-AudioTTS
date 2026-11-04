# Checklist kiểm thử trên ESP32

Các mục dưới đây **chưa được xác nhận trên phần cứng**. Ghi ngày, version, board, nguồn, kết quả và log khi chạy.

- [ ] Xác nhận board ESP32-S3, baseline flash 4 MB/PSRAM tắt, chân 15/16/7 và nguồn MAX98357A.
- [ ] Điền WiFi/server trong `main/speaker_config.h`, build/nạp; boot có log sẵn sàng, không brownout/reset.
- [ ] Provisioning PoP đúng thành công; PoP sai bị chặn; credentials còn sau reboot.
- [ ] SSID/password sai có thể nhập lại; WiFi mất/khôi phục tự reconnect.
- [ ] HTTPS xác thực đúng domain và thời gian; chứng chỉ sai bị từ chối.
- [ ] Tone 440 Hz một giây nghe đúng, volume 0 im lặng, không bị hụt đoạn cuối.
- [ ] PCM 1/10/60 giây và HTTP bị chia chunk lẻ vẫn đúng tốc độ và không lệch mẫu.
- [ ] Cắt stream/mất WiFi giữa câu: job failed hoặc lease hết hạn; không tự phát lại.
- [ ] 100 job FIFO/priority, chỉ một câu đang phát.
- [ ] Gửi lại một request và làm mất ACK: không sinh thêm lượt phát.
- [ ] Ghép API thật; 20 câu tiếng Việt; đối chiếu số/ngày giờ và cache.
- [ ] Đo P50/P95 latency request→tiếng đầu, minimum heap, reset reason, dropout.
- [ ] Soak 8 giờ/500 job; ghi log, nghe mẫu ngẫu nhiên và kiểm tra heap theo thời gian.
- [ ] OTA image version mới đúng chip thành công; image lỗi/version cũ xử lý rõ.
- [ ] Thử mất nguồn lúc OTA; thử image không qua self-test để xác nhận rollback.

Không đánh dấu đạt bằng kết quả compile hoặc test backend. Xem mục tiêu đề xuất trong `PLAN_P01.md`.
