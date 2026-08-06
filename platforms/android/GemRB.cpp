// SPDX-FileCopyrightText: 2011 Contributors to the GemRB project <https://gemrb.org>
//
// SPDX-License-Identifier: GPL-2.0-or-later

// GemRB.cpp : Defines the entry point for the application.

#include "AndroidLogger.h"
#include "Interface.h"

#include <SDL.h>
#include <android/log.h>
#include <clocale> //language encoding
#include <cstdlib>

// if/when android moves to SDL 1.3 remove these special functions.
// SDL 1.3 fires window events for these conditions that are handled in SDLVideo.cpp.
// see SDL_WINDOWEVENT_MINIMIZED and SDL_WINDOWEVENT_RESTORED
#if SDL_COMPILEDVERSION < SDL_VERSIONNUM(1, 3, 0)
	#include "Audio.h"

// pause audio playing if app goes in background
static void appPutToBackground()
{
	GemRB::core->GetAudioDrv()->Pause();
}
// resume audio playing if app return to foreground
static void appPutToForeground()
{
	GemRB::core->GetAudioDrv()->Resume();
}

#endif

using namespace GemRB;

int main(int argc, char* argv[])
{
	__android_log_print(ANDROID_LOG_INFO, "GemRB", "GEMRB_ANDROID_NATIVE_START");

	const char* gemrbData = getenv("GEMRB_DATA");
	const char* pythonHome = getenv("PYTHONHOME");
	if (!gemrbData || !pythonHome) {
		__android_log_print(ANDROID_LOG_ERROR, "GemRB", "Android runtime environment is incomplete");
		return GEM_ERROR;
	}
	if (argc >= 3) {
		__android_log_print(ANDROID_LOG_INFO, "GemRB", "GEMRB_ANDROID_CONFIG=%s", argv[2]);
	}
	__android_log_print(ANDROID_LOG_INFO, "GemRB", "GEMRB_ANDROID_RUNTIME=%s", gemrbData);
	__android_log_print(ANDROID_LOG_INFO, "GemRB", "GEMRB_ANDROID_PYTHONHOME=%s", pythonHome);
	__android_log_print(ANDROID_LOG_INFO, "GemRB", "GEMRB_ANDROID_CONFIGURED_START");

	setlocale(LC_ALL, "");
	if (argc > 0 && argv[0]) {
		setenv("SDL_VIDEO_X11_WMCLASS", argv[0], 0);
	}

// Prevent fragmentation of the heap by malloc (glibc).
// The default threshold is 128*1024, which can result in a large memory usage
// due to fragmentation since we use a lot of small objects. On the other hand
// if the threshold is too low, free() starts to permanently ask the kernel
// about shrinking the heap.
#if defined(HAVE_UNISTD_H)
	int pagesize = sysconf(_SC_PAGESIZE);
#else
	int pagesize = 4 * 1024;
#endif
	setenv("MALLOC_TRIM_THRESHOLD_", fmt::format("{}", 5 * pagesize), 1);

	AddLogWriter(createAndroidLogger());
	ToggleLogging(true);

	SanityCheck();

	try {
		Interface gemrb(LoadFromArgs(argc, argv));
		__android_log_print(ANDROID_LOG_INFO, "GemRB", "GEMRB_ANDROID_ENGINE_INIT");
#if SDL_COMPILEDVERSION < SDL_VERSIONNUM(1, 3, 0)
		SDL_ANDROID_SetApplicationPutToBackgroundCallback(&appPutToBackground, &appPutToForeground);
#endif
		gemrb.Main();
	} catch (CoreInitializationException& cie) {
		Log(FATAL, "Main", "Aborting due to fatal error... {}", cie);
		return GEM_ERROR;
	}

	VideoDriver.reset();

	return GEM_OK;
}
