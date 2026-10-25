// SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
//
// SPDX-License-Identifier: GPL-2.0-or-later

#ifndef IMAGEBUFFERSIZE_H
#define IMAGEBUFFERSIZE_H

#include <cstddef>
#include <cstdint>
#include <limits>

namespace GemRB {

// Sprite2D stores pitch in uint16_t and image row/area calculations use int.
// Check those representations before evaluating a product or narrowing a size.
constexpr bool CheckedImageByteCount(int64_t width, int64_t height, size_t bytesPerPixel, size_t& bytes) noexcept
{
	bytes = 0;
	const size_t limit = std::numeric_limits<int>::max();
	if (width <= 0 || height <= 0 || !bytesPerPixel || bytesPerPixel > limit ||
	    uint64_t(width) > std::numeric_limits<uint16_t>::max() / bytesPerPixel ||
	    uint64_t(height) > limit || size_t(width) > limit / bytesPerPixel / size_t(height)) return false;
	bytes = size_t(width) * size_t(height) * bytesPerPixel;
	return true;
}

}

#endif
