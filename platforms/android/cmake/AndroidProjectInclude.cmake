if(NOT ANDROID)
    return()
endif()

add_subdirectory("${GEMRB_ANDROID_SDL2_ROOT}" "${CMAKE_BINARY_DIR}/android-sdl2" EXCLUDE_FROM_ALL)
