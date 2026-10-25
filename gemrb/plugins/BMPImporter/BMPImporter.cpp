// SPDX-FileCopyrightText: 2003 Contributors to the GemRB project <https://gemrb.org>
//
// SPDX-License-Identifier: GPL-2.0-or-later

#include "BMPImporter.h"

#include "RGBAColor.h"

#include "Video/ImageBufferSize.h"
#include "Video/Video.h"

#include <limits>
#include <memory>

using namespace GemRB;

BMPImporter::~BMPImporter(void)
{
	free(PaletteColors);
	free(pixels);
}

bool BMPImporter::Import(DataStream* str)
{
	free(pixels);
	pixels = nullptr;
	free(PaletteColors);
	PaletteColors = nullptr;
	NumColors = 0;
	BitCount = 0;

	char signature[2] {};
	ieDword fileSize = 0, reserved = 0, dataOffset = 0;
	if (str->Read(signature, 2) != 2 || strncmp(signature, "BM", 2) != 0 ||
	    str->ReadDword(fileSize) != 4 || str->ReadDword(reserved) != 4 ||
	    str->ReadDword(dataOffset) != 4 || str->ReadDword(Size) != 4) return false;

	// The supported Windows/OS2 headers share this 40-byte prefix.
	if (Size < 40 || str->Size() < 14 || Size > str->Size() - 14 ||
	    dataOffset < 14 + size_t(Size) || dataOffset > str->Size()) return false;
	ieDword width = 0, height = 0, unused = 0, colorsUsed = 0;
	if (str->ReadDword(width) != 4 || str->ReadDword(height) != 4 ||
	    str->ReadWord(Planes) != 2 || str->ReadWord(BitCount) != 2 ||
	    str->ReadDword(Compression) != 4 || str->ReadDword(ImageSize) != 4 ||
	    str->ReadDword(unused) != 4 || str->ReadDword(unused) != 4 ||
	    str->ReadDword(colorsUsed) != 4 || str->ReadDword(unused) != 4) return false;

	const bool isV3or5 = Size == 56 || Size == 124;
	hasAlpha = isV3or5;
	if (Planes != 1 || (BitCount != 4 && BitCount != 8 && BitCount != 24 && BitCount != 32) ||
	    (Compression != 0 && !(Compression == 3 && isV3or5 && BitCount == 32))) return false;

	// BMP height is signed; a negative value stores rows from top to bottom.
	const int64_t signedHeight = height <= uint32_t(INT32_MAX) ? int64_t(height) : int64_t(height) - (int64_t(1) << 32);
	const bool topDown = signedHeight < 0;
	const int64_t imageHeight = topDown ? -signedHeight : signedHeight;
	size_t outputBytes = 0;
	const size_t outputBpp = BitCount <= 8 ? 1 : 4;
	if (!CheckedImageByteCount(width, imageHeight, outputBpp, outputBytes)) return false;
	size.w = width;
	size.h = imageHeight;

	if (BitCount <= 8) {
		const ieDword paletteLimit = ieDword(1) << BitCount;
		NumColors = colorsUsed ? colorsUsed : paletteLimit;
		const size_t paletteOffset = 14 + size_t(Size);
		if (NumColors > paletteLimit || NumColors > (dataOffset - paletteOffset) / 4) return false;
		PaletteColors = static_cast<Color*>(malloc(NumColors * sizeof(Color)));
		if (!PaletteColors || str->Seek(paletteOffset, GEM_STREAM_START) < 0) return false;
		for (ieDword i = 0; i < NumColors; ++i) {
			uint8_t color[4] {};
			if (str->Read(color, 4) != 4) return false;
			PaletteColors[i] = Color { color[2], color[1], color[0], color[3] ? color[3] : uint8_t(255) };
		}
	}

	uint32_t rMask = 0xff, gMask = 0xff00, bMask = 0xff0000, aMask = 0xff000000;
	if (isV3or5 && Compression == 3) {
		if (str->Seek(54, GEM_STREAM_START) < 0 || str->ReadDword(rMask) != 4 ||
		    str->ReadDword(gMask) != 4 || str->ReadDword(bMask) != 4 || str->ReadDword(aMask) != 4) return false;
	}
	auto normshift = [](uint32_t mask) {
		if (mask == 0xff000000) return 24;
		if (mask == 0xff0000) return 16;
		if (mask == 0xff00) return 8;
		return 0;
	};

	// Round bits to a four-byte scanline, including the final odd 4-bit pixel.
	const size_t rowBytes = ((size_t(size.w) * BitCount + 31) / 32) * 4;
	if (size_t(size.h) > (str->Size() - dataOffset) / rowBytes) return false;
	const size_t sourceBytes = rowBytes * size_t(size.h);
	if (sourceBytes > size_t(std::numeric_limits<strret_t>::max())) return false;
	std::unique_ptr<uint8_t, decltype(&free)> source(static_cast<uint8_t*>(malloc(sourceBytes)), free);
	std::unique_ptr<uint8_t, decltype(&free)> output(static_cast<uint8_t*>(malloc(outputBytes)), free);
	if (!source || !output || str->Seek(dataOffset, GEM_STREAM_START) < 0 ||
	    str->Read(source.get(), sourceBytes) != strret_t(sourceBytes)) return false;

	for (int y = 0; y < size.h; ++y) {
		const uint8_t* src = source.get() + size_t(y) * rowBytes;
		const int destY = topDown ? y : size.h - 1 - y;
		uint8_t* dst = output.get() + size_t(destY) * size.w * outputBpp;
		for (int x = 0; x < size.w; ++x) {
			if (BitCount <= 8) {
				const uint8_t index = BitCount == 8 ? src[x] : (x & 1 ? src[x / 2] & 15 : src[x / 2] >> 4);
				if (index >= NumColors) return false;
				dst[x] = index;
			} else {
				uint32_t value;
				if (BitCount == 24) {
					value = 0xff000000 | uint32_t(src[x * 3]) << 16 | uint32_t(src[x * 3 + 1]) << 8 | src[x * 3 + 2];
				} else {
					const uint8_t* p = src + size_t(x) * 4;
					const uint32_t pixel = uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
					value = (isV3or5 ? ((pixel & aMask) >> normshift(aMask)) : 0xff) << 24;
					value |= ((pixel & bMask) >> normshift(bMask)) << 16 | ((pixel & gMask) >> normshift(gMask)) << 8 | ((pixel & rMask) >> normshift(rMask));
				}
				memcpy(dst + size_t(x) * 4, &value, 4);
			}
		}
	}
	pixels = output.release();
	BitCount = outputBpp == 1 ? 8 : 32;
	return true;
}

Holder<Sprite2D> BMPImporter::GetSprite2D()
{
	if (!pixels) return nullptr;
	Holder<Sprite2D> spr;
	if (BitCount == 32) {
		constexpr uint32_t redMask = 0x000000ff;
		constexpr uint32_t greenMask = 0x0000ff00;
		constexpr uint32_t blueMask = 0x00ff0000;
		uint32_t alphaMask = hasAlpha ? 0xff000000 : 0;
		PixelFormat fmt(4, redMask, greenMask, blueMask, alphaMask);
		fmt.HasColorKey = true;
		fmt.ColorKey = greenMask | (0xff << 24);

		spr = VideoDriver->CreateSprite(Region(0, 0, size.w, size.h), nullptr, fmt);
		if (!spr || spr->GetPitch() < size_t(size.w) * 4) return nullptr;
		auto* dst = static_cast<uint8_t*>(spr->LockSprite());
		if (!dst) {
			spr->UnlockSprite();
			return nullptr;
		}
		const auto* src = static_cast<const uint8_t*>(pixels);
		for (int y = 0; y < size.h; ++y) {
			memcpy(dst + size_t(y) * spr->GetPitch(), src + size_t(y) * size.w * 4, size_t(size.w) * 4);
		}
		spr->UnlockSprite();
	} else if (BitCount == 8) {
		Holder<Palette> pal = MakeHolder<Palette>(PaletteColors, PaletteColors + NumColors);
		PixelFormat fmt = PixelFormat::Paletted8Bit(pal, pal->GetColorAt(0) == ColorGreen, 0);
		spr = VideoDriver->CreateSprite(Region(0, 0, size.w, size.h), nullptr, fmt);
		if (!spr) return nullptr;
		const uint8_t* src = static_cast<uint8_t*>(pixels);
		const uint8_t* end = src + size.Area();
		auto dst = spr->GetIterator();
		for (; src != end; ++src, ++dst) {
			*dst = *src;
		}
	}
	return spr;
}

int BMPImporter::GetPalette(int colors, Palette& pal)
{
	if (colors < 0 || size_t(colors) > Palette::Colors {}.size()) return -1;
	if (BitCount > 8) return ImageMgr::GetPalette(colors, pal);
	if (!PaletteColors || NumColors == 0) return -1;

	Palette::Colors buffer;
	for (int i = 0; i < colors; ++i) {
		buffer[i] = PaletteColors[i % NumColors];
		buffer[i].a = 0xff;
	}
	pal.CopyColors(0, buffer.cbegin(), buffer.cbegin() + colors);
	return -1;
}

#include "plugindef.h"

GEMRB_PLUGIN(0xD768B1, "BMP File Reader")
PLUGIN_IE_RESOURCE(BMPImporter, "bmp", (ieWord) IE_BMP_CLASS_ID)
END_PLUGIN()
