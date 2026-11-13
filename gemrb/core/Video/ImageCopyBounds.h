// SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
//
// SPDX-License-Identifier: GPL-2.0-or-later

#ifndef IMAGECOPYBOUNDS_H
#define IMAGECOPYBOUNDS_H

#include <cstdint>

namespace GemRB {

// Subtract only after validating the origin so rectangle endpoints need not
// be formed in the file's signed-int coordinate representation.
constexpr bool ImageContainsRect(int64_t width, int64_t height, int64_t x, int64_t y,
				 int64_t rectWidth, int64_t rectHeight) noexcept
{
	return width >= 0 && height >= 0 && x >= 0 && y >= 0 && rectWidth >= 0 && rectHeight >= 0 &&
		x <= width && y <= height && rectWidth <= width - x && rectHeight <= height - y;
}

}

#endif
