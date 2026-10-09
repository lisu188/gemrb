// SPDX-FileCopyrightText: 2024 Contributors to the GemRB project <https://gemrb.org>
//
// SPDX-License-Identifier: GPL-2.0-or-later

// FIXME: remove once fixed, this is excluding non-linux build bots
#if defined(USE_OPENGL_BACKEND) || (!defined(__APPLE__) && !defined(WIN32))

	#include "../../core/GameData.h"
	#include "../../core/Interface.h"
	#include "../../core/InterfaceConfig.h"
	#include "../../core/Logging/Loggers/Stdio.h"
	#include "../../core/Logging/Logging.h"
	#include "../../core/Map.h"
	#include "../../core/PluginMgr.h"
	#include "../../core/SaveGameMgr.h"
	#include "../../core/Scriptable/Actor.h"

	#include <algorithm>
	#include <gtest/gtest.h>

namespace GemRB {

class MapTest : public testing::Test {
public:
	static std::unique_ptr<Interface> gemrb;
	static Map* map;

	// set up core and the first map from the demo
	static void SetUpTestSuite()
	{
		setlocale(LC_ALL, "");
		const char* argv[] = { "tester", "-c", "../../tester.cfg" };
		auto cfg = LoadFromArgs(3, const_cast<char**>(argv));
		// Demo class/kit tables are empty placeholders. Queue tests need valid
		// zero-row tables to construct actors, but do not exercise class rules.
		cfg.ModPath.emplace_back("tests/resources/map_queue");
		ToggleLogging(true);
		SetMainLogLevel(DEBUG);
		AddLogWriter(createStdioLogWriter());
		gemrb = std::make_unique<Interface>(std::move(cfg));

		auto gamStream = gamedata->GetResourceStream("gem-demo", IE_GAM_CLASS_ID);
		auto gamMgr = GetImporter<SaveGameMgr>(IE_GAM_CLASS_ID, gamStream);
		auto gam = gamMgr->LoadGame(std::make_unique<Game>(), GAMVersion::GemRB);
		core->SetGame(std::move(gam));
		Game* game = core->GetGame();

		ResRef mapRef { "ar0100" };
		map = game->GetMap(mapRef, false);
	}

	static void TearDownTestSuite()
	{
		// cleanup to prevent a delay and crash on exit
		core->SetGame(nullptr);
		VideoDriver.reset();
		gemrb.reset();
		// Later filesystem tests consult this non-owning engine observer.
		core = nullptr;
		PluginMgr::Get()->RunCleanup();
	}

protected:
	std::vector<std::unique_ptr<Actor>> testActors;
	std::vector<Actor*> savedQueues[int(Priority::Ignore)];

	void SetUp() override
	{
		for (int i = 0; i < int(Priority::Ignore); ++i) savedQueues[i] = map->queue[i];
	}

	void TearDown() override
	{
		for (const auto& actor : testActors) {
			if (actor && map->HasActor(actor.get())) map->RemoveActor(actor.get());
		}
		for (int i = 0; i < int(Priority::Ignore); ++i) map->queue[i] = std::move(savedQueues[i]);
		testActors.clear();
	}

	Actor* AddTestActor(int y)
	{
		auto actor = std::make_unique<Actor>();
		actor->Pos = Point(1126, y);
		map->AddActor(actor.get(), false);
		// Establish membership without applying gameplay equipment/feat effects.
		actor->Scriptable::SetMap(map);
		testActors.push_back(std::move(actor));
		return testActors.back().get();
	}

	void DeleteTestActor(Actor* actor)
	{
		for (auto& owned : testActors) {
			if (owned.get() == actor) owned.release();
		}
		auto it = std::find(map->actors.begin(), map->actors.end(), actor);
		ASSERT_NE(it, map->actors.end());
		map->DeleteActor(size_t(it - map->actors.begin()));
	}

	static void SetQueues(std::vector<Actor*> run, std::vector<Actor*> display)
	{
		map->queue[int(Priority::RunScripts)] = std::move(run);
		map->queue[int(Priority::Display)] = std::move(display);
	}

	static size_t QueueSize(Priority priority) { return map->queue[int(priority)].size(); }
	static Actor* NextActor(int& priority, size_t& index) { return map->GetNextActor(priority, index); }
	static void SortQueues() { map->SortQueues(); }

	static std::vector<Actor*> DrawableActors()
	{
		int priority = int(Priority::Display);
		size_t index = QueueSize(Priority::Display);
		std::vector<Actor*> result;
		while (Actor* actor = NextActor(priority, index)) result.push_back(actor);
		return result;
	}
};

Map* MapTest::map = nullptr;
std::unique_ptr<Interface> MapTest::gemrb = nullptr;

TEST_F(MapTest, RemovedActorsAreNotDrawnWithoutAnUpdate)
{
	Actor* running = AddTestActor(601);
	Actor* removedRunning = AddTestActor(610);
	Actor* displayed = AddTestActor(620);
	Actor* removedDisplayed = AddTestActor(630);
	SetQueues({ running, removedRunning }, { displayed, removedDisplayed });

	map->RemoveActor(removedRunning);
	map->RemoveActor(removedDisplayed);

	// Paused gameplay still draws, without UpdateScripts regenerating queues.
	EXPECT_EQ(DrawableActors(), (std::vector<Actor*> { displayed, running }));
	EXPECT_EQ(QueueSize(Priority::RunScripts), 2);
	EXPECT_EQ(QueueSize(Priority::Display), 2);
	EXPECT_EQ(removedRunning->GetCurrentArea(), nullptr);
	EXPECT_EQ(removedDisplayed->GetCurrentArea(), nullptr);
}

TEST_F(MapTest, DeletedActorIsNotReturnedByDrawingQueue)
{
	Actor* survivor = AddTestActor(601);
	Actor* removed = AddTestActor(610);
	SetQueues({ survivor }, { removed });

	DeleteTestActor(removed);

	EXPECT_EQ(DrawableActors(), (std::vector<Actor*> { survivor }));
}

TEST_F(MapTest, RemovingActorsPreservesActiveQueueTraversal)
{
	Actor* low = AddTestActor(601);
	Actor* middle = AddTestActor(610);
	Actor* high = AddTestActor(620);
	Actor* displayed = AddTestActor(630);
	SetQueues({ low, middle, high }, { displayed });
	int priority = int(Priority::Display);
	size_t index = QueueSize(Priority::Display);
	ASSERT_EQ(NextActor(priority, index), displayed);
	ASSERT_EQ(NextActor(priority, index), high);

	// A script can remove both the current actor and an actor still to visit.
	map->RemoveActor(high);
	map->RemoveActor(low);
	map->RemoveActor(displayed);
	EXPECT_EQ(NextActor(priority, index), middle);
	EXPECT_EQ(NextActor(priority, index), nullptr);
	EXPECT_EQ(NextActor(priority, index), nullptr);

	SortQueues();
	EXPECT_EQ(QueueSize(Priority::RunScripts), 1);
	EXPECT_EQ(QueueSize(Priority::Display), 0);
	EXPECT_EQ(DrawableActors(), (std::vector<Actor*> { middle }));
}

static Point badPaths[] = { Point(1270, 640), Point(1071, 699), Point(1170, 967), Point(1126, 601) };
static Point goodPaths[] = { Point(1126, 601), Point(685, 655), Point(720, 496), Point(1056, 336) };
static SearchmapPoint badPaths2[] = { SearchmapPoint(badPaths[0]), SearchmapPoint(badPaths[1]), SearchmapPoint(badPaths[2]), SearchmapPoint(badPaths[3]) };
static SearchmapPoint goodPaths2[] = { SearchmapPoint(goodPaths[0]), SearchmapPoint(goodPaths[1]), SearchmapPoint(goodPaths[2]), SearchmapPoint(goodPaths[3]) };

TEST_F(MapTest, GetBlockedInLineTest1)
{
	// same point
	EXPECT_TRUE(map->IsVisibleLOS(badPaths[0], badPaths[0], nullptr));

	// random points
	for (int i = 0; i < 3; i++) {
		EXPECT_FALSE(map->IsVisibleLOS(badPaths[i], badPaths[i + 1], nullptr)) << "i: " << i << std::endl;

		EXPECT_TRUE(map->IsVisibleLOS(goodPaths[i], goodPaths[i + 1], nullptr)) << "i: " << i << std::endl;
	}
}

TEST_F(MapTest, GetBlockedInLineTileTest1)
{
	// same point
	EXPECT_TRUE(map->IsVisibleLOS(badPaths2[0], badPaths2[0], nullptr));

	// random points
	for (int i = 0; i < 3; i++) {
		EXPECT_FALSE(map->IsVisibleLOS(badPaths2[i], badPaths2[i + 1], nullptr)) << "i: " << i << std::endl;

		EXPECT_TRUE(map->IsVisibleLOS(goodPaths2[i], goodPaths2[i + 1], nullptr)) << "i: " << i << std::endl;
	}
}

// test GetBlockedInLineTile == GetBlockedInLine
TEST_F(MapTest, GetBlockedInLineTestDouble)
{
	// same point
	EXPECT_TRUE(map->IsVisibleLOS(badPaths[0], badPaths[0], nullptr));

	// random points
	for (int i = 0; i < 3; i++) {
		EXPECT_EQ(map->IsVisibleLOS(badPaths[i], badPaths[i + 1], nullptr),
			  map->IsVisibleLOS(badPaths2[i], badPaths2[i + 1], nullptr))
			<< "i: " << i << std::endl;

		EXPECT_EQ(map->IsVisibleLOS(goodPaths[i], goodPaths[i + 1], nullptr),
			  map->IsVisibleLOS(goodPaths2[i], goodPaths2[i + 1], nullptr))
			<< "i: " << i << std::endl;
	}
}

TEST_F(MapTest, FindPathTest)
{
	// straight path
	constexpr int circleSize = 2;
	auto path = map->FindPath(goodPaths[0], goodPaths[1], circleSize);
	EXPECT_TRUE(path);
	EXPECT_EQ(path.Size(), 1);

	// curvy path
	path = map->FindPath(badPaths[0], badPaths[1], circleSize);
	EXPECT_TRUE(path);
	EXPECT_EQ(path.Size(), 3);

	// ... is exactly what we expect
	EXPECT_EQ(path.GetStep(0).point, Point(1222, 700));
	EXPECT_EQ(path.GetStep(1).point, Point(1110, 712));
	EXPECT_EQ(path.GetStep(2).point, Point(1062, 700)); // not exactly badPaths[1]!

	// basic determinism
	auto path2 = map->FindPath(badPaths[0], badPaths[1], circleSize);
	EXPECT_TRUE(path2);
	EXPECT_EQ(path2.Size(), 3);
	for (int i = 0; i < 3; i++) {
		EXPECT_EQ(path.GetStep(i).point, path2.GetStep(i).point);
	}

	// close obstacle: don't try to tunnel through monolith
	path = map->FindPath(Point(1217, 690), Point(1111, 715), circleSize);
	EXPECT_TRUE(path);
	EXPECT_GT(path.Size(), 1);
}
}
#endif
