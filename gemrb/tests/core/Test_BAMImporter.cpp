// SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
//
// SPDX-License-Identifier: GPL-2.0-or-later

// Match the supported demo/Interface configurations in Test_Map.cpp.
#if defined(USE_OPENGL_BACKEND) || (!defined(__APPLE__) && !defined(WIN32))

	#include "../../core/AnimationMgr.h"
	#include "../../core/Interface.h"
	#include "../../core/InterfaceConfig.h"
	#include "../../core/PluginMgr.h"
	#include "../../core/Streams/MemoryStream.h"

	#include <array>
	#include <clocale>
	#include <cstdlib>
	#include <gtest/gtest.h>

namespace GemRB {

namespace {

	// Original synthetic BAM: two 2x2 frames, two cycles, and a palette
	// between the lookup table and pixels. No game assets are required.
	MemoryStream* MakeBAM(bool rle)
	{
		constexpr ieDword framesOffset = 24;
		constexpr ieDword lookupOffset = framesOffset + 2 * 12 + 2 * 4;
		constexpr ieDword paletteOffset = lookupOffset + 2 * 2;
		constexpr ieDword pixelsOffset = paletteOffset + 256 * 4;
		auto stream = new MemoryStream("synthetic.bam", calloc(pixelsOffset + 8, 1), pixelsOffset + 8);
		stream->Write("BAM V1  ", 8);
		stream->WriteWord(2);
		stream->WriteScalar<ieByte>(2);
		stream->WriteScalar<ieByte>(0); // transparent palette index / RLE marker
		stream->WriteDword(framesOffset);
		stream->WriteDword(paletteOffset);
		stream->WriteDword(lookupOffset);
		for (ieDword frame = 0; frame < 2; ++frame) {
			stream->WriteWord(2); // width
			stream->WriteWord(2); // height
			stream->WriteWord(0); // x
			stream->WriteWord(0); // y
			stream->WriteDword((pixelsOffset + frame * 4) | (rle ? 0 : 0x80000000));
		}
		for (ieWord cycle = 0; cycle < 2; ++cycle) {
			stream->WriteWord(1); // one frame per cycle
			stream->WriteWord(cycle);
		}
		stream->WriteWord(1); // cycle 0 refers to the second frame
		stream->WriteWord(0); // cycle 1 refers to the first frame
		for (int index = 0; index < 256; ++index) {
			const ieByte bgra[] = { 13, 17, static_cast<ieByte>(index), 255 };
			stream->Write(bgra, sizeof(bgra));
		}
		const ieByte pixels[] = { 1, 2, 3, 4, 5, 0, static_cast<ieByte>(rle ? 1 : 0), 6 };
		stream->Write(pixels, sizeof(pixels));
		stream->Seek(0, GEM_STREAM_START);
		return stream;
	}

	void ExpectPixels(const Holder<Sprite2D>& sprite, const std::array<ieByte, 4>& pixels)
	{
		ASSERT_NE(sprite, nullptr);
		EXPECT_EQ(sprite->Frame.size, Size(2, 2));
		for (int index = 0; index < 4; ++index) {
			const auto pixel = pixels[index];
			EXPECT_EQ(sprite->GetPixel(Point(index % 2, index / 2)), Color(pixel, 17, 13, pixel ? 255 : 0));
		}
	}

}

class BAMImporterTest : public testing::Test {
	static std::unique_ptr<Interface> gemrb;

public:
	static void SetUpTestSuite()
	{
		setlocale(LC_ALL, "");
		const char* argv[] = { "tester", "-c", "../../tester.cfg" };
		gemrb = std::make_unique<Interface>(LoadFromArgs(3, const_cast<char**>(argv)));
	}

	static void TearDownTestSuite()
	{
		VideoDriver.reset();
		gemrb.reset();
		core = nullptr;
		PluginMgr::Get()->RunCleanup();
	}
};

std::unique_ptr<Interface> BAMImporterTest::gemrb;

TEST_F(BAMImporterTest, FramePixelsAreReadAfterTheLookupTable)
{
	for (bool rle : { false, true }) {
		SCOPED_TRACE(rle ? "RLE frames" : "uncompressed frames");
		auto importer = GetImporter<AnimationMgr>(IE_BAM_CLASS_ID, MakeBAM(rle));
		ASSERT_NE(importer, nullptr);
		// Reuse the same stream across both decoding paths and repeated calls.
		for (bool allowCompression : { false, true, false, true }) {
			SCOPED_TRACE(allowCompression ? "keep RLE" : "decode RLE");
			auto factory = importer->GetAnimationFactory("bamtest", allowCompression);
			ASSERT_NE(factory, nullptr);
			EXPECT_EQ(factory->GetFrameCount(), 2);
			EXPECT_EQ(factory->GetCycleCount(), 2);
			EXPECT_EQ(factory->GetCycleSize(0), 1);
			EXPECT_EQ(factory->GetCycleSize(1), 1);
			ExpectPixels(factory->GetFrameWithoutCycle(0), { 1, 2, 3, 4 });
			ExpectPixels(factory->GetFrameWithoutCycle(1), { 5, 0, 0, 6 });
			ExpectPixels(factory->GetFrame(0, 0), { 5, 0, 0, 6 });
			ExpectPixels(factory->GetFrame(0, 1), { 1, 2, 3, 4 });
		}
	}
}

}

#endif
