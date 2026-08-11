if(NOT ANDROID)
    return()
endif()

if(NOT DEFINED GEMRB_ANDROID_OPENAL_PREFIX)
    set(OPENAL_FOUND FALSE)
    return()
endif()

set(OPENAL_INCLUDE_DIR "${GEMRB_ANDROID_OPENAL_PREFIX}/include/AL")
set(_GEMRB_ANDROID_OPENAL_ARCHIVE "${GEMRB_ANDROID_OPENAL_PREFIX}/lib/libopenal.a")

if(EXISTS "${OPENAL_INCLUDE_DIR}/al.h" AND EXISTS "${_GEMRB_ANDROID_OPENAL_ARCHIVE}")
    set(OPENAL_LIBRARY
        "${_GEMRB_ANDROID_OPENAL_ARCHIVE}"
        OpenSLES
        log
        android
        dl
        m
    )
    set(OPENAL_FOUND TRUE)
else()
    set(OPENAL_FOUND FALSE)
endif()
