## Danh sách mã firmware được biên dịch. Thêm file .cpp mới tại SRCS.
idf_component_register(SRCS
    "app_main.cpp"
    "speaker_api.cpp"
    "speaker_audio.cpp"
    "speaker_network.cpp"
    "speaker_update.cpp"
    INCLUDE_DIRS "."
    PRIV_REQUIRES esp_driver_i2s esp_driver_gpio esp_wifi esp_netif esp_event
        nvs_flash wifi_provisioning esp_http_client mbedtls json esp_timer
        app_update esp_https_ota)
