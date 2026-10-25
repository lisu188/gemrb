// SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
//
// SPDX-License-Identifier: GPL-2.0-or-later

#include "../../../core/GUI/TextSystem/Font.h"

#include <array>
#include <gtest/gtest.h>

namespace GemRB {

namespace {

	class LockedGlyphSprite : public Sprite2D {
	public:
		using Sprite2D::LockSprite;
		bool locked = false;
		std::array<ieByte, 8> data { 11, 12, 99, 99, 21, 22, 99, 99 };

		explicit LockedGlyphSprite(const Holder<Palette>& pal)
			: Sprite2D(Region(0, 12, 2, 2), nullptr, PixelFormat::Paletted8Bit(pal), 4) {}

		void* LockSprite() override
		{
			locked = true;
			return data.data();
		}
		void UnlockSprite() override
		{
			locked = false;
			data.fill(0); // direct pixel access is valid only while locked
		}
	};

	class CanvasFont : public Font {
	public:
		CanvasFont()
			: Font(MakeHolder<Palette>(), 14, 12, false) {}
		Holder<LockedGlyphSprite> MakeSprite() const { return MakeHolder<LockedGlyphSprite>(palette); }
	};

	class CachedFont : public Font {
	public:
		CachedFont()
			: Font(MakeHolder<Palette>(), 14, 12, false) {}

		using Font::FindGlyph;

		const Glyph& AddGlyph(ieWord chr, int width)
		{
			const Region frame(0, 12, width, 0);
			auto sprite = MakeHolder<Sprite2D>(frame, nullptr, PixelFormat::Paletted8Bit(palette));
			return CreateGlyphForCharSprite(chr, sprite);
		}
	};

}

TEST(FontTest, DeferredGlyphLookupDoesNotReturnFallback)
{
	CachedFont font;
	EXPECT_EQ(font.FindGlyph('A'), nullptr);

	// Match the initial cache of a TrueType font: an empty error glyph and
	// whitespace exist, but ordinary glyphs have not been rasterized yet.
	const Glyph& blank = font.AddGlyph(0, 0);
	font.AddGlyph(' ', 3);
	font.AddGlyph('\t', 12);
	ASSERT_NE(blank.pixels, nullptr);
	EXPECT_EQ(blank.size.w, 0);
	EXPECT_EQ(font.GetGlyph('A').size.w, 0);
	EXPECT_EQ(font.FindGlyph('A'), nullptr);
	EXPECT_EQ(font.FindGlyph(31), nullptr); // an uncached hole inside the index

	const Glyph& letter = font.AddGlyph('A', 8);
	EXPECT_EQ(font.FindGlyph('A'), &letter);
	EXPECT_EQ(&font.GetGlyph('A'), &letter);
	EXPECT_EQ(font.StringSize(u"AAA").w, 24);
}

TEST(FontTest, ExplicitWhitespaceAliasesAreCached)
{
	CachedFont font;
	const Glyph& space = font.AddGlyph(' ', 3);
	EXPECT_EQ(font.FindGlyph(0x3000), nullptr);

	font.CreateAliasForChar(' ', 0x3000);
	EXPECT_EQ(font.FindGlyph(0x3000), &space);
	EXPECT_EQ(font.StringSize(u"\u3000").w, 3);
}


TEST(FontTest, GlyphAtlasCopiesPaddedRowsBeforeUnlock)
{
	CanvasFont font;
	auto sprite = font.MakeSprite();
	const Glyph& glyph = font.CreateGlyphForCharSprite('A', sprite);

	EXPECT_FALSE(sprite->locked);
	EXPECT_EQ(sprite->data[0], 0);
	ASSERT_NE(glyph.pixels, nullptr);
	EXPECT_EQ(glyph.pixels[0], 11);
	EXPECT_EQ(glyph.pixels[1], 12);
	EXPECT_EQ(glyph.pixels[glyph.pitch], 21);
	EXPECT_EQ(glyph.pixels[glyph.pitch + 1], 22);
}

}
