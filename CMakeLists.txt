cmake_minimum_required(VERSION 3.27)

project(borders-plus-plus-svg
    DESCRIPTION "borders-plus-plus-svg plugin for Hyprland"
    VERSION 0.1
)

set(CMAKE_CXX_STANDARD 23)

file(GLOB_RECURSE SRC "*.cpp")

add_library(borders-plus-plus-svg SHARED ${SRC})

find_package(PkgConfig REQUIRED)
pkg_check_modules(deps REQUIRED IMPORTED_TARGET
    hyprland
    libdrm
    libinput
    libudev
    pangocairo
    pixman-1
    wayland-server
    xkbcommon
    librsvg-2.0
)
target_link_libraries(borders-plus-plus-svg PRIVATE rt PkgConfig::deps)

install(TARGETS borders-plus-plus-svg)
