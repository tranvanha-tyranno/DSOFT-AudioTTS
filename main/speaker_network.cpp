/** WIFI VÀ ĐỒNG HỒ
 *  Có SSID trong cấu hình: dùng SSID đó.
 *  SSID trống + NVS đã lưu WiFi: dùng WiFi đã lưu.
 *  SSID trống + chưa lưu: mở SoftAP provisioning để nhập bằng ứng dụng.
 */
#include "speaker_network.h"
#include "speaker_config.h"

#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif_sntp.h"
#include "esp_wifi.h"
#include "wifi_provisioning/manager.h"
#include "wifi_provisioning/scheme_softap.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

static const char *TAG = "speaker_wifi";
static constexpr EventBits_t WIFI_CONNECTED = BIT0;
static EventGroupHandle_t network_events;

// ESP-IDF gọi hàm này khi WiFi đổi trạng thái, không phải vòng lặp chính gọi.
static void on_network_event(void *argument, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(network_events, WIFI_CONNECTED);
        esp_wifi_connect();  // Tự nối lại sau khi router mất hoặc WiFi yếu.
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        const auto *ip = static_cast<ip_event_got_ip_t *>(data);
        ESP_LOGI(TAG, "Da co WiFi, IP: " IPSTR, IP2STR(&ip->ip_info.ip));
        xEventGroupSetBits(network_events, WIFI_CONNECTED);
    } else if (base == WIFI_PROV_EVENT && id == WIFI_PROV_END) {
        wifi_prov_mgr_deinit();
    } else if (base == WIFI_PROV_EVENT && id == WIFI_PROV_CRED_FAIL) {
        ESP_LOGW(TAG, "Thong tin WiFi sai, thu nhap lai tren ung dung provisioning");
        wifi_prov_mgr_reset_sm_state_on_failure();
    }
}

static void start_station_mode()
{
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
}

static void connect_using_configured_wifi()
{
    wifi_config_t wifi = {};
    strlcpy(reinterpret_cast<char *>(wifi.sta.ssid), speaker_config::wifi_ssid, sizeof(wifi.sta.ssid));
    strlcpy(reinterpret_cast<char *>(wifi.sta.password), speaker_config::wifi_password, sizeof(wifi.sta.password));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi));
    ESP_ERROR_CHECK(esp_wifi_start());
}

static void connect_using_saved_wifi_or_provisioning()
{
    wifi_prov_mgr_config_t provisioning = {};
    provisioning.scheme = wifi_prov_scheme_softap;
    provisioning.scheme_event_handler = WIFI_PROV_EVENT_HANDLER_NONE;
    ESP_ERROR_CHECK(wifi_prov_mgr_init(provisioning));

    bool has_saved_wifi = false;
    ESP_ERROR_CHECK(wifi_prov_mgr_is_provisioned(&has_saved_wifi));
    if (has_saved_wifi) {
        wifi_prov_mgr_deinit();
        start_station_mode();
        return;
    }

    // PoP là mật khẩu chứng minh quyền cấu hình loa, không phải mật khẩu WiFi.
    if (strlen(speaker_config::provisioning_pop) < 8) {
        ESP_LOGE(TAG, "Dien wifi_ssid/wifi_password hoac provisioning_pop trong main/speaker_config.h");
        abort();
    }

    uint8_t mac[6];
    ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_STA, mac));
    char service_name[24];
    snprintf(service_name, sizeof(service_name), "DSOFT_%02X%02X%02X", mac[3], mac[4], mac[5]);
    ESP_LOGI(TAG, "Dung ESP SoftAP Prov: %s, security 1, PoP da cau hinh", service_name);
    ESP_ERROR_CHECK(wifi_prov_mgr_start_provisioning(
        WIFI_PROV_SECURITY_1, speaker_config::provisioning_pop, service_name, nullptr));
}

void speaker_network_init(void)
{
    network_events = xEventGroupCreate();
    assert(network_events);
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    // Luôn tạo netif kể cả khi bản release tắt assert.
    esp_netif_t *station = esp_netif_create_default_wifi_sta();
    esp_netif_t *access_point = esp_netif_create_default_wifi_ap();
    ESP_ERROR_CHECK(station && access_point ? ESP_OK : ESP_ERR_NO_MEM);

    wifi_init_config_t wifi = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_network_event, nullptr));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_network_event, nullptr));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_PROV_EVENT, ESP_EVENT_ANY_ID, on_network_event, nullptr));

    if (strlen(speaker_config::wifi_ssid) > 0) {
        connect_using_configured_wifi();
    } else {
        connect_using_saved_wifi_or_provisioning();
    }

    // Giữ radio hoạt động khi phát stream; tối ưu pin sau khi đã đo trên board.
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
}

void speaker_network_wait(void)
{
    xEventGroupWaitBits(network_events, WIFI_CONNECTED, pdFALSE, pdFALSE, portMAX_DELAY);
}

void speaker_network_sync_clock(void)
{
    esp_sntp_config_t time = ESP_NETIF_SNTP_DEFAULT_CONFIG(speaker_config::time_server);
    ESP_ERROR_CHECK(esp_netif_sntp_init(&time));
    while (esp_netif_sntp_sync_wait(pdMS_TO_TICKS(10000)) != ESP_OK) {
        ESP_LOGW(TAG, "Dang doi dong bo gio de xac thuc HTTPS");
        speaker_network_wait();
    }
}
