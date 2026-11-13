// SPDX-FileCopyrightText: 2022 Contributors to the GemRB project <https://gemrb.org>
//
// SPDX-License-Identifier: GPL-2.0-or-later


#include "Geometry.h"

#include <cmath>
#include <cstdint>
#include <limits>
#include <new>
#include <stdexcept>

namespace GemRB {

// Fast approximation of atan2(y, x)
// with a maximum error of 0.1620 degrees
// rcor's rational approximation that can be arbitrarily
// improved if we ever want greater precision
static float pseudoAtan2(float y, float x)
{
	static const uint32_t signMask = 0x80000000;
	static const float b = 0.596227F;
	if (x == 0 && y == 0) return -M_PI_2;

	// Extract the sign bits
	uint32_t xS = signMask & (uint32_t&) x;
	uint32_t yS = signMask & (uint32_t&) y;

	// Determine the quadrant offset
	float q = float((~xS & yS) >> 29 | xS >> 30);

	// Calculate the arctangent in the first quadrant
	float bxy = std::fabs(b * x * y);
	float num = bxy + y * y;
	float atan1q = num / (x * x + bxy + num);

	// Translate it to the proper quadrant
	uint32_t uatan2q = (xS ^ yS) | (uint32_t&) atan1q;
	return (q + (float&) uatan2q) * M_PI_2;
}

float_t AngleFromPoints(float_t y, float_t x)
{
	return pseudoAtan2(y, x);
}

float_t AngleFromPoints(const Point& p1, const Point& p2, bool exact)
{
	float_t xdiff = p1.x - p2.x;
	float_t ydiff = p1.y - p2.y;
	if (xdiff == 0 && ydiff == 0) return -M_PI_2;

	float_t angle;
	if (exact) {
		angle = std::atan2(ydiff, xdiff);
	} else {
		angle = pseudoAtan2(ydiff, xdiff);
	}
	return angle;
}

Point RotatePoint(const Point& p, float_t angle)
{
	int newx = static_cast<int>(p.x * std::cos(angle) - p.y * std::sin(angle));
	int newy = static_cast<int>(p.x * std::sin(angle) + p.y * std::cos(angle));
	return Point(newx, newy);
}

/** Calculates distance between 2 points */
unsigned int Distance(const BasePoint& p, const BasePoint& q)
{
	long x = p.x - q.x;
	long y = p.y - q.y;
	return (unsigned int) std::hypot(x, y);
}

/** Calculates squared distance between 2 points */
unsigned int SquaredDistance(const BasePoint& p, const BasePoint& q)
{
	long x = p.x - q.x;
	long y = p.y - q.y;
	return static_cast<unsigned int>(x * x + y * y);
}

// returns twice the area of triangle a, b, c.
// (can also be negative depending on orientation of a,b,c)
int area2(const BasePoint& a, const BasePoint& b, const BasePoint& c)
{
	return (b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y);
}

// return (c is to the left of a-b)
bool left(const BasePoint& a, const BasePoint& b, const BasePoint& c)
{
	return (area2(a, b, c) > 0);
}

// { return (c is collinear with a-b)
bool collinear(const Point& a, const Point& b, const Point& c)
{
	return (area2(a, b, c) == 0);
}

// Find the intersection of two segments, if any.
// If the intersection is one of the endpoints, or the lines are
// parallel, false is returned.
// The point returned has the actual intersection coordinates rounded down
// to integers
bool intersectSegments(const Point& a, const Point& b, const Point& c, const Point& d, Point& s)
{
	if (collinear(a, b, c) || collinear(a, b, d) ||
	    collinear(c, d, a) || collinear(c, d, b))
		return false;

	if (!((left(a, b, c) != left(a, b, d)) &&
	      (left(c, d, a) != left(c, d, b))))
		return false;

	int64_t A1 = area2(c, d, a);
	int64_t A2 = area2(d, c, b);

	s.x = int((b.x * A1 + a.x * A2) / (A1 + A2));
	s.y = int((b.y * A1 + a.y * A2) / (A1 + A2));

	return true;
}

// find the intersection of a segment with a horizontal scanline, if any
bool intersectSegmentScanline(const Point& a, const Point& b, int y, int& x)
{
	int y1 = a.y - y;
	int y2 = b.y - y;

	if (y1 * y2 > 0) return false;
	if (y1 == 0 && y2 == 0) return false;

	x = a.x + ((b.x - a.x) * y1) / (y1 - y2);
	return true;
}

namespace {

	bool CheckedAdd64(int64_t lhs, int64_t rhs, int64_t& result) noexcept
	{
		const auto min = std::numeric_limits<int64_t>::min();
		const auto max = std::numeric_limits<int64_t>::max();
		if ((rhs > 0 && lhs > max - rhs) || (rhs < 0 && lhs < min - rhs)) return false;
		result = lhs + rhs;
		return true;
	}

	bool CheckedSub64(int64_t lhs, int64_t rhs, int64_t& result) noexcept
	{
		const auto min = std::numeric_limits<int64_t>::min();
		const auto max = std::numeric_limits<int64_t>::max();
		if ((rhs > 0 && lhs < min + rhs) || (rhs < 0 && lhs > max + rhs)) return false;
		result = lhs - rhs;
		return true;
	}

	bool CheckedMul64(int64_t lhs, int64_t rhs, int64_t& result) noexcept
	{
		const auto min = std::numeric_limits<int64_t>::min();
		const auto max = std::numeric_limits<int64_t>::max();
		if (lhs > 0) {
			if ((rhs > 0 && lhs > max / rhs) || (rhs <= 0 && rhs < min / lhs)) return false;
		} else if (lhs < 0) {
			if ((rhs > 0 && lhs < min / rhs) || (rhs <= 0 && rhs < max / lhs)) return false;
		}
		result = lhs * rhs;
		return true;
	}

	bool PlotCoordinate(int64_t value) noexcept
	{
		return value >= std::numeric_limits<int>::min() && value <= std::numeric_limits<int>::max();
	}

	size_t PlotPointLimit(const std::vector<BasePoint>& points) noexcept
	{
		// SDL_RenderDrawPoints consumes an int count.
		return std::min(points.max_size(), size_t(std::numeric_limits<int>::max()));
	}

	bool ReservePlotPoints(std::vector<BasePoint>& points, int64_t estimate)
	{
		if (estimate < 0) return false;
		// Reserve for the perimeter, rather than multiplying rectangle area.
		// This is a capacity estimate, not a diameter or output-size cap.
		const uint64_t count = std::min(uint64_t(estimate), uint64_t(PlotPointLimit(points)));
		points.reserve(size_t(count));
		return true;
	}

	bool AppendPlotPoint(std::vector<BasePoint>& points, int64_t x, int64_t y)
	{
		if (!PlotCoordinate(x) || !PlotCoordinate(y) || points.size() == PlotPointLimit(points)) return false;
		points.emplace_back(int(x), int(y));
		return true;
	}

}

static std::vector<BasePoint> PlotCircleImpl(const BasePoint& origin, int64_t r, uint8_t octants) noexcept
{
	// Uses the 2nd order Bresenham's Circle Algorithm.
	try {
		std::vector<BasePoint> points;
		if (!octants || r < 0) return points;
		int64_t reserveCount, twiceRadius;
		if (!CheckedAdd64(r, 1, reserveCount) || !CheckedMul64(8, reserveCount, reserveCount) ||
		    !CheckedMul64(2, r, twiceRadius)) return {};
		if (!ReservePlotPoints(points, reserveCount)) return {};

		auto GenOctants = [&origin, &points, octants](int64_t x, int64_t y) {
			auto Append = [&origin, &points](int64_t xOffset, int64_t yOffset) {
				int64_t x, y;
				return CheckedAdd64(origin.x, xOffset, x) &&
					CheckedAdd64(origin.y, yOffset, y) && AppendPlotPoint(points, x, y);
			};
			// Keep the original octant sequence, including coincident points.
			if ((octants & (1 << 0)) && !Append(y, x)) return false;
			if ((octants & (1 << 1)) && !Append(-y, x)) return false;
			if ((octants & (1 << 2)) && !Append(x, y)) return false;
			if ((octants & (1 << 3)) && !Append(-x, y)) return false;
			if ((octants & (1 << 4)) && !Append(x, -y)) return false;
			if ((octants & (1 << 5)) && !Append(-x, -y)) return false;
			if ((octants & (1 << 6)) && !Append(y, -x)) return false;
			if ((octants & (1 << 7)) && !Append(-y, -x)) return false;
			return true;
		};

		int64_t x = 0;
		int64_t y = r;
		int64_t fm, dse;
		int64_t de = 3;
		if (!CheckedSub64(1, r, fm) || !CheckedSub64(5, twiceRadius, dse)) return {};
		if (!GenOctants(x, y)) return {};

		while (x < y) {
			if (fm <= 0) {
				if (!CheckedAdd64(fm, de, fm)) return {};
			} else {
				if (!CheckedAdd64(fm, dse, fm) || !CheckedAdd64(dse, 2, dse) ||
				    !CheckedSub64(y, 1, y)) return {};
			}
			if (!CheckedAdd64(de, 2, de) || !CheckedAdd64(dse, 2, dse) ||
			    !CheckedAdd64(x, 1, x) || !GenOctants(x, y)) return {};
		}
		return points;
	} catch (const std::bad_alloc&) {
		return {};
	} catch (const std::length_error&) {
		return {};
	}
}

std::vector<BasePoint> PlotCircle(const BasePoint& origin, uint16_t r, uint8_t octants) noexcept
{
	return PlotCircleImpl(origin, r, octants);
}

std::vector<BasePoint> PlotEllipse(const Region& rect) noexcept
{
	if (rect.size.IsInvalid()) return {};
	try {
		// Avoid int overflow in Region::Maximum/Center before plotting starts.
		int64_t x1 = rect.x;
		int64_t y1 = rect.y;
		int64_t x2 = int64_t(rect.x) + rect.w - 1;
		int64_t y2 = int64_t(rect.y) + rect.h - 1;
		if (!PlotCoordinate(x2) || !PlotCoordinate(y2)) return {};

		if (rect.w == rect.h) {
			const int64_t radius = std::max<int64_t>(0, int64_t(rect.w) / 2 - 1);
			const int64_t centerX = int64_t(rect.x) + rect.w / 2;
			const int64_t centerY = int64_t(rect.y) + rect.h / 2;
			if (!PlotCoordinate(centerX) || !PlotCoordinate(centerY)) return {};
			return PlotCircleImpl(BasePoint(int(centerX), int(centerY)), radius, 0xff);
		}

		const int64_t a = int64_t(rect.w) - 1;
		const int64_t b = int64_t(rect.h) - 1;
		const int64_t parity = b & 1;
		int64_t aSquared, bSquared, dx, dy, err, parityError, aStep, bStep;
		if (!CheckedMul64(a, a, aSquared) || !CheckedMul64(b, b, bSquared) ||
		    !CheckedMul64(4, 1 - a, dx) || !CheckedMul64(dx, bSquared, dx) ||
		    !CheckedMul64(4, parity + 1, dy) || !CheckedMul64(dy, aSquared, dy) ||
		    !CheckedMul64(parity, aSquared, parityError) ||
		    !CheckedAdd64(dx, dy, err) || !CheckedAdd64(err, parityError, err) ||
		    !CheckedMul64(8, aSquared, aStep) || !CheckedMul64(8, bSquared, bStep) ||
		    !CheckedAdd64(y1, (b + 1) / 2, y1) || !CheckedSub64(y1, parity, y2)) return {};

		std::vector<BasePoint> points;
		int64_t reserveCount;
		if (!CheckedAdd64(rect.w, rect.h, reserveCount) ||
		    !CheckedMul64(4, reserveCount, reserveCount)) return {};
		if (!ReservePlotPoints(points, reserveCount)) return {};

		do {
			if (!AppendPlotPoint(points, x2, y1) || !AppendPlotPoint(points, x1, y1) ||
			    !AppendPlotPoint(points, x1, y2) || !AppendPlotPoint(points, x2, y2)) return {};

			int64_t e2;
			if (!CheckedMul64(2, err, e2)) return {};
			if (e2 <= dy) {
				if (!CheckedAdd64(y1, 1, y1) || !CheckedSub64(y2, 1, y2) ||
				    !CheckedAdd64(dy, aStep, dy) || !CheckedAdd64(err, dy, err)) return {};
			}
			bool stepX = e2 >= dx;
			if (!stepX) {
				int64_t updatedError;
				if (!CheckedMul64(2, err, updatedError)) return {};
				stepX = updatedError > dy;
			}
			if (stepX) {
				if (!CheckedAdd64(x1, 1, x1) || !CheckedSub64(x2, 1, x2) ||
				    !CheckedAdd64(dx, bStep, dx) || !CheckedAdd64(err, dx, err)) return {};
			}
		} while (x1 <= x2);

		for (;;) {
			int64_t span, left, right;
			if (!CheckedSub64(y1, y2, span)) return {};
			if (span >= b) break;
			if (!CheckedSub64(x1, 1, left) || !CheckedAdd64(x2, 1, right) ||
			    !AppendPlotPoint(points, left, y1) || !AppendPlotPoint(points, right, y1) ||
			    !AppendPlotPoint(points, left, y2) || !AppendPlotPoint(points, right, y2) ||
			    !CheckedAdd64(y1, 1, y1) || !CheckedSub64(y2, 1, y2)) return {};
		}
		return points;
	} catch (const std::bad_alloc&) {
		return {};
	} catch (const std::length_error&) {
		return {};
	}
}

}
