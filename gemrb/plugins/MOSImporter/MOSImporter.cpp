// SPDX-FileCopyrightText: 2003 Contributors to the GemRB project <https://gemrb.org>
//
// SPDX-License-Identifier: GPL-2.0-or-later

#include "MOSImporter.h"

#include "GameData.h"

#include "Video/ImageBufferSize.h"
#include "Video/ImageCopyBounds.h"
#include "Video/Video.h"

#include <memory>

using namespace GemRB;

bool MOSImporter::Import(DataStream* str)
{
	char Signature[8] {};
	if (str->Read(Signature, 8) != 8) return false;
	if (strncmp(Signature, "MOSCV1  ", 8) == 0) {
		if (str->Seek(4, GEM_CURRENT_POS) < 0) return false;
		str = DecompressStream(str);
		if (!str || str->Read(Signature, 8) != 8) return false;
	}

	version = MOSVersion::V1;
	if (strncmp(Signature, "MOS V2  ", 8) == 0) {
		version = MOSVersion::V2;
	} else if (strncmp(Signature, "MOS V1  ", 8) != 0) {
		return false;
	}

	if (version == MOSVersion::V1) {
		ieWord width = 0, height = 0;
		if (str->ReadWord(width) != 2 || str->ReadWord(height) != 2 ||
		    str->ReadWord(Cols) != 2 || str->ReadWord(Rows) != 2 ||
		    str->ReadDword(layout.v1.BlockSize) != 4 || str->ReadDword(layout.v1.PalOffset) != 4) return false;
		size = Size(width, height);
		// MOS V1 tiles are 64x64, with partial tiles at the right/bottom edges.
		if (layout.v1.BlockSize != 64 || Cols != (size.w + 63) / 64 || Rows != (size.h + 63) / 64) return false;
		const size_t blockCount = size_t(Rows) * Cols;
		if (layout.v1.PalOffset > str->Size() || blockCount > (str->Size() - layout.v1.PalOffset) / 1028) return false;
	} else {
		ieDword width = 0, height = 0;
		if (str->ReadDword(width) != 4 || str->ReadDword(height) != 4 ||
		    str->ReadDword(layout.v2.NumBlocks) != 4 || str->ReadDword(layout.v2.BlockOffset) != 4 ||
		    width > uint32_t(INT_MAX) || height > uint32_t(INT_MAX)) return false;
		size = Size(int(width), int(height));
		if (layout.v2.BlockOffset > str->Size() ||
		    layout.v2.NumBlocks > (str->Size() - layout.v2.BlockOffset) / 28) return false;
	}
	size_t bytes = 0;
	return CheckedImageByteCount(size.w, size.h, 4, bytes);
}

bool MOSImporter::Blit(const MOSV2DataBlock& block, uint8_t* frameData)
{
	if (!ImageContainsRect(size.w, size.h, block.destination.x, block.destination.y, block.size.w, block.size.h)) return false;
	if (!block.size.w || !block.size.h) return true;
	if (!lastPVRZ || block.pvrzPage != lastPVRZPage) {
		auto resRef = fmt::format("mos{:04d}", block.pvrzPage);
		lastPVRZ = gamedata->GetResourceHolder<ImageMgr>(resRef, true);
		lastPVRZPage = block.pvrzPage;
	}
	if (!lastPVRZ) return false;
	const auto sourceSize = lastPVRZ->GetSize();
	if (!ImageContainsRect(sourceSize.w, sourceSize.h, block.source.x, block.source.y, block.size.w, block.size.h)) return false;
	auto sprite = lastPVRZ->GetSprite2D(Region { block.source.x, block.source.y, block.size.w, block.size.h });
	const size_t rowBytes = size_t(block.size.w) * 4;
	if (!sprite || sprite->Format().Bpp != 4 || sprite->Frame.w < block.size.w || sprite->Frame.h < block.size.h || sprite->GetPitch() < rowBytes) return false;
	const uint8_t* source = static_cast<const uint8_t*>(sprite->LockSprite());
	if (!source) {
		sprite->UnlockSprite();
		return false;
	}
	for (int y = 0; y < block.size.h; ++y) {
		const size_t destination = (size_t(size.w) * (size_t(block.destination.y) + y) + block.destination.x) * 4;
		memcpy(frameData + destination, source + size_t(y) * sprite->GetPitch(), rowBytes);
	}
	sprite->UnlockSprite();
	return true;
}

Holder<Sprite2D> MOSImporter::GetSprite2D()
{
	return version == MOSVersion::V2 ? GetSprite2Dv2() : GetSprite2Dv1();
}

Holder<Sprite2D> MOSImporter::GetSprite2Dv2()
{
	size_t imageSize = 0;
	if (!CheckedImageByteCount(size.w, size.h, 4, imageSize)) return nullptr;
	std::unique_ptr<uint8_t, decltype(&free)> imageData(static_cast<uint8_t*>(calloc(imageSize, 1)), free);
	if (!imageData || str->Seek(layout.v2.BlockOffset, GEM_STREAM_START) < 0) return nullptr;

	for (ieDword i = 0; i < layout.v2.NumBlocks; ++i) {
		ieDword fields[7] {};
		for (auto& field : fields) {
			if (str->ReadDword(field) != 4) return nullptr;
		}
		for (size_t field = 1; field < 7; ++field) {
			if (fields[field] > uint32_t(INT_MAX)) return nullptr;
		}
		const MOSV2DataBlock block { fields[0], Point(int(fields[1]), int(fields[2])), Size(int(fields[3]), int(fields[4])), Point(int(fields[5]), int(fields[6])) };
		if (!Blit(block, imageData.get())) return nullptr;
	}
	return VideoDriver->CreateSprite(Region(0, 0, size.w, size.h), imageData.release(), PixelFormat::ARGB32Bit());
}

Holder<Sprite2D> MOSImporter::GetSprite2Dv1()
{
	size_t imageSize = 0;
	if (!CheckedImageByteCount(size.w, size.h, 4, imageSize)) return nullptr;
	const size_t blockCount = size_t(Rows) * Cols;
	const size_t paletteOffset = layout.v1.PalOffset;
	if (paletteOffset > str->Size() || blockCount > (str->Size() - paletteOffset) / 1028) return nullptr;
	const size_t offsetTable = paletteOffset + blockCount * 1024;
	const size_t pixelOffset = offsetTable + blockCount * 4;
	std::unique_ptr<uint8_t, decltype(&free)> pixels(static_cast<uint8_t*>(malloc(imageSize)), free);
	if (!pixels) return nullptr;
	Color colors[256];
	uint8_t blockPixels[64 * 64];
	for (int y = 0; y < Rows; ++y) {
		const int bh = std::min(64, size.h - y * 64);
		for (int x = 0; x < Cols; ++x) {
			const int bw = std::min(64, size.w - x * 64);
			const size_t blockIndex = size_t(y) * Cols + x;
			if (str->Seek(paletteOffset + blockIndex * 1024, GEM_STREAM_START) < 0 || str->Read(colors, 1024) != 1024 ||
			    str->Seek(offsetTable + blockIndex * 4, GEM_STREAM_START) < 0) return nullptr;
			ieDword blockOffset = 0;
			const size_t blockBytes = size_t(bw) * bh;
			if (str->ReadDword(blockOffset) != 4 || blockOffset > str->Size() - pixelOffset ||
			    blockBytes > str->Size() - pixelOffset - blockOffset ||
			    str->Seek(pixelOffset + blockOffset, GEM_STREAM_START) < 0 ||
			    str->Read(blockPixels, blockBytes) != strret_t(blockBytes)) return nullptr;
			for (int row = 0; row < bh; ++row) {
				uint8_t* dst = pixels.get() + (size_t(size.w) * (y * 64 + row) + x * 64) * 4;
				for (int col = 0; col < bw; ++col) {
					const Color& color = colors[blockPixels[row * bw + col]];
					*dst++ = color.r;
					*dst++ = color.g;
					*dst++ = color.b;
					*dst++ = color.a;
				}
			}
		}
	}
	constexpr uint32_t redMask = 0x00ff0000;
	constexpr uint32_t greenMask = 0x0000ff00;
	constexpr uint32_t blueMask = 0x000000ff;
	PixelFormat fmt(4, redMask, greenMask, blueMask, 0);
	fmt.HasColorKey = true;
	fmt.ColorKey = greenMask;
	return VideoDriver->CreateSprite(Region(0, 0, size.w, size.h), pixels.release(), fmt);
}

#include "plugindef.h"

GEMRB_PLUGIN(0x167B73E, "MOS File Importer")
PLUGIN_IE_RESOURCE(MOSImporter, "mos", (ieWord) IE_MOS_CLASS_ID)
END_PLUGIN()
