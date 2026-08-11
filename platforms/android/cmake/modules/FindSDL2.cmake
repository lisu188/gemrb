if(NOT ANDROID)
    message(FATAL_ERROR "Android FindSDL2.cmake must only be used for Android builds")
endif()

if(NOT TARGET SDL2::SDL2)
    message(FATAL_ERROR "SDL2::SDL2 target is unavailable; AndroidBootstrap.cmake must add SDL2 first")
endif()

set(SDL2_FOUND TRUE)
set(SDL2_INCLUDE_DIRS "${GEMRB_ANDROID_SDL2_ROOT}/include")
set(SDL2_LIBRARIES SDL2::SDL2)

if(TARGET SDL2::SDL2main)
    list(APPEND SDL2_LIBRARIES SDL2::SDL2main)
    set(SDL2_SDL2main_FOUND TRUE)
else()
    set(SDL2_SDL2main_FOUND FALSE)
endif()
