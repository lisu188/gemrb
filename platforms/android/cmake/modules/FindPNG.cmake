if(NOT ANDROID OR NOT DEFINED GEMRB_ANDROID_PNG_PREFIX)
    include("${CMAKE_ROOT}/Modules/FindPNG.cmake")
    return()
endif()

set(PNG_INCLUDE_DIRS "${GEMRB_ANDROID_PNG_PREFIX}/include")
set(PNG_LIBRARIES "${GEMRB_ANDROID_PNG_PREFIX}/lib/libpng16.a;ZLIB::ZLIB")

if(EXISTS "${GEMRB_ANDROID_PNG_PREFIX}/include/png.h" AND EXISTS "${GEMRB_ANDROID_PNG_PREFIX}/lib/libpng16.a")
    set(PNG_FOUND TRUE)
else()
    set(PNG_FOUND FALSE)
endif()
