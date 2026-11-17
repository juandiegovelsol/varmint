//  SuperTux - rock behaviour scenario tests
//
//  This program is free software: you can redistribute it and/or modify
//  it under the terms of the GNU General Public License as published by
//  the Free Software Foundation, either version 3 of the License, or
//  (at your option) any later version.
//
//  This program is distributed in the hope that it will be useful,
//  but WITHOUT ANY WARRANTY; without even the implied warranty of
//  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
//  GNU General Public License for more details.

// Every test below loads a small level into a real Sector and runs the game's
// own update loop (64 logical frames per second, the same collision system the
// game uses). Tux is driven through his scripting controller, exactly like a
// level script would drive him. The tests only look at where things are and
// whether they still exist, never at how a rock or Tux is implemented.

#include <gtest/gtest.h>

#include <SDL.h>
#include <SDL_ttf.h>
#include <physfs.h>

#include <cmath>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include "audio/sound_manager.hpp"
#include "badguy/badguy.hpp"
#include "control/input_manager.hpp"
#include "object/coin.hpp"
#include "object/player.hpp"
#include "object/rock.hpp"
#include "squirrel/squirrel_virtual_machine.hpp"
#include "sprite/sprite_manager.hpp"
#include "supertux/gameconfig.hpp"
#include "supertux/globals.hpp"
#include "supertux/level.hpp"
#include "supertux/level_parser.hpp"
#include "supertux/resources.hpp"
#include "supertux/sector.hpp"
#include "supertux/tile.hpp"
#include "supertux/tile_manager.hpp"
#include "supertux/tile_set.hpp"
#include "video/ttf_surface_manager.hpp"
#include "video/video_system.hpp"

namespace {

const float FRAME = 1.0f / 64.0f;
const int LEVEL_W = 40;          // tiles
const int LEVEL_H = 15;          // tiles
const int FLOOR_ROW = 13;        // the floor's top is at y = 416
const float FLOOR_Y = 416.0f;
const float LEDGE_Y = 224.0f;    // ledge tiles on row 7, x tiles 1..8 (right end at x = 288)
const float LEDGE_END = 288.0f;

/** Brings up the subsystems the game itself starts before it plays a level
    (data files, a headless "null" video system, muted sound, scripting,
    tiles, sprites, fonts). */
class GameEnvironment : public ::testing::Environment
{
public:
  void SetUp() override
  {
    ASSERT_TRUE(PHYSFS_init(nullptr)) << "Could not initialize physfs";
    // The test binary runs from the repository root, so the shipped data/
    // directory can be mounted directly.
    ASSERT_TRUE(PHYSFS_mount("data", nullptr, 1)) << "Could not mount data/";
    ASSERT_EQ(0, SDL_Init(SDL_INIT_TIMER | SDL_INIT_VIDEO | SDL_INIT_JOYSTICK | SDL_INIT_GAMECONTROLLER))
      << SDL_GetError();
    ASSERT_EQ(0, TTF_Init());

    g_config = std::make_unique<Config>();
    m_input_manager = std::make_unique<InputManager>(g_config->keyboard_config, g_config->joystick_config);
    m_video_system = VideoSystem::create(VideoSystem::VIDEO_NULL);
    m_ttf_surface_manager = std::make_unique<TTFSurfaceManager>();
    m_sound_manager = std::make_unique<SoundManager>();
    m_sound_manager->enable_sound(false);
    m_sound_manager->enable_music(false);
    m_squirrel = std::make_unique<SquirrelVirtualMachine>(false);
    m_tile_manager = std::make_unique<TileManager>();
    m_sprite_manager = std::make_unique<SpriteManager>();
    m_resources = std::make_unique<Resources>();
  }

  void TearDown() override
  {
    m_resources.reset();
    m_sprite_manager.reset();
    m_tile_manager.reset();
    m_squirrel.reset();
    m_sound_manager.reset();
    m_ttf_surface_manager.reset();
    m_video_system.reset();
    m_input_manager.reset();
    g_config.reset();
    TTF_Quit();
    SDL_Quit();
    PHYSFS_deinit();
  }

private:
  std::unique_ptr<InputManager> m_input_manager;
  std::unique_ptr<VideoSystem> m_video_system;
  std::unique_ptr<TTFSurfaceManager> m_ttf_surface_manager;
  std::unique_ptr<SoundManager> m_sound_manager;
  std::unique_ptr<SquirrelVirtualMachine> m_squirrel;
  std::unique_ptr<TileManager> m_tile_manager;
  std::unique_ptr<SpriteManager> m_sprite_manager;
  std::unique_ptr<Resources> m_resources;
};

::testing::Environment* const g_game_environment =
  ::testing::AddGlobalTestEnvironment(new GameEnvironment());

/** A walled room with a solid floor and, optionally, a ledge in the upper
    left part of the room that ends in open air at x = 288. With a trench,
    two one-tile posts on the floor (x 256..288 and 352..384) fence in the
    floor right below the ledge's end. */
std::string room_tiles(bool ledge, bool trench = false)
{
  std::ostringstream out;
  for (int y = 0; y < LEVEL_H; ++y) {
    for (int x = 0; x < LEVEL_W; ++x) {
      const bool solid = y >= FLOOR_ROW || x == 0 || x == LEVEL_W - 1 ||
                         (ledge && y == 7 && x >= 1 && x <= 8) ||
                         (trench && y == FLOOR_ROW - 1 && (x == 8 || x == 11));
      out << (solid ? 48 : 0) << ' ';
    }
  }
  return out.str();
}

class Scene
{
public:
  Scene(const std::string& objects, float spawn_x, float spawn_y, bool ledge, bool trench = false) :
    m_level(),
    m_sector(nullptr),
    m_tux(nullptr)
  {
    std::ostringstream lvl;
    lvl << "(supertux-level (version 3) (name \"rock scene\") (author \"tests\") (license \"CC0\")"
        << " (sector (name \"main\") (ambient-light (color 1 1 1))"
        << " (spawnpoint (name \"main\") (x " << spawn_x << ") (y " << spawn_y << "))"
        << " (tilemap (solid #t) (z-pos 0) (width " << LEVEL_W << ") (height " << LEVEL_H << ")"
        << " (tiles " << room_tiles(ledge, trench) << "))"
        << " " << objects << "))";
    std::istringstream in(lvl.str());
    m_level = LevelParser::from_stream(in, "rock-scene", false, false);
    m_sector = m_level->get_sector(0);
    m_sector->activate("main");
    m_tux = &m_sector->get_player();
    m_tux->use_scripting_controller(true);
  }

  ~Scene()
  {
    m_sector->deactivate();
  }

  void step(int frames = 1)
  {
    for (int i = 0; i < frames; ++i)
      m_sector->update(FRAME);
  }

  void press(const std::string& control) { m_tux->do_scripting_controller(control, true); }
  void release(const std::string& control) { m_tux->do_scripting_controller(control, false); }

  Player& tux() { return *m_tux; }

  std::vector<Rock*> rocks()
  {
    std::vector<Rock*> out;
    for (auto& rock : m_sector->get_objects_by_type<Rock>())
      out.push_back(&rock);
    return out;
  }

  Rock* rock_near(float x)
  {
    Rock* best = nullptr;
    for (auto* rock : rocks())
      if (!best || std::abs(rock->get_bbox().get_middle().x - x) < std::abs(best->get_bbox().get_middle().x - x))
        best = rock;
    return best;
  }

  std::vector<BadGuy*> badguys()
  {
    std::vector<BadGuy*> out;
    for (auto& badguy : m_sector->get_objects_by_type<BadGuy>())
      out.push_back(&badguy);
    return out;
  }

  size_t coin_count()
  {
    size_t n = 0;
    for (auto& coin : m_sector->get_objects_by_type<Coin>()) { (void)coin; ++n; }
    return n;
  }

  /** Short taps on "right" so Tux creeps forward instead of sliding past
      the target (a ledge's end, for instance). */
  void creep_right_until(float right_edge)
  {
    for (int i = 0; i < 600 && m_tux->get_bbox().get_right() < right_edge; ++i) {
      press("right");
      step(2);
      release("right");
      step(10);
    }
    step(30);
  }

private:
  std::unique_ptr<Level> m_level;
  Sector* m_sector;
  Player* m_tux;
};

/** Tux picks up the rock lying on the ledge and stands at the ledge's end
    holding it, facing right, over the open air. */
void carry_rock_to_ledge_end(Scene& scene)
{
  scene.step(10);
  scene.press("action");
  scene.creep_right_until(LEDGE_END + 14.0f);
}

/** Frames until the rock's bottom first reaches the floor, or -1. */
int frames_until_on_floor(Scene& scene, Rock& rock, int max_frames)
{
  for (int i = 1; i <= max_frames; ++i) {
    scene.step();
    if (rock.get_bbox().get_bottom() >= FLOOR_Y - 1.0f)
      return i;
  }
  return -1;
}

/** Tux walks right (or left) holding a rock and lets go of it mid-stride. */
struct ThrowResult
{
  float release_x;     // rock centre right after it left Tux's hands
  float flight_x;      // rock centre a quarter of a second later
  float tux_x;         // Tux's centre when he let go
};

ThrowResult throw_while_walking(Scene& scene, const std::string& dir)
{
  scene.step(10);
  scene.press("action");
  scene.press(dir);
  scene.step(48);
  ThrowResult result;
  result.tux_x = scene.tux().get_bbox().get_middle().x;
  scene.release("action");
  scene.step(1);
  scene.release(dir);
  Rock* rock = scene.rocks().front();
  result.release_x = rock->get_bbox().get_middle().x;
  scene.step(16);
  result.flight_x = rock->get_bbox().get_middle().x;
  return result;
}

} // namespace

// ---------------------------------------------------------------------------
// Dropping a rock past coins
// ---------------------------------------------------------------------------

TEST(RockBehaviour, DroppedRockFallsPastCoinsLikeThroughOpenAir)
{
  // Same drop twice: once through open air, once through a column of coins
  // hanging under the ledge's end. The coins must not hold the rock up.
  int open_air = -1;
  {
    Scene scene("(rock (x 200) (y 192))", 96, 160, true);
    carry_rock_to_ledge_end(scene);
    ASSERT_EQ(1u, scene.rocks().size());
    scene.release("action");
    open_air = frames_until_on_floor(scene, *scene.rocks().front(), 256);
    ASSERT_GT(open_air, 0) << "the rock should reach the floor when nothing is in its way";
  }

  Scene scene("(rock (x 200) (y 192))"
              " (coin (x 306) (y 260)) (coin (x 306) (y 292)) (coin (x 306) (y 324))",
              96, 160, true);
  carry_rock_to_ledge_end(scene);
  Rock& rock = *scene.rocks().front();
  const size_t coins_before = scene.coin_count();
  scene.release("action");
  const int through_coins = frames_until_on_floor(scene, rock, 256);

  EXPECT_GT(through_coins, 0) << "the dropped rock never reached the floor below the coins";
  EXPECT_LE(through_coins, open_air + 2)
    << "the rock took " << through_coins << " frames to fall past the coins, but only "
    << open_air << " frames to fall the same distance through open air";
  EXPECT_EQ(coins_before, scene.coin_count()) << "a falling rock should not use up coins";
}

// ---------------------------------------------------------------------------
// Carrying
// ---------------------------------------------------------------------------

TEST(RockBehaviour, CarriedRockIsHeldInFrontOfTux)
{
  Scene scene("(rock (x 200) (y 384))", 96, 352, false);
  scene.step(10);
  scene.press("action");
  scene.press("right");
  scene.step(40);
  ASSERT_EQ(1u, scene.rocks().size());
  Rock& rock = *scene.rocks().front();

  for (int i = 0; i < 4; ++i) {
    scene.step(8);
    EXPECT_GT(rock.get_bbox().get_middle().x, scene.tux().get_bbox().get_middle().x)
      << "walking right: the rock (centre x " << rock.get_bbox().get_middle().x
      << ") should be in front of Tux (centre x " << scene.tux().get_bbox().get_middle().x << ")";
  }

  scene.release("right");
  scene.press("left");
  scene.step(24);
  for (int i = 0; i < 4; ++i) {
    scene.step(8);
    EXPECT_LT(rock.get_bbox().get_middle().x, scene.tux().get_bbox().get_middle().x)
      << "walking left: the rock (centre x " << rock.get_bbox().get_middle().x
      << ") should be in front of Tux (centre x " << scene.tux().get_bbox().get_middle().x << ")";
  }
  scene.release("left");
  scene.release("action");
}

TEST(RockBehaviour, CarriedRockMovesAlongWithTux)
{
  Scene scene("(rock (x 200) (y 384))", 96, 352, false);
  scene.step(10);
  scene.press("action");
  scene.press("right");
  scene.step(40);
  Rock& rock = *scene.rocks().front();
  const float start = rock.get_bbox().get_middle().x;
  scene.step(40);
  EXPECT_GT(rock.get_bbox().get_middle().x - start, 64.0f) << "the carried rock should travel with Tux";
  EXPECT_LT(std::abs(rock.get_bbox().get_middle().x - scene.tux().get_bbox().get_middle().x), 48.0f);
  EXPECT_LT(rock.get_bbox().get_bottom(), FLOOR_Y) << "the carried rock is lifted off the floor";
  scene.release("right");
  scene.release("action");
}

// ---------------------------------------------------------------------------
// Throwing
// ---------------------------------------------------------------------------

TEST(RockBehaviour, RockThrownWhileWalkingFliesForward)
{
  {
    Scene scene("(rock (x 200) (y 384))", 96, 352, false);
    const ThrowResult r = throw_while_walking(scene, "right");
    EXPECT_GT(r.flight_x - r.release_x, 16.0f)
      << "thrown while walking right, the rock moved from x " << r.release_x << " to " << r.flight_x;
  }
  {
    Scene scene("(rock (x 800) (y 384))", 900, 352, false);
    const ThrowResult r = throw_while_walking(scene, "left");
    EXPECT_LT(r.flight_x - r.release_x, -16.0f)
      << "thrown while walking left, the rock moved from x " << r.release_x << " to " << r.flight_x;
  }
}

TEST(RockBehaviour, ThrownRockLandsAndStaysOnTheGround)
{
  for (const std::string dir : {"right", "left"}) {
    Scene scene(dir == "right" ? "(rock (x 200) (y 384))" : "(rock (x 800) (y 384))",
                dir == "right" ? 96 : 900, 352, false);
    throw_while_walking(scene, dir);
    Rock& rock = *scene.rocks().front();
    scene.step(128);
    const Rectf before = rock.get_bbox();
    scene.step(64);
    EXPECT_NEAR(FLOOR_Y, rock.get_bbox().get_bottom(), 2.0f)
      << "thrown " << dir << ": two seconds later the rock should lie on the floor, its bottom is at y "
      << rock.get_bbox().get_bottom();
    EXPECT_NEAR(before.get_top(), rock.get_bbox().get_top(), 1.0f) << "thrown " << dir << ": the landed rock keeps still";
    EXPECT_NEAR(before.get_left(), rock.get_bbox().get_left(), 1.0f) << "thrown " << dir << ": the landed rock keeps still";
  }
}

TEST(RockBehaviour, PutDownRockLandsOnTheGround)
{
  Scene scene("(rock (x 200) (y 192))", 96, 160, true);
  carry_rock_to_ledge_end(scene);
  scene.release("action");
  Rock& rock = *scene.rocks().front();
  scene.step(128);
  EXPECT_NEAR(FLOOR_Y, rock.get_bbox().get_bottom(), 2.0f);
}

// ---------------------------------------------------------------------------
// A rock lying on the ground is solid
// ---------------------------------------------------------------------------

TEST(RockBehaviour, TuxCanStandOnARestingRock)
{
  Scene scene("(rock (x 320) (y 384))", 320, 160, false);
  scene.step(128);
  Rock& rock = *scene.rocks().front();
  EXPECT_NEAR(rock.get_bbox().get_top(), scene.tux().get_bbox().get_bottom(), 2.0f)
    << "Tux fell onto the rock and should be standing on top of it (rock top y " << rock.get_bbox().get_top()
    << ", Tux bottom y " << scene.tux().get_bbox().get_bottom() << ")";
  scene.step(64);
  EXPECT_NEAR(rock.get_bbox().get_top(), scene.tux().get_bbox().get_bottom(), 2.0f) << "and keep standing there";
  EXPECT_NEAR(FLOOR_Y, rock.get_bbox().get_bottom(), 2.0f) << "the rock itself stays on the floor";
}

TEST(RockBehaviour, TuxWalkingIntoARestingRockIsStoppedByIt)
{
  Scene scene("(rock (x 320) (y 384))", 160, 352, false);
  scene.step(30);
  scene.press("right");
  scene.step(128);
  Rock& rock = *scene.rocks().front();
  EXPECT_LE(scene.tux().get_bbox().get_right(), rock.get_bbox().get_left() + 2.0f)
    << "Tux walked into the rock without picking it up; he should be stopped by it (Tux right x "
    << scene.tux().get_bbox().get_right() << ", rock left x " << rock.get_bbox().get_left() << ")";
  EXPECT_NEAR(FLOOR_Y, scene.tux().get_bbox().get_bottom(), 2.0f);
  scene.release("right");
}

TEST(RockBehaviour, RockDroppedOnARestingRockStaysOnTop)
{
  Scene scene("(rock (x 320) (y 384)) (rock (x 322) (y 100))", 96, 352, false);
  scene.step(192);
  Rock* lower = nullptr;
  Rock* upper = nullptr;
  for (auto* rock : scene.rocks()) {
    if (!lower || rock->get_bbox().get_top() > lower->get_bbox().get_top()) { upper = lower; lower = rock; }
    else upper = rock;
  }
  ASSERT_NE(nullptr, upper);
  EXPECT_NEAR(FLOOR_Y, lower->get_bbox().get_bottom(), 2.0f);
  EXPECT_NEAR(lower->get_bbox().get_top(), upper->get_bbox().get_bottom(), 2.0f)
    << "the dropped rock should rest on top of the other one";
}

// ---------------------------------------------------------------------------
// A rock falling on an enemy
// ---------------------------------------------------------------------------

TEST(RockBehaviour, RockDroppedOnAWalkingLeafKnocksItOut)
{
  // The leaf paces back and forth in a two-tile trench right below the ledge's
  // end, so wherever in that trench it is, the dropped rock comes down on it.
  Scene scene("(rock (x 200) (y 192)) (walkingleaf (x 304) (y 384) (direction \"left\"))", 96, 160, true, true);
  carry_rock_to_ledge_end(scene);
  ASSERT_EQ(1u, scene.badguys().size());
  const Rectf leaf_box = scene.badguys().front()->get_bbox();
  ASSERT_GE(leaf_box.get_left(), LEDGE_END - 1.0f) << "setup: the leaf should be pacing in the trench";
  ASSERT_LE(leaf_box.get_right(), LEDGE_END + 65.0f) << "setup: the leaf should be pacing in the trench";
  scene.release("action");
  scene.step(64 * 4);

  bool leaf_still_there = false;
  for (auto* badguy : scene.badguys())
    if (badguy->get_bbox().get_top() < FLOOR_Y)
      leaf_still_there = true;
  EXPECT_FALSE(leaf_still_there)
    << "four seconds after the rock fell on the walking leaf, the leaf is still standing in the room";
}

/* EOF */
