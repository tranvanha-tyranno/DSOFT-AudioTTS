/** PHÁT ÂM THANH
 *
 * Hai tác vụ làm việc song song:
 *   app_main/speaker_api: tải PCM từ backend → ghi vào buffer.
 *   playback_task: đọc buffer → chỉnh volume → gửi I2S ra MAX98357A.
 *
 * Task = tác vụ FreeRTOS. Buffer = RAM tạm. DMA = phần cứng chuyển mẫu ra I2S.
 * Các kích thước/thời gian chờ nằm trong speaker_config.h.
 */
#include "speaker_audio.h"
#include "speaker_config.h"

#include <cstring>
#include "driver/i2s_std.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/stream_buffer.h"
#include "freertos/event_groups.h"

// Các cờ trao đổi giữa tác vụ tải và tác vụ phát; một câu dùng một lượt cờ.
static constexpr EventBits_t PLAY_REQUESTED = BIT0;
static constexpr EventBits_t DOWNLOAD_FINISHED = BIT1;
static constexpr EventBits_t PLAYBACK_FINISHED = BIT2;
static constexpr EventBits_t PLAYBACK_FAILED = BIT3;

static StreamBufferHandle_t pcm_buffer;
static EventGroupHandle_t playback_events;
static i2s_chan_handle_t i2s_output;
static unsigned volume_percent;
static bool playback_requested;
static const char *TAG = "speaker_audio";

// Giữ phép nhân ở kiểu có dấu: nửa âm của sóng cũng phải giảm đúng theo volume.
static constexpr int16_t scale_pcm_sample(int16_t sample, unsigned volume)
{
    return static_cast<int16_t>(static_cast<int32_t>(sample) * static_cast<int32_t>(volume) / 100);
}

// Kiểm tra ngay lúc biên dịch các biên dễ gây méo âm khi đổi công thức volume.
static_assert(scale_pcm_sample(-12000, 50) == -6000);
static_assert(scale_pcm_sample(-32768, 100) == -32768);
static_assert(scale_pcm_sample(32767, 100) == 32767);
static_assert(scale_pcm_sample(-32768, 0) == 0);

// Ghi đủ dữ liệu ra I2S. Driver có thể nhận ít hơn lượng yêu cầu mỗi lần.
static bool write_to_i2s(const void *data, std::size_t size)
{
    const auto *bytes = static_cast<const uint8_t *>(data);
    std::size_t sent = 0;
    while (sent < size) {
        std::size_t written = 0;
        const esp_err_t result = i2s_channel_write(i2s_output, bytes + sent, size - sent,
                                                  &written, speaker_config::i2s_write_timeout_ms);
        if (result != ESP_OK || written == 0) {
            ESP_LOGE(TAG, "I2S write failed: %s, written=%u", esp_err_to_name(result),
                     static_cast<unsigned>(written));
            return false;
        }
        sent += written;
    }
    return true;
}

// Thêm một đoạn im lặng để phần tiếng cuối đã nằm trong DMA được truyền hết.
static bool flush_audio_tail()
{
    const int16_t silence[speaker_config::playback_chunk_bytes] = {};
    for (int block = 0; block < speaker_config::silence_tail_blocks; ++block) {
        if (!write_to_i2s(silence, sizeof(silence))) {
            return false;
        }
    }
    return true;
}

static bool play_buffered_audio()
{
    uint8_t input[speaker_config::playback_chunk_bytes];
    int16_t stereo[speaker_config::playback_chunk_bytes];

    // PCM16 dùng 2 byte/mẫu. HTTP có thể chia đúng giữa hai byte của một mẫu.
    bool has_first_byte = false;
    uint8_t first_byte = 0;
    std::size_t consumed = 0;
    const int64_t started = esp_timer_get_time();
    int64_t last_progress = started;
    ESP_LOGI(TAG, "Playback start: buffer=%u/%u bytes",
             static_cast<unsigned>(xStreamBufferBytesAvailable(pcm_buffer)),
             static_cast<unsigned>(speaker_config::audio_buffer_bytes));

    while (true) {
        if (xEventGroupGetBits(playback_events) & PLAYBACK_FAILED) {
            return false;
        }

        const std::size_t received = xStreamBufferReceive(
            pcm_buffer, input, sizeof(input), pdMS_TO_TICKS(speaker_config::audio_data_wait_ms));
        if (received == 0) {
            const bool download_finished = xEventGroupGetBits(playback_events) & DOWNLOAD_FINISHED;
            if (download_finished) {
                ESP_LOGI(TAG, "Playback drained: pcm=%u bytes, elapsed=%lld ms",
                         static_cast<unsigned>(consumed), (esp_timer_get_time() - started) / 1000);
                return !has_first_byte;  // Một byte lẻ còn sót nghĩa là audio bị cắt giữa mẫu.
            }
            ESP_LOGE(TAG, "Buffer underrun: pcm=%u bytes, wait=%d ms",
                     static_cast<unsigned>(consumed), speaker_config::audio_data_wait_ms);
            return false;  // Hụt buffer quá thời gian chờ: báo lỗi thay vì báo phát thành công.
        }

        std::size_t output_samples = 0;
        for (std::size_t index = 0; index < received; ++index) {
            if (!has_first_byte) {
                first_byte = input[index];
                has_first_byte = true;
                continue;
            }

            // Ghép low byte + high byte thành một mẫu PCM signed 16-bit little endian.
            int16_t sample = static_cast<int16_t>(
                static_cast<uint16_t>(first_byte) | (static_cast<uint16_t>(input[index]) << 8));
            sample = scale_pcm_sample(sample, volume_percent);

            // Backend trả mono; gửi cùng mẫu sang cả trái và phải của I2S.
            stereo[output_samples++] = sample;
            stereo[output_samples++] = sample;
            has_first_byte = false;
        }

        if (!write_to_i2s(stereo, output_samples * sizeof(int16_t))) {
            return false;
        }
        consumed += received;
        const int64_t now = esp_timer_get_time();
        if (now - last_progress >= 1000000) {
            ESP_LOGI(TAG, "Playback progress: pcm=%u bytes, buffer=%u/%u, elapsed=%lld ms",
                     static_cast<unsigned>(consumed),
                     static_cast<unsigned>(xStreamBufferBytesAvailable(pcm_buffer)),
                     static_cast<unsigned>(speaker_config::audio_buffer_bytes), (now - started) / 1000);
            last_progress = now;
        }
    }
}

static void playback_task(void *argument)
{
    while (true) {
        // Ngủ tới khi có đủ prebuffer hoặc câu ngắn đã tải xong.
        xEventGroupWaitBits(playback_events, PLAY_REQUESTED, pdTRUE, pdFALSE, portMAX_DELAY);

        bool played = false;
        if (i2s_channel_enable(i2s_output) == ESP_OK) {
            played = play_buffered_audio();
            if (played) {
                played = flush_audio_tail();
            }
            i2s_channel_disable(i2s_output);
        }

        // Báo cho speaker_audio_end() rằng tác vụ phát đã xử lý xong câu này.
        xEventGroupSetBits(playback_events, PLAYBACK_FINISHED | (played ? 0 : PLAYBACK_FAILED));
        ESP_LOGI(TAG, "Playback task finished: %s", played ? "played" : "failed");
    }
}

esp_err_t speaker_audio_init(void)
{
    playback_events = xEventGroupCreate();
    if (!playback_events) {
        return ESP_ERR_NO_MEM;
    }

    i2s_chan_config_t channel = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_AUTO, I2S_ROLE_MASTER);
    channel.dma_desc_num = speaker_config::dma_buffer_count;
    channel.dma_frame_num = speaker_config::dma_frames_per_buffer;
    channel.auto_clear = true;
    esp_err_t result = i2s_new_channel(&channel, &i2s_output, nullptr);
    if (result != ESP_OK) {
        return result;
    }

    i2s_std_config_t config = {};
    config.clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(speaker_config::sample_rate_hz);
    config.slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO);
    config.gpio_cfg.mclk = I2S_GPIO_UNUSED;
    config.gpio_cfg.bclk = static_cast<gpio_num_t>(speaker_config::pin_bclk);
    config.gpio_cfg.ws = static_cast<gpio_num_t>(speaker_config::pin_ws);
    config.gpio_cfg.dout = static_cast<gpio_num_t>(speaker_config::pin_dout);
    config.gpio_cfg.din = I2S_GPIO_UNUSED;

    result = i2s_channel_init_std_mode(i2s_output, &config);
    if (result != ESP_OK) {
        return result;
    }

    const BaseType_t created = xTaskCreate(playback_task, "i2s_player",
        speaker_config::player_task_stack_bytes, nullptr, speaker_config::player_task_priority, nullptr);
    return created == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}

// Only the download task releases the buffer, after both tasks have stopped using it.
static void release_pcm_buffer()
{
    if (pcm_buffer) {
        vStreamBufferDelete(pcm_buffer);
        pcm_buffer = nullptr;
        ESP_LOGI(TAG, "Audio RAM released: buffer=0 bytes, heap=%u",
                 static_cast<unsigned>(esp_get_free_heap_size()));
    }
}

esp_err_t speaker_audio_begin(unsigned volume)
{
    if (pcm_buffer) {
        if (!(xEventGroupGetBits(playback_events) & PLAYBACK_FINISHED)) {
            return ESP_ERR_INVALID_STATE;
        }
        // Reap a previous playback that finished after the end() timeout.
        release_pcm_buffer();
    }
    pcm_buffer = xStreamBufferCreate(speaker_config::audio_buffer_bytes, 1);
    if (!pcm_buffer) {
        ESP_LOGE(TAG, "Cannot allocate audio RAM");
        return ESP_ERR_NO_MEM;
    }
    xEventGroupClearBits(playback_events,
        PLAY_REQUESTED | DOWNLOAD_FINISHED | PLAYBACK_FINISHED | PLAYBACK_FAILED);
    volume_percent = volume > 100 ? 100 : volume;
    playback_requested = false;
    ESP_LOGI(TAG, "Audio RAM allocated: %u bytes (temporary, no file storage)",
             static_cast<unsigned>(speaker_config::audio_buffer_bytes));
    return ESP_OK;
}

esp_err_t speaker_audio_push(const uint8_t *data, std::size_t size)
{
    if (!pcm_buffer) {
        return ESP_ERR_INVALID_STATE;
    }
    while (size > 0) {
        if (xEventGroupGetBits(playback_events) & (PLAYBACK_FAILED | PLAYBACK_FINISHED)) {
            return ESP_FAIL;
        }

        const std::size_t written = xStreamBufferSend(
            pcm_buffer, data, size, pdMS_TO_TICKS(speaker_config::buffer_write_timeout_ms));
        if (written == 0) {
            ESP_LOGE(TAG, "Buffer write timeout: buffer=%u/%u bytes",
                     static_cast<unsigned>(xStreamBufferBytesAvailable(pcm_buffer)),
                     static_cast<unsigned>(speaker_config::audio_buffer_bytes));
            return ESP_ERR_TIMEOUT;
        }
        data += written;
        size -= written;

        if (!playback_requested && xStreamBufferBytesAvailable(pcm_buffer) >= speaker_config::prebuffer_bytes) {
            playback_requested = true;
            xEventGroupSetBits(playback_events, PLAY_REQUESTED);
        }
    }
    return ESP_OK;
}

size_t speaker_audio_buffered_bytes(void)
{
    return pcm_buffer ? xStreamBufferBytesAvailable(pcm_buffer) : 0;
}

esp_err_t speaker_audio_end(bool abort_playback)
{
    if (!pcm_buffer) {
        return ESP_ERR_INVALID_STATE;
    }
    // Câu ngắn có thể chưa đủ prebuffer: tải xong thì yêu cầu phát ngay.
    EventBits_t flags = DOWNLOAD_FINISHED;
    if (!playback_requested) {
        flags |= PLAY_REQUESTED;
    }
    if (abort_playback) {
        flags |= PLAYBACK_FAILED;
    }
    xEventGroupSetBits(playback_events, flags);

    EventBits_t result = xEventGroupWaitBits(playback_events, PLAYBACK_FINISHED,
        pdFALSE, pdFALSE, pdMS_TO_TICKS(speaker_config::playback_finish_timeout_ms));
    const bool timed_out = !(result & PLAYBACK_FINISHED);
    if (timed_out) {
        ESP_LOGE(TAG, "Waiting for playback timed out: buffer=%u bytes",
                 static_cast<unsigned>(speaker_audio_buffered_bytes()));
        xEventGroupSetBits(playback_events, PLAYBACK_FAILED);
        result = xEventGroupWaitBits(playback_events, PLAYBACK_FINISHED,
            pdFALSE, pdFALSE, pdMS_TO_TICKS(speaker_config::playback_finish_timeout_ms));
    }
    if (result & PLAYBACK_FINISHED) {
        release_pcm_buffer();
    } else {
        // Never free memory while the I2S task might still be reading it.
        ESP_LOGE(TAG, "Audio cleanup pending: I2S task has not stopped");
    }
    return !timed_out && (result & PLAYBACK_FINISHED) && !(result & PLAYBACK_FAILED)
        ? ESP_OK : ESP_FAIL;
}
