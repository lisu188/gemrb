// SPDX-FileCopyrightText: 2011 Contributors to the GemRB project <https://gemrb.org>
//
// SPDX-License-Identifier: GPL-2.0-or-later

#include "AndroidLogger.h"

#include <android/log.h>

namespace GemRB {

void AndroidLogger::WriteLogMessage(const Logger::LogMessage& msg)
{
	android_LogPriority priority = ANDROID_LOG_INFO;
	const char* level = "UNKNOWN";
	switch (msg.level) {
		case INTERNAL:
			priority = ANDROID_LOG_VERBOSE;
			level = "INTERNAL";
			break;
		case FATAL:
			priority = ANDROID_LOG_FATAL;
			level = "FATAL";
			break;
		case ERROR:
			priority = ANDROID_LOG_ERROR;
			level = "ERROR";
			break;
		case WARNING:
			priority = ANDROID_LOG_WARN;
			level = "WARNING";
			break;
		case MESSAGE:
			priority = ANDROID_LOG_INFO;
			level = "MESSAGE";
			break;
		case COMBAT:
			priority = ANDROID_LOG_INFO;
			level = "COMBAT";
			break;
		case DEBUG:
			priority = ANDROID_LOG_DEBUG;
			level = "DEBUG";
			break;
		case count:
			break;
	}
	__android_log_print(priority, "GemRB", "[%s/%s]: %s", msg.owner.c_str(), level, msg.message.c_str());
}

Logger::WriterPtr createAndroidLogger()
{
	return Logger::WriterPtr(new AndroidLogger());
}

}
