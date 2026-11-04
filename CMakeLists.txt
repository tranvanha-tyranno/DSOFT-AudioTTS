cmake_minimum_required(VERSION 3.16)
# Chip mục tiêu của dự án loa. Các lệnh build/flash đều dùng ESP32-S3.
set(IDF_TARGET "esp32s3" CACHE STRING "ESP-IDF chip target")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(dsoft_wifi_speaker VERSION 0.1.0)
