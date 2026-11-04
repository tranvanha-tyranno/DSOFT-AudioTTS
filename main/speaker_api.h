#pragma once

/** Một "job" là một câu âm thanh mà backend giao cho loa phát.
 *  lease là mã quyền xử lý tạm thời; gửi kèm khi tải audio và báo kết quả.
 *  Struct cố định giúp app_main không phải quản lý bộ nhớ JSON.
 */
struct SpeakerJob {
    char id[65] = {};
    char lease[65] = {};
    int volume_percent = 0;
    int audio_bytes = 0;
};

// Kiểm tra URL/ID/token và chuẩn bị xác thực HTTP. false: chưa cấu hình đủ.
bool speaker_api_init();

// true: có job hợp lệ. false: chưa có hoặc lỗi kết nối/dữ liệu; thử lại sau.
bool speaker_api_next_job(SpeakerJob &job);

// Tải từng phần PCM vào speaker_audio. true chỉ khi phát xong.
bool speaker_api_play_job(const SpeakerJob &job);

// ACK = báo kết quả cho backend. Retry ACK không phát lại câu âm thanh.
void speaker_api_report_result(const SpeakerJob &job, bool played);
