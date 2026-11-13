// SPDX-FileCopyrightText: 2003 Contributors to the GemRB project <https://gemrb.org>
//
// SPDX-License-Identifier: GPL-2.0-or-later

#include "PLTImporter.h"

#include "RGBAColor.h"

#include "Interface.h"

#include "Video/Video.h"

#include <limits>

using namespace GemRB;

PLTImporter::~PLTImporter(void)
{
	free(pixels);
}

bool PLTImporter::Import(DataStream* str)
{
	char Signature[8];
	unsigned short unknown[4];

	if (str->Read(Signature, 8) != 8) return false;
	if (strncmp(Signature, "PLT V1  ", 8) != 0) {
		return false;
	}

	ieDword width = 0;
	ieDword height = 0;
	if (str->Read(unknown, 8) != 8 || str->ReadDword(width) != 4 || str->ReadDword(height) != 4) return false;
	// Sprite dimensions and row offsets are signed ints. Bound the RGBA
	// result before computing either the packed input or output byte count.
	if (!width || !height || width > std::numeric_limits<int>::max() / 4u / height) return false;
	const size_t inputSize = size_t(width) * height * 2;
	if (inputSize > str->Remains()) return false;
	auto* imported = static_cast<unsigned char*>(malloc(inputSize));
	if (!imported) return false;
	if (str->Read(imported, inputSize) != static_cast<strret_t>(inputSize)) {
		free(imported);
		return false;
	}
	for (size_t i = 1; i < inputSize; i += 2) {
		if (imported[i] >= 8) {
			free(imported);
			return false;
		}
	}
	free(pixels);
	pixels = imported;
	Width = width;
	Height = height;
	return true;
}

Holder<Sprite2D> PLTImporter::GetSprite2D(unsigned int type, ieDword paletteIndex[8])
{
	static int pperm[8] = { 3, 6, 0, 5, 4, 1, 2, 7 };
	ColorPal<256> Palettes[8];
	for (int i = 0; i < 8; i++) {
		Palettes[i] = core->GetPalette256(paletteIndex[pperm[i]] >> (8 * type));
	}
	unsigned char* p = (unsigned char*) malloc(size_t(Width) * Height * 4);
	if (!p) return nullptr;
	unsigned char* dest = p;
	const unsigned char* src = nullptr;
	for (int y = Height - 1; y >= 0; y--) {
		src = (unsigned char*) pixels + (y * Width * 2);
		for (unsigned int x = 0; x < Width; x++) {
			unsigned char intensity = *src++;
			unsigned char palindex = *src++;
			*dest++ = Palettes[palindex][intensity].b;
			*dest++ = Palettes[palindex][intensity].g;
			*dest++ = Palettes[palindex][intensity].r;
			if (intensity == 0xff)
				*dest++ = 0x00;
			else
				*dest++ = 0xff;
		}
	}
	constexpr uint32_t red_mask = 0x00ff0000;
	constexpr uint32_t green_mask = 0x0000ff00;
	constexpr uint32_t blue_mask = 0x000000ff;
	PixelFormat fmt(4, red_mask, green_mask, blue_mask, 0);
	fmt.HasColorKey = true;
	fmt.ColorKey = green_mask;

	Holder<Sprite2D> spr = VideoDriver->CreateSprite(Region(0, 0, Width, Height), p, fmt);
	spr->Frame.x = 0;
	spr->Frame.y = 0;
	return spr;
}

#include "plugindef.h"

GEMRB_PLUGIN(0x8D0C64F, "PLT File Importer")
PLUGIN_IE_RESOURCE(PLTImporter, "plt", (ieWord) IE_PLT_CLASS_ID)
END_PLUGIN()
