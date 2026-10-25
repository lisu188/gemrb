// SPDX-FileCopyrightText: 2003 Contributors to the GemRB project <https://gemrb.org>
//
// SPDX-License-Identifier: GPL-2.0-or-later


#include "BAMImporter.h"

#include "plugindef.h"

#include "GameData.h"
#include "ImageMgr.h"
#include "Palette.h"

#include "Streams/DataStream.h"
#include "Video/ImageBufferSize.h"
#include "Video/ImageCopyBounds.h"
#include "Video/Video.h"

#include <limits>
#include <memory>

using namespace GemRB;

bool BAMImporter::Import(DataStream* str)
{
	char Signature[8] {};
	if (str->Read(Signature, 8) != 8) return false;
	if (strncmp(Signature, "BAMCV1  ", 8) == 0) {
		if (str->Seek(4, GEM_CURRENT_POS) < 0) return false;
		str = DecompressStream(str);
		if (!str || str->Read(Signature, 8) != 8) return false;
	}

	version = BAMVersion::V1;
	if (strncmp(Signature, "BAM V2  ", 8) == 0) {
		version = BAMVersion::V2;
	} else if (strncmp(Signature, "BAM V1  ", 8) != 0) {
		return false;
	}

	ieDword frameCount = 0;
	if (version == BAMVersion::V1) {
		ieWord count = 0;
		if (str->ReadWord(count) != 2) return false;
		frameCount = count;
	} else {
		if (str->ReadDword(frameCount) != 4) return false;
	}
	// AnimationFactory reserves the maximum index as InvalidIndex.
	if (frameCount >= std::numeric_limits<index_t>::max()) return false;
	frames.resize(frameCount);

	ieDword cycleCount = 0;
	if (version == BAMVersion::V1) {
		ieByte count = 0;
		if (str->ReadScalar(count) != 1) return false;
		cycleCount = count;
	} else {
		if (str->ReadDword(cycleCount) != 4) return false;
	}
	if (cycleCount >= std::numeric_limits<index_t>::max()) return false;
	cycles.resize(cycleCount);

	ieDword dataBlockCount = 0;
	if (version == BAMVersion::V1) {
		if (str->Read(&CompressedColorIndex, 1) != 1) return false;
	} else if (str->ReadDword(dataBlockCount) != 4) {
		return false;
	}
	ieDword PaletteOffset = 0;
	if (str->ReadDword(FramesOffset) != 4) return false;
	if (version == BAMVersion::V1) {
		if (str->ReadDword(PaletteOffset) != 4 || str->ReadDword(FLTOffset) != 4) return false;
		DataStart = str->Size();
	} else {
		ieDword offset = 0;
		if (str->ReadDword(CyclesOffset) != 4 || str->ReadDword(offset) != 4) return false;
		DataStart = offset;
		if (DataStart > str->Size() || dataBlockCount > (str->Size() - DataStart) / 28 ||
		    CyclesOffset > str->Size() || cycles.size() > (str->Size() - CyclesOffset) / 4) return false;
	}
	if (FramesOffset > str->Size() || frames.size() > (str->Size() - FramesOffset) / 12 ||
	    str->Seek(FramesOffset, GEM_STREAM_START) < 0) return false;

	for (auto& frame : frames) {
		ieWord width = 0, height = 0;
		int16_t x = 0, y = 0;
		if (str->ReadWord(width) != 2 || str->ReadWord(height) != 2 ||
		    str->ReadScalar(x) != 2 || str->ReadScalar(y) != 2) return false;
		frame.bounds = Region(x, y, width, height);
		// Empty frames occur in fonts. They need no sprite allocation.
		size_t bytes = 0;
		if (width && height && !CheckedImageByteCount(width, height, version == BAMVersion::V1 ? 1 : 4, bytes)) return false;
		if (version == BAMVersion::V1) {
			ieDword offset = 0;
			if (str->ReadDword(offset) != 4) return false;
			frame.RLE = (offset & 0x80000000) == 0;
			frame.location.dataOffset = offset & 0x7fffffff;
			if (frame.location.dataOffset > str->Size()) return false;
			DataStart = std::min(DataStart, frame.location.dataOffset);
		} else {
			if (str->ReadWord(frame.location.v2.dataBlockIdx) != 2 ||
			    str->ReadWord(frame.location.v2.dataBlockCount) != 2) return false;
			const size_t first = frame.location.v2.dataBlockIdx;
			if (first > dataBlockCount || frame.location.v2.dataBlockCount > dataBlockCount - first) return false;
		}
	}

	if (version == BAMVersion::V2 && str->Seek(CyclesOffset, GEM_STREAM_START) < 0) return false;
	for (auto& cycle : cycles) {
		if (str->ReadWord(cycle.FramesCount) != 2 || str->ReadWord(cycle.FirstFrame) != 2) return false;
		const size_t end = size_t(cycle.FirstFrame) + cycle.FramesCount;
		if (end >= std::numeric_limits<index_t>::max() ||
		    (version == BAMVersion::V2 && end > frames.size())) return false;
	}
	if (version == BAMVersion::V2) return true;

	if (PaletteOffset > str->Size() || str->Size() - PaletteOffset < 1024 ||
	    str->Seek(PaletteOffset, GEM_STREAM_START) < 0) return false;
	palette = MakeHolder<Palette>();
	Palette::Colors buffer;
	for (auto& color : buffer) {
		uint8_t bgra[4] {};
		if (str->Read(bgra, 4) != 4) return false;
		color = Color { bgra[2], bgra[1], bgra[0], bgra[3] ? bgra[3] : uint8_t(255) };
	}
	palette->CopyColors(buffer);
	return true;
}

BAMImporter::index_t BAMImporter::GetCycleSize(index_t cycle)
{
	if (cycle >= cycles.size()) {
		return AnimationFactory::InvalidIndex;
	}
	return cycles[cycle].FramesCount;
}

Holder<Sprite2D> BAMImporter::GetFrameInternal(const FrameEntry& frameInfo, bool RLESprite, const uint8_t* data, size_t dataSize) const
{
	const Region& rgn = frameInfo.bounds;
	if (!rgn.w || !rgn.h) {
		// Fonts use empty sprites for glyph metrics. Keep their concrete sprite
		// and palette without reading a pixel from the stream.
		size_t bytes = 0;
		if (rgn.w < 0 || rgn.h < 0 || !CheckedImageByteCount(std::max(1, rgn.w), std::max(1, rgn.h), 1, bytes)) return nullptr;
		void* pixels = calloc(1, 1);
		if (!pixels) return nullptr;
		return VideoDriver->CreateSprite(rgn, pixels, PixelFormat::Paletted8Bit(palette, true, CompressedColorIndex));
	}
	size_t pixelCount = 0;
	if (!CheckedImageByteCount(rgn.w, rgn.h, 1, pixelCount) || frameInfo.location.dataOffset < DataStart) return nullptr;
	const size_t offset = frameInfo.location.dataOffset - DataStart;
	if (offset > dataSize) return nullptr;
	const uint8_t* dataBegin = data + offset;
	const size_t available = dataSize - offset;
	size_t encodedBytes = 0;
	if (frameInfo.RLE) {
		// Validate each token before retaining or decoding the encoded span.
		for (size_t decoded = 0; decoded < pixelCount;) {
			if (encodedBytes == available) return nullptr;
			const uint8_t pixel = dataBegin[encodedBytes++];
			size_t run = 1;
			if (pixel == CompressedColorIndex) {
				if (encodedBytes == available) return nullptr;
				run += dataBegin[encodedBytes++];
			}
			decoded += std::min(run, pixelCount - decoded);
		}
	} else if (pixelCount > available) {
		return nullptr;
	}

	const size_t bytes = RLESprite ? encodedBytes : pixelCount;
	uint8_t* pixels = static_cast<uint8_t*>(malloc(bytes));
	if (!pixels) return nullptr;
	if (RLESprite || !frameInfo.RLE) {
		memcpy(pixels, dataBegin, bytes);
	} else {
		size_t src = 0;
		for (size_t dst = 0; dst < pixelCount;) {
			const uint8_t pixel = dataBegin[src++];
			const size_t run = pixel == CompressedColorIndex ? std::min<size_t>(size_t(dataBegin[src++]) + 1, pixelCount - dst) : 1;
			std::fill_n(pixels + dst, run, pixel);
			dst += run;
		}
	}
	const PixelFormat fmt = RLESprite ? PixelFormat::RLE8Bit(palette, CompressedColorIndex) : PixelFormat::Paletted8Bit(palette, true, CompressedColorIndex);
	return VideoDriver->CreateSprite(rgn, pixels, fmt);
}

Holder<Sprite2D> BAMImporter::GetV2Frame(const FrameEntry& frame)
{
	if (!frame.bounds.w || !frame.bounds.h) {
		size_t bytes = 0;
		if (frame.bounds.w < 0 || frame.bounds.h < 0 || !CheckedImageByteCount(std::max(1, frame.bounds.w), std::max(1, frame.bounds.h), 4, bytes)) return nullptr;
		void* pixels = calloc(1, 1);
		if (!pixels) return nullptr;
		return VideoDriver->CreateSprite(frame.bounds, pixels, PixelFormat::ARGB32Bit());
	}
	size_t frameSize = 0;
	if (!CheckedImageByteCount(frame.bounds.w, frame.bounds.h, 4, frameSize) || DataStart > str->Size()) return nullptr;
	// The wire record is seven dwords, independent of host struct padding.
	const size_t availableBlocks = (str->Size() - DataStart) / 28;
	const size_t first = frame.location.v2.dataBlockIdx;
	if (first > availableBlocks || frame.location.v2.dataBlockCount > availableBlocks - first) return nullptr;
	std::unique_ptr<uint8_t, decltype(&free)> frameData(static_cast<uint8_t*>(calloc(frameSize, 1)), free);
	if (!frameData || str->Seek(DataStart + first * 28, GEM_STREAM_START) < 0) return nullptr;
	for (uint16_t i = 0; i < frame.location.v2.dataBlockCount; ++i) {
		ieDword fields[7] {};
		for (auto& field : fields) {
			if (str->ReadDword(field) != 4) return nullptr;
		}
		for (size_t field = 1; field < 7; ++field) {
			if (fields[field] > uint32_t(INT_MAX)) return nullptr;
		}
		const BAMV2DataBlock block { fields[0], Point(int(fields[1]), int(fields[2])), Size(int(fields[3]), int(fields[4])), Point(int(fields[5]), int(fields[6])) };
		if (!Blit(frame, block, frameData.get())) return nullptr;
	}
	return VideoDriver->CreateSprite(frame.bounds, frameData.release(), PixelFormat::ARGB32Bit());
}

bool BAMImporter::Blit(const FrameEntry& frame, const BAMV2DataBlock& block, uint8_t* frameData)
{
	if (!ImageContainsRect(frame.bounds.w, frame.bounds.h, block.destination.x, block.destination.y, block.size.w, block.size.h)) return false;
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
		const size_t destination = (size_t(frame.bounds.w) * (size_t(block.destination.y) + y) + block.destination.x) * 4;
		memcpy(frameData + destination, source + size_t(y) * sprite->GetPitch(), rowBytes);
	}
	sprite->UnlockSprite();
	return true;
}

bool BAMImporter::CacheFLT(std::vector<index_t>& FLT)
{
	size_t count = 0;
	for (const auto& cycle : cycles) {
		const size_t end = size_t(cycle.FirstFrame) + cycle.FramesCount;
		if (end >= std::numeric_limits<index_t>::max()) return false;
		count = std::max(count, end);
	}
	if (FLTOffset > str->Size() || count > (str->Size() - FLTOffset) / 2 ||
	    str->Seek(FLTOffset, GEM_STREAM_START) < 0) return false;
	FLT.assign(count, 0);
	for (auto& index : FLT) {
		if (str->ReadWord(index) != 2 || index >= frames.size()) return false;
	}
	return true;
}

std::shared_ptr<AnimationFactory> BAMImporter::GetAnimationFactory(const ResRef& resref, bool allowCompression)
{
	std::vector<Holder<Sprite2D>> animframes;
	std::vector<index_t> FLT;
	if (version == BAMVersion::V1) {
		if (DataStart > str->Size() || !CacheFLT(FLT)) return nullptr;
		const size_t length = str->Size() - DataStart;
		if (!length || length > size_t(std::numeric_limits<strret_t>::max()) || str->Seek(DataStart, GEM_STREAM_START) < 0) return nullptr;
		std::unique_ptr<uint8_t, decltype(&free)> data(static_cast<uint8_t*>(malloc(length)), free);
		if (!data || str->Read(data.get(), length) != strret_t(length)) return nullptr;
		for (const auto& frame : frames) {
			auto sprite = GetFrameInternal(frame, allowCompression && frame.RLE, data.get(), length);
			if (!sprite) return nullptr;
			animframes.push_back(std::move(sprite));
		}
	} else {
		FLT.resize(frames.size());
		for (index_t i = 0; i < frames.size(); ++i) FLT[i] = i;
		for (const auto& frame : frames) {
			auto sprite = GetV2Frame(frame);
			if (!sprite) return nullptr;
			animframes.push_back(std::move(sprite));
		}
	}
	return std::make_shared<AnimationFactory>(resref, std::move(animframes), cycles, std::move(FLT));
}

/** Debug Function: Returns the Global Animation Palette as a Sprite2D Object.
If the Global Animation Palette is NULL, returns NULL. */
Holder<Sprite2D> BAMImporter::GetPalette()
{
	unsigned char* pixels = (unsigned char*) malloc(256);
	if (!pixels) return nullptr;
	unsigned char* p = pixels;
	for (int i = 0; i < 256; i++) {
		*p++ = (unsigned char) i;
	}
	PixelFormat fmt = PixelFormat::Paletted8Bit(palette);
	return VideoDriver->CreateSprite(Region(0, 0, 16, 16), pixels, fmt);
}

#include "plugindef.h"

#include "BAMFontManager.h"

GEMRB_PLUGIN(0x3AD6427A, "BAM File Importer")
PLUGIN_IE_RESOURCE(BAMFontManager, "bam", (ieWord) IE_BAM_CLASS_ID)
PLUGIN_CLASS(IE_BAM_CLASS_ID, ImporterPlugin<BAMImporter>)
END_PLUGIN()
