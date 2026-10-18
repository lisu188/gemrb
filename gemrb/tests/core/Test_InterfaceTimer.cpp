// SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
//
// SPDX-License-Identifier: GPL-2.0-or-later

// Match the supported demo/Interface configurations in Test_Map.cpp.
#if defined(USE_OPENGL_BACKEND) || (!defined(__APPLE__) && !defined(WIN32))

	#include "../../core/Interface.h"
	#include "../../core/InterfaceConfig.h"
	#include "../../core/PluginMgr.h"

	#include <array>
	#include <clocale>
	#include <gtest/gtest.h>

namespace GemRB {

class InterfaceTimerTest : public testing::Test {
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

protected:
	void SetUp() override { gemrb->timers.clear(); }
	void TearDown() override { gemrb->timers.clear(); }

	static Timer* AddTimer(const EventHandler& callback, tick_t delay, int repeats = 0)
	{
		return &gemrb->SetTimer(callback, delay, repeats);
	}

	static void Update(tick_t time) { gemrb->UpdateTimers(time); }

	static std::vector<Timer*> TimerAddresses()
	{
		std::vector<Timer*> addresses;
		for (auto& timer : gemrb->timers) addresses.push_back(&timer);
		return addresses;
	}
};

std::unique_ptr<Interface> InterfaceTimerTest::gemrb;

TEST_F(InterfaceTimerTest, RemovingMiddleTimerPreservesOwnerHandles)
{
	constexpr tick_t delay = 60000;
	std::array<int, 5> calls {};
	std::array<Timer*, 5> handles {};
	for (size_t i = 0; i < handles.size(); ++i) {
		handles[i] = AddTimer([&, i] { ++calls[i]; }, delay);
	}
	handles[2]->Invalidate();
	Update(0);

	// Check addresses before using retained handles: a deque middle erase can
	// move surviving timers, so a failed regression never dereferences them.
	ASSERT_EQ(TimerAddresses(), (std::vector<Timer*> { handles[0], handles[1], handles[3], handles[4] }));
	// TextArea/Control destruction must cancel the same timer they registered.
	handles[3]->Invalidate();
	Update(GetMilliseconds() + delay + 1);
	EXPECT_EQ(calls, (std::array<int, 5> { 1, 1, 0, 0, 1 }));
	Update(0);
	EXPECT_TRUE(TimerAddresses().empty());
}

TEST_F(InterfaceTimerTest, CallbackCanAppendTimersAndCancelPendingTimer)
{
	constexpr size_t appendedCount = 4096;
	constexpr tick_t delay = 60000;
	int firstCalls = 0;
	int cancelledCalls = 0;
	int tailCalls = 0;
	int appendedCalls = 0;
	Timer* cancelled = nullptr;
	std::vector<Timer*> appended;
	Timer* first = AddTimer([&] {
		++firstCalls;
		for (size_t i = 0; i < appendedCount; ++i) {
			appended.push_back(AddTimer([&] { ++appendedCalls; }, delay));
		}
		cancelled->Invalidate();
	},
				0);
	cancelled = AddTimer([&] { ++cancelledCalls; }, 0);
	Timer* tail = AddTimer([&] { ++tailCalls; }, 0);
	Update(GetMilliseconds());

	EXPECT_EQ(firstCalls, 1);
	EXPECT_EQ(cancelledCalls, 0);
	EXPECT_EQ(tailCalls, 1);
	EXPECT_EQ(appendedCalls, 0);
	std::vector<Timer*> expected { first, tail };
	expected.insert(expected.end(), appended.begin(), appended.end());
	ASSERT_EQ(TimerAddresses(), expected);
	Update(GetMilliseconds() + delay + 1);
	EXPECT_EQ(appendedCalls, appendedCount);
	Update(0);
	EXPECT_TRUE(TimerAddresses().empty());
}

TEST_F(InterfaceTimerTest, OneShotRepeatingAndCancelledTimersKeepTheirSemantics)
{
	int oneShotCalls = 0;
	int repeatedCalls = 0;
	int cancelledCalls = 0;
	AddTimer([&] { ++oneShotCalls; }, 0);
	AddTimer([&] { ++repeatedCalls; }, 0, 1);
	AddTimer([&] { ++cancelledCalls; }, 0)->Invalidate();
	Update(GetMilliseconds());
	EXPECT_EQ(oneShotCalls, 1);
	EXPECT_EQ(repeatedCalls, 1);
	EXPECT_EQ(cancelledCalls, 0);
	Update(GetMilliseconds());
	EXPECT_EQ(oneShotCalls, 1);
	EXPECT_EQ(repeatedCalls, 2);
	EXPECT_EQ(cancelledCalls, 0);
	Update(0);
	EXPECT_TRUE(TimerAddresses().empty());
}

}

#endif
