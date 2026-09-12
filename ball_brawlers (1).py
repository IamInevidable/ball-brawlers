"""
Ball Brawlers - single-file merge of main.py, skills.py, combat.py,
stats.py, and enemy_config.py.

Module order preserved from the original dependency chain:
  stats.py -> combat.py -> enemy_config.py -> skills.py -> main.py

Run with:  python ball_brawlers.py
Requires:  pip install pygame
"""

import copy
import math
import random
import sys
from dataclasses import dataclass, field
from typing import List

import pygame


# ===========================================================================
# stats.py
# ===========================================================================
@dataclass
class Stats:
    """Notes on units:
      - crit_rate: percent chance to crit (0 = never).
      - crit_damage: percent bonus damage on a crit (100 = double damage).
      - defence: flat damage reduction, subtracted from incoming hits.
      - attack_speed: base 10 -> baseline sword spin speed; higher spins faster.
      - special_damage: multiplier applied to attacks tagged "special".
      - skill_speed: percent, base 100 -> normal cast/cooldown speed.
      - dodge_chance / hp_regen: no explicit starting value was specified,
        defaulted to 0 until they're tuned.
      - gray_token_percent: 100 means a guaranteed gray-token pickup;
        values above 100 add a chance for an extra token.
    """
    hp: float = 100
    max_hp: float = 100
    move_speed: float = 20
    attack: float = 5
    defence: float = 0
    hp_regen: float = 0
    crit_rate: float = 0
    crit_damage: float = 100
    special_damage: float = 1
    attack_speed: float = 30
    skill_speed: float = 100
    coin_count: int = 10
    dodge_chance: float = 0
    gray_tokens: int = 0
    gray_token_percent: float = 100
    blue_tokens: int = 0
    blue_token_percent: float = 100
    contact_damage_percent: float = 0
    body_slam_enabled: bool = False
    body_slam_damage_percent: float = 40
    body_slam_extra_impacts: int = 0
    head_hitter_chance: float = 20
    lingering_poison_enabled: bool = False
    shuriken_mastery: int = 0
    mini_shurikens_enabled: bool = False
    shuriken_split_count: int = 2
    rage_level: int = 0
    # Percent bonuses applied to every pet a player owns (see the Pet
    # class and PET POWER! card) - read live off the owner's stats each
    # frame rather than baked into any one pet, so buying more copies of
    # the card buffs pets that already exist.
    pet_speed_percent: float = 0
    pet_attack_percent: float = 0


# ===========================================================================
# combat.py
# ===========================================================================
"""
Shared damage math. Anything that hits anything else - the player's sword
against an enemy, an enemy's contact damage against the player, future
skills, etc - should route through calculate_damage() so crit, defence,
dodge, and special-damage tags all behave consistently everywhere.
"""

def calculate_damage(attacker_stats, defender_stats, tags=None):
    """Returns (damage_dealt, was_crit, was_dodged).

    - Dodge is checked first: a successful dodge means 0 damage.
    - "special" in tags multiplies the base attack by attacker's special_damage.
    - Crit chance/damage come from the attacker's stats.
    - Defence is a flat subtraction, floored at 0 damage.
    """
    tags = tags or []

    if random.uniform(0, 100) < defender_stats.dodge_chance:
        return 0.0, False, True

    damage = attacker_stats.attack
    if "special" in tags:
        damage *= attacker_stats.special_damage

    is_crit = random.uniform(0, 100) < attacker_stats.crit_rate
    if is_crit:
        damage *= (1 + attacker_stats.crit_damage / 100)

    damage = max(0.0, damage - defender_stats.defence)
    return damage, is_crit, False


# ===========================================================================
# enemy_config.py
# ===========================================================================
"""
ENEMY CONFIG SHEET
==================
One EnemyConfig per enemy type: its stats, its look, which skills it uses
(see skills.py), and its spawn rule (see SpawnRule below). Add a new enemy
by building a new EnemyConfig and adding it to ENEMY_CONFIGS.
"""

@dataclass
class SpawnRule:
    """Governs when and how many of an enemy type spawn each wave."""
    start_wave: int              # first wave this enemy type is eligible
    min_per_wave: float          # minimum spawned per eligible wave
    max_per_wave: float          # spawn cap per eligible wave
    hp_increase_amount: float = 0        # flat hp added...
    hp_increase_interval_waves: int = 5  # ...every N waves active
    attack_increase_amount: float = 0
    attack_increase_interval_waves: int = 0
    min_growth_per_interval: float = 0
    max_growth_per_interval: float = 0

    def hp_bonus_for_wave(self, wave_number):
        if wave_number < self.start_wave or self.hp_increase_interval_waves <= 0:
            return 0
        waves_active = wave_number - self.start_wave
        steps = waves_active // self.hp_increase_interval_waves
        return steps * self.hp_increase_amount

    def count_for_wave(self, wave_number, rng):
        if wave_number < self.start_wave:
            return 0
        intervals = (wave_number - self.start_wave) // 2
        minimum = self.min_per_wave + intervals * self.min_growth_per_interval
        maximum = self.max_per_wave + intervals * self.max_growth_per_interval
        return rng.randint(math.ceil(minimum), math.floor(maximum))

    def attack_bonus_for_wave(self, wave_number):
        if (wave_number < self.start_wave
                or self.attack_increase_interval_waves <= 0):
            return 0
        waves_active = wave_number - self.start_wave
        steps = waves_active // self.attack_increase_interval_waves
        return steps * self.attack_increase_amount


@dataclass
class EnemyConfig:
    key: str
    display_name: str
    base_stats: Stats
    radius: float
    base_color: tuple
    outline_color: tuple
    spawn_rule: SpawnRule
    skills: List[str] = field(default_factory=list)
    gray_token_percent: float = 10
    # "graphic nuisance": visually grows and darkens toward base_color as
    # current hp rises toward max, and shrinks/pales as it takes damage.
    graphic_nuisance: bool = False
    miniboss: bool = False
    blue_token_drop_count: int = 1
    # True for the "wave boss" pool: rare, player-build-mimicking enemies
    # that get their own cinematic entrance (see WAVE_BOSS_CONFIGS below).
    wave_boss: bool = False


# ---------------------------------------------------------------------------
# PETS
# ---------------------------------------------------------------------------
# Tag carried by every persistent player ally (see the Pet class further
# down). Anything can check `entity.has_tag(TAG_PET)` - nothing currently
# branches on it, but it's there for future cards/skills that care whether
# something is a pet specifically (as opposed to a shuriken summon, etc).
TAG_PET = "pet"


@dataclass
class PetConfig:
    """A persistent player ally, granted by a card rather than spawned by
    the wave-based SpawnManager. `player.pet_grants` records how many of
    a given PetConfig a player has been granted; `respawn_pets` tops that
    count back up at the start of every wave (and immediately when the
    granting card is bought), so losing a pet mid-wave isn't permanent."""
    key: str
    display_name: str
    base_stats: Stats
    radius: float
    base_color: tuple
    outline_color: tuple
    tags: tuple = (TAG_PET,)


GREEN_PIP = EnemyConfig(
    key="green_pip",
    display_name="Green Pip",
    base_stats=Stats(
        hp=4,
        max_hp=4,
        move_speed=11,
        attack=2,
        defence=0,
        hp_regen=0,
        crit_rate=0,
        coin_count=4,
        gray_token_percent=30,
        blue_token_percent=20,
    ),
    radius=14,                     # smaller than the player's 22
    base_color=(150, 220, 40),     # lime
    outline_color=(70, 110, 15),
    spawn_rule=SpawnRule(
        start_wave=1,
        min_per_wave=12,
        max_per_wave=15,
        hp_increase_amount=8,
        hp_increase_interval_waves=5,
    ),
    skills=["contact_damage", "eye_of_sight"],
    graphic_nuisance=True,
)

GREEN_O_PIP_STATS = copy.deepcopy(GREEN_PIP.base_stats)
GREEN_O_PIP_STATS.hp *= 10
GREEN_O_PIP_STATS.max_hp *= 10
GREEN_O_PIP_STATS.move_speed *= 0.7
GREEN_O_PIP_STATS.blue_token_percent = 100

GREEN_O_PIPPAH = EnemyConfig(
    key="green_o_pippah",
    display_name="Green-o-Pippah",
    base_stats=GREEN_O_PIP_STATS,
    radius=GREEN_PIP.radius * 3,
    base_color=tuple(max(0, int(channel * 0.55)) for channel in GREEN_PIP.base_color),
    outline_color=(20, 55, 20),
    spawn_rule=SpawnRule(start_wave=1, min_per_wave=1, max_per_wave=1),
    skills=["contact_damage", "eye_of_sight", "body_slam"],
    gray_token_percent=GREEN_PIP.gray_token_percent,
    miniboss=True,
    blue_token_drop_count=3,
)

YELLOW_PIP = EnemyConfig(
    key="yellow_pip",
    display_name="Yellow Pip",
    base_stats=Stats(
        hp=1,
        max_hp=1,
        move_speed=16,
        attack=4,
        defence=0,
        hp_regen=0,
        crit_rate=0,
        coin_count=2,
        gray_token_percent=30,
        blue_token_percent=20,
    ),
    radius=9,
    base_color=(245, 220, 45),
    outline_color=(145, 115, 10),
    spawn_rule=SpawnRule(
        start_wave=1,
        min_per_wave=2,
        max_per_wave=4,
        attack_increase_amount=3,
        attack_increase_interval_waves=4,
        min_growth_per_interval=0.5,
        max_growth_per_interval=0.6,
    ),
    skills=["contact_damage", "eye_of_sight", "self_annihilating"],
    graphic_nuisance=False,
)

# Same stat block as Yellow Pip, just 0.4x move speed - she hangs back and
# lets the aura do the work instead of rushing in.
FLAGBEARER_PIPPA_STATS = copy.deepcopy(YELLOW_PIP.base_stats)
FLAGBEARER_PIPPA_STATS.move_speed *= 0.4

FLAGBEARER_PIPPA = EnemyConfig(
    key="flagbearer_pippa",
    display_name="Flagbearer Pippa",
    base_stats=FLAGBEARER_PIPPA_STATS,
    radius=GREEN_PIP.radius,           # same size as a Green Pip
    base_color=(210, 225, 245),        # pale flag-blue
    outline_color=(70, 90, 130),
    spawn_rule=SpawnRule(start_wave=1, min_per_wave=1, max_per_wave=1),
    # Same kit as Yellow Pip, but Eye of Sight -> Eye of Avoidance (she
    # keeps her distance instead of charging in), plus her aura skill.
    skills=["contact_damage", "self_annihilating", "eye_of_avoidance", "flagbearer"],
    miniboss=True,
    blue_token_drop_count=2,
)

# ---------------------------------------------------------------------------
# WAVE BOSSES
# ---------------------------------------------------------------------------
# A separate pool from MINIBOSS_CONFIGS. Every WAVE_BOSS_INTERVAL waves
# (see main.py), the spawn manager rolls one random entry from this list
# and gives it its own boss-intro cinematic instead of trickling it into
# the normal spawn queue. Each one is built to feel like a real player
# build - same cards, same stat block shape - just wearing an enemy's
# skin, so keep new entries stocked with actual player skills/cards
# rather than one-off stats.

WRESLER_KAI_STATS = Stats(
    hp=300,
    max_hp=300,
    move_speed=10,
    attack=6,
    defence=6,
    hp_regen=0.1,
    crit_rate=0,
    coin_count=50,
    dodge_chance=20,
    gray_token_percent=0,        # no gray-card build here, just blue skills
    blue_token_percent=100,      # guaranteed blue-token drop
    # --- the "build", card for card ---
    contact_damage_percent=40 + 4 * 5,   # Contact Bump (40) + Bump Up x4 (+5 ea) = 60
    body_slam_enabled=True,              # Body Slam
    body_slam_extra_impacts=2,           # Reslamming x2 (+1 ea)
    rage_level=4,                        # Head Hitter, maxed at 4 purchases
)

WRESLER_KAI = EnemyConfig(
    key="wresler_kai",
    display_name="Wresler Kai",
    base_stats=WRESLER_KAI_STATS,
    radius=35.2,                  # 1.6x the player ball's 22px radius
    base_color=(150, 60, 200),    # purple
    outline_color=(65, 20, 95),
    spawn_rule=SpawnRule(
        start_wave=3,
        min_per_wave=1,
        max_per_wave=1,
        # Wave bosses repeat (see WAVE_BOSS_INTERVAL in main.py) and get a
        # little tougher each time they come back around.
        hp_increase_amount=40,
        hp_increase_interval_waves=3,
        attack_increase_amount=2,
        attack_increase_interval_waves=3,
    ),
    skills=["eye_of_sight", "contact_damage", "body_slam", "head_hitter", "bounty_bump"],
    blue_token_drop_count=5,
    wave_boss=True,
)

# Every enemy type currently in the game. The spawn manager walks this
# list each wave and rolls a count for anyone whose start_wave has arrived.
ENEMY_CONFIGS = [GREEN_PIP, YELLOW_PIP]
MINIBOSS_CONFIGS = [GREEN_O_PIPPAH, FLAGBEARER_PIPPA]

# The randomized wave-boss pool. Add future wrestlers/mimics here - the
# spawn manager will start rolling them in automatically.
WAVE_BOSS_CONFIGS = [WRESLER_KAI]


# ---------------------------------------------------------------------------
# PET CONFIGS
# ---------------------------------------------------------------------------
# Green Pip Pup: a Green Pip that fights for the player instead of against
# them. Same base stat block as GREEN_PIP, plus the pup's own bonuses.
GREEN_PIP_PUP_STATS = copy.deepcopy(GREEN_PIP.base_stats)
GREEN_PIP_PUP_STATS.defence += 100
GREEN_PIP_PUP_STATS.max_hp += 500
GREEN_PIP_PUP_STATS.hp = GREEN_PIP_PUP_STATS.max_hp
GREEN_PIP_PUP_STATS.move_speed *= 0.8
GREEN_PIP_PUP_STATS.attack += 4

GREEN_PIP_PUP_CONFIG = PetConfig(
    key="green_pip_pup",
    display_name="Green Pip Pup",
    base_stats=GREEN_PIP_PUP_STATS,
    radius=GREEN_PIP.radius,
    base_color=GREEN_PIP.base_color,
    outline_color=GREEN_PIP.outline_color,
)

# key -> PetConfig, looked up by respawn_pets() from a player's pet_grants.
PET_CONFIGS = {
    GREEN_PIP_PUP_CONFIG.key: GREEN_PIP_PUP_CONFIG,
}


# ===========================================================================
# skills.py
# ===========================================================================
"""
SKILL SHEET
===========
Central registry of enemy skills. This is the single place to add, tweak,
or retire a skill.

To turn a skill on for an enemy: add its `name` string to that enemy's
`skills` list in enemy_config.py.
To turn it off: remove it from that list. Nothing else to touch.

Each skill is a small class with two hooks:
  - on_spawn(enemy): one-time setup when the enemy is created (e.g.
    randomizing an initial cooldown so enemies don't all sync up).
  - update(enemy, dt, player, arena_rect, all_enemies=None): called every
    frame the enemy is alive. `all_enemies` is the live enemy roster
    (only populated for enemies, not the player); most skills ignore it,
    but aura-style skills like Flagbearer need it to see nearby allies.

An enemy using a skill needs whatever attributes that skill expects
(e.g. contact_damage expects `enemy.stats`, `enemy.x/y`, `enemy.radius`).
The Enemy class in main.py provides all of these.
"""

class Skill:
    """Base class - override on_spawn/update as needed."""
    name = "base_skill"

    def on_spawn(self, enemy):
        pass

    def update(self, enemy, dt, player, arena_rect, all_enemies=None):
        pass

    def on_collision(self, enemy, player):
        pass

    def on_damaged(self, enemy, attacker, amount):
        pass

    def on_damage_dealt(self, enemy, target, amount):
        pass

    def on_wall_hit(self, entity):
        pass

    def on_entity_collision(self, entity, other):
        pass

    def on_eye_of_sight_trigger(self, entity):
        pass


class ContactDamage(Skill):
    """Lets an enemy deal damage just by touching the player - no weapon
    needed. Has its own short cooldown so overlapping doesn't melt the
    player in a single frame."""
    name = "contact_damage"
    HIT_COOLDOWN = 0.6  # seconds between contact hits on the player

    def on_spawn(self, enemy):
        enemy.contact_cooldown_timer = 0.0

    def update(self, enemy, dt, player, arena_rect, all_enemies=None):
        if getattr(enemy, "is_player", False):
            return
        if enemy.contact_cooldown_timer > 0:
            enemy.contact_cooldown_timer -= dt
            return

        dist = math.hypot(player.x - enemy.x, player.y - enemy.y)
        if dist <= player.radius + enemy.radius:
            self._deal_damage(enemy, player)

    def on_collision(self, enemy, player):
        """Catch fast-moving contacts resolved after the normal skill update."""
        if getattr(enemy, "is_player", False):
            if enemy.stats.contact_damage_percent <= 0:
                return
            damage, is_crit, dodged = calculate_damage(enemy.stats, player.stats)
            damage *= enemy.stats.contact_damage_percent / 100
            if not dodged:
                player.take_damage(damage, attacker=enemy)
                enemy.last_bump_damage = damage
            return
        if enemy.contact_cooldown_timer <= 0:
            self._deal_damage(enemy, player)

    def _deal_damage(self, enemy, player):
        dmg, is_crit, dodged = calculate_damage(enemy.stats, player.stats, tags=["contact"])
        if not dodged:
            enemy.last_bump_damage = dmg
            player.take_damage(dmg, attacker=enemy)
            for skill in list(enemy.skills):
                skill.on_damage_dealt(enemy, player, dmg)
        enemy.contact_cooldown_timer = self.HIT_COOLDOWN


class EyeOfSight(Skill):
    """Periodically re-aims the enemy's movement straight at the player's
    current position, so it doesn't just wander and hope for a collision.
    Normal interval is 5-9s. The very first trigger after spawning can
    instead land anywhere from 1-9s, so enemies don't all "wake up" in
    lockstep with each other."""
    name = "eye_of_sight"
    NORMAL_MIN, NORMAL_MAX = 5.0, 9.0
    SPAWN_MIN, SPAWN_MAX = 1.0, 9.0
    FLASH_DURATION = 0.35
    FAST_MIN, FAST_MAX = 1.0, 4.0
    DIRECTION_SIGN = 1  # +1 = steer toward the target. EyeOfAvoidance flips this to -1.

    def on_spawn(self, enemy):
        enemy.eye_of_sight_timer = random.uniform(self.SPAWN_MIN, self.SPAWN_MAX)
        enemy.eye_of_sight_trigger_count = 0
        enemy.eye_of_sight_fast_initialized = False
        enemy.skill_flash_timer = 0.0
        enemy.skill_flash_duration = self.FLASH_DURATION
        if hasattr(self, "FLASH_COLOR"):
            enemy.skill_flash_color = self.FLASH_COLOR
        enemy.slam_shark_boost_timer = 0.0

    def update(self, enemy, dt, player, arena_rect, all_enemies=None):
        if getattr(enemy, "head_hitter_timer", 0) > 0:
            enemy.head_hitter_timer = max(0.0, enemy.head_hitter_timer - dt)
            if enemy.head_hitter_timer == 0:
                if random.uniform(0, 100) < enemy.stats.head_hitter_chance:
                    enemy.eye_of_sight_timer = 0.0
        if enemy.slam_shark_boost_timer > 0:
            enemy.slam_shark_boost_timer = max(0.0, enemy.slam_shark_boost_timer - dt)
            if enemy.slam_shark_boost_timer == 0:
                self._restore_normal_speed(enemy)
        if getattr(enemy, "body_slam_eye_locked", False):
            enemy.skill_flash_timer = max(0.0, enemy.skill_flash_timer - dt)
            return
        fast_mode = getattr(enemy, "eye_of_sight_fast", False)
        if fast_mode and not enemy.eye_of_sight_fast_initialized:
            enemy.eye_of_sight_timer = random.uniform(self.FAST_MIN, self.FAST_MAX)
            enemy.eye_of_sight_fast_initialized = True
        elif not fast_mode:
            enemy.eye_of_sight_fast_initialized = False
        enemy.eye_of_sight_timer -= dt
        enemy.skill_flash_timer = max(0.0, enemy.skill_flash_timer - dt)
        if enemy.eye_of_sight_trigger_count >= 3:
            return
        if enemy.eye_of_sight_timer <= 0:
            target = player
            if getattr(enemy, "is_player", False):
                targets = [candidate for candidate in player if candidate.alive]
                if not targets:
                    if fast_mode:
                        enemy.eye_of_sight_timer = random.uniform(self.FAST_MIN, self.FAST_MAX)
                    else:
                        enemy.eye_of_sight_timer = random.uniform(self.NORMAL_MIN, self.NORMAL_MAX)
                    return
                target = min(targets, key=lambda candidate: math.hypot(
                    candidate.x - enemy.x, candidate.y - enemy.y))

            dx = target.x - enemy.x
            dy = target.y - enemy.y
            dist = math.hypot(dx, dy) or 1.0
            speed = math.hypot(enemy.vx, enemy.vy) or (enemy.stats.move_speed * enemy.MOVE_SPEED_PIXEL_SCALE)
            enemy.vx = dx / dist * speed * self.DIRECTION_SIGN
            enemy.vy = dy / dist * speed * self.DIRECTION_SIGN
            if fast_mode:
                enemy.eye_of_sight_timer = random.uniform(self.FAST_MIN, self.FAST_MAX)
            else:
                enemy.eye_of_sight_timer = random.uniform(self.NORMAL_MIN, self.NORMAL_MAX)
            enemy.eye_of_sight_trigger_count += 1
            enemy.skill_flash_timer = self.FLASH_DURATION
            for skill in enemy.skills:
                skill.on_eye_of_sight_trigger(enemy)

    @staticmethod
    def _restore_normal_speed(entity):
        speed = math.hypot(entity.vx, entity.vy)
        normal_speed = entity.movement_speed
        if speed > 0:
            entity.vx = entity.vx / speed * normal_speed
            entity.vy = entity.vy / speed * normal_speed


class EyeOfAvoidance(EyeOfSight):
    """Eye of Sight's mirror image: same cadence, same spawn-stagger, same
    fast-mode wake-up - it just steers away from the nearest threat instead
    of charging it, and flashes blue instead of red so it reads as fleeing
    rather than aggroing."""
    name = "eye_of_avoidance"
    DIRECTION_SIGN = -1
    FLASH_COLOR = (60, 150, 255)


class WayOfNinja(Skill):
    """Summons an allied Shuriken Projectile every five seconds."""
    name = "way_of_ninja"
    SUMMON_INTERVAL = 5.0

    def on_spawn(self, enemy):
        enemy.way_of_ninja_timer = self.SUMMON_INTERVAL

    def update(self, enemy, dt, player, arena_rect, all_enemies=None):
        if not getattr(enemy, "is_player", False):
            return
        enemy.way_of_ninja_timer -= dt
        if enemy.way_of_ninja_timer <= 0:
            enemy.summon_shuriken_projectiles()
            enemy.way_of_ninja_timer = self.SUMMON_INTERVAL


class SlamShark(Skill):
    """Temporarily boosts movement whenever Eye of Sight triggers."""
    name = "slam_shark"
    BOOST_FACTOR = 1.8
    BOOST_DURATION = 0.8

    def on_eye_of_sight_trigger(self, enemy):
        if not getattr(enemy, "slam_shark_boost_timer", 0) > 0:
            enemy.slam_shark_boost_timer = self.BOOST_DURATION
            enemy.vx *= self.BOOST_FACTOR
            enemy.vy *= self.BOOST_FACTOR


class HeadHitter(Skill):
    """Gives each Eye of Sight dash a delayed chance to trigger again."""
    name = "head_hitter"

    def on_eye_of_sight_trigger(self, enemy):
        enemy.head_hitter_timer = 0.6


class LingeringPoison(Skill):
    """Adds stacking damage-over-time effects to enemies hit by the player."""
    name = "lingering_poison"

    def on_damage_dealt(self, attacker, target, amount):
        if getattr(attacker, "is_player", False):
            target.add_poison(attacker.stats.attack * 0.6, 3.0)


class SelfAnnihilating(Skill):
    """Deals a final retaliation when its owner successfully deals damage."""
    name = "self_annihilating"

    def on_damage_dealt(self, enemy, target, amount):
        if getattr(enemy, "self_annihilated", False):
            return
        enemy.self_annihilated = True
        damage = enemy.stats.attack * enemy.stats.special_damage
        target.take_damage(damage, attacker=enemy)
        enemy.alive = False


class BodySlam(Skill):
    """Makes the next bumped enemy impact hurt both involved enemies."""
    name = "body_slam"
    SPEED_MULTIPLIER = 1.8
    IMPACT_FACTOR = 0.4

    def on_spawn(self, enemy):
        enemy.body_slam_pending = False
        enemy.body_slam_source = None
        enemy.body_slam_damage = 0.0
        enemy.body_slam_impact_count = 0
        enemy.body_slam_required_impacts = 1
        enemy.body_slam_handler = None
        enemy.body_slam_eye_locked = False

    def on_collision(self, owner, other):
        if getattr(owner, "is_player", False):
            if getattr(owner, "last_bump_damage", 0) <= 0:
                return
            self._arm_slam(other, owner, owner.last_bump_damage)
            owner.last_bump_damage = 0.0
            return
        if not getattr(other, "is_player", False):
            return
        if getattr(owner, "last_bump_damage", 0) <= 0:
            return
        self._arm_slam(other, owner, owner.last_bump_damage)
        owner.last_bump_damage = 0.0

    def _arm_slam(self, target, source, damage):
        target.body_slam_pending = True
        target.body_slam_source = source
        target.body_slam_damage = damage
        target.body_slam_impact_count = 0
        target.body_slam_required_impacts = 1 + getattr(
            source.stats, "body_slam_extra_impacts", 0)
        target.body_slam_handler = self
        target.body_slam_eye_locked = True
        target.slam_ripple_timer = 0.0
        target.slam_ripples = []
        target.vx *= self.SPEED_MULTIPLIER
        target.vy *= self.SPEED_MULTIPLIER

    def on_wall_hit(self, enemy):
        if enemy.body_slam_pending:
            self._register_impact(enemy, None)
        if not enemy.body_slam_pending:
            enemy.body_slam_eye_locked = False
            enemy.body_slam_handler = None

    def on_entity_collision(self, enemy, other):
        if enemy.body_slam_pending:
            self._register_impact(enemy, other)

    def _register_impact(self, enemy, other):
        enemy.body_slam_impact_count += 1
        self._deal_impact_damage(enemy, other)
        if enemy.body_slam_impact_count < enemy.body_slam_required_impacts:
            return
        self._finish_slam(enemy)

    def _deal_impact_damage(self, enemy, other):
        source = enemy.body_slam_source
        impact_damage = self.IMPACT_FACTOR * (
            enemy.body_slam_damage + source.stats.move_speed)
        if impact_damage > 0:
            enemy.take_damage(impact_damage, attacker=source)
            if other is not None and other is not source:
                other.take_damage(impact_damage)

    def _finish_slam(self, enemy):
        enemy.body_slam_pending = False
        enemy.body_slam_source = None
        enemy.body_slam_damage = 0.0
        enemy.body_slam_eye_locked = False
        enemy.body_slam_handler = None
        speed = math.hypot(enemy.vx, enemy.vy)
        if speed > 0:
            enemy.vx = enemy.vx / speed * enemy.movement_speed
            enemy.vy = enemy.vy / speed * enemy.movement_speed


class BountyBump(Skill):
    """Wresler Kai's signature. As long as he goes without landing a bump
    (or otherwise dealing damage), he builds up stacks every 3 seconds -
    each one worth +10% of his own move speed, and each one tints him a
    little redder. Bumping the player, or any damage he deals, burns the
    whole stack off and restarts the clock."""
    name = "bounty_bump"
    STACK_INTERVAL = 0.6        # seconds between stack gains while "patient"
    SPEED_PER_STACK = 0.25      # +25% of base move speed, per stack
    MAX_STACKS = 40             # safety cap so the speed can't run away forever
    MAX_TINT_STACKS = 5         # fully red by this many stacks

    def on_spawn(self, enemy):
        enemy.bounty_bump_stacks = 0
        enemy.bounty_bump_timer = self.STACK_INTERVAL
        enemy.bounty_bump_base_speed = enemy.stats.move_speed

    def update(self, enemy, dt, player, arena_rect, all_enemies=None):
        enemy.bounty_bump_timer -= dt
        while (enemy.bounty_bump_timer <= 0
               and enemy.bounty_bump_stacks < self.MAX_STACKS):
            enemy.bounty_bump_stacks += 1
            enemy.bounty_bump_timer += self.STACK_INTERVAL
            self._apply_speed(enemy)
        if enemy.bounty_bump_timer <= 0:
            enemy.bounty_bump_timer = self.STACK_INTERVAL

    def on_collision(self, enemy, player):
        self._reset(enemy)

    def on_damage_dealt(self, enemy, target, amount):
        self._reset(enemy)

    def _apply_speed(self, enemy):
        old_speed = enemy.stats.move_speed
        new_speed = enemy.bounty_bump_base_speed * (
            1 + self.SPEED_PER_STACK * enemy.bounty_bump_stacks)
        enemy.stats.move_speed = new_speed
        if old_speed > 0:
            ratio = new_speed / old_speed
            enemy.vx *= ratio
            enemy.vy *= ratio

    def _reset(self, enemy):
        if enemy.bounty_bump_stacks == 0:
            return
        old_speed = enemy.stats.move_speed
        enemy.bounty_bump_stacks = 0
        enemy.bounty_bump_timer = self.STACK_INTERVAL
        enemy.stats.move_speed = enemy.bounty_bump_base_speed
        if old_speed > 0:
            ratio = enemy.bounty_bump_base_speed / old_speed
            enemy.vx *= ratio
            enemy.vy *= ratio


class Flagbearer(Skill):
    """Aura skill: every RALLY_INTERVAL seconds, force-retriggers Eye of
    Sight (or Eye of Avoidance) on every ally within RADIUS, regardless of
    that ally's own cooldown - a rally pulse layered on top of an ally's
    normal cadence. Works on both sides of the fight:
      - On an enemy (e.g. Flagbearer Pippa), "allies" are nearby enemies
        (from `all_enemies`) and the aim target is the player.
      - On the player, "allies" are the player's own shurikens (from
        `enemy.summons` - shurikens have no Eye of Sight of their own, so
        the pulse re-aims them directly) and the aim target is whichever
        enemy is nearest. Note the `player` parameter is repurposed to
        carry the enemies list in this case - see Ball.update().

    Also stamps a `flagbearer_pulse_progress` (0 -> 1 sawtooth, synced to
    the owner's cooldown, not each ally's own) onto the owner and every
    ally currently in range each frame, purely for rendering - main.py
    uses it to draw a synchronized "buffed" pulse ring."""
    name = "flagbearer"
    RALLY_INTERVAL = 0.75
    RADIUS = 22 * 5  # player ball's BALL_RADIUS (22) x5

    def on_spawn(self, enemy):
        enemy.flagbearer_timer = self.RALLY_INTERVAL
        enemy.flagbearer_pulse_progress = 0.0

    def update(self, enemy, dt, player, arena_rect, all_enemies=None):
        enemy.flagbearer_timer -= dt
        fire = enemy.flagbearer_timer <= 0
        if fire:
            enemy.flagbearer_timer += self.RALLY_INTERVAL

        # 0 -> 1 across each rally cycle. Stamped onto every currently-in
        # -range ally (and herself) so their visual pulse stays locked to
        # THIS cooldown instead of drifting off each ally's own timer.
        progress = 1 - max(0.0, min(1.0, enemy.flagbearer_timer / self.RALLY_INTERVAL))
        enemy.flagbearer_pulse_progress = progress

        is_player = getattr(enemy, "is_player", False)
        allies = enemy.summons if is_player else (all_enemies or [])
        target = self._nearest(enemy, player) if is_player else player
        if target is None:
            return

        for ally in allies:
            if ally is enemy or not getattr(ally, "alive", True):
                continue
            if math.hypot(ally.x - enemy.x, ally.y - enemy.y) > self.RADIUS:
                continue
            ally.flagbearer_pulse_progress = progress
            if fire:
                self._rally(ally, target)

    @staticmethod
    def _nearest(enemy, candidates):
        living = [c for c in candidates if getattr(c, "alive", True)]
        if not living:
            return None
        return min(living, key=lambda c: math.hypot(c.x - enemy.x, c.y - enemy.y))

    @staticmethod
    def _rally(ally, target):
        if getattr(ally, "body_slam_eye_locked", False):
            return
        eye_skill = next(
            (skill for skill in getattr(ally, "skills", [])
             if skill.name in ("eye_of_sight", "eye_of_avoidance")), None)
        # Allies without an Eye skill (shurikens) still get re-aimed - they
        # just default to chasing rather than fleeing.
        sign = getattr(eye_skill, "DIRECTION_SIGN", 1)
        dx = target.x - ally.x
        dy = target.y - ally.y
        dist = math.hypot(dx, dy) or 1.0
        speed = math.hypot(ally.vx, ally.vy) or ally.movement_speed
        ally.vx = dx / dist * speed * sign
        ally.vy = dy / dist * speed * sign
        if eye_skill is not None:
            ally.skill_flash_timer = eye_skill.FLASH_DURATION
            if hasattr(eye_skill, "FLASH_COLOR"):
                ally.skill_flash_color = eye_skill.FLASH_COLOR
            for skill in ally.skills:
                skill.on_eye_of_sight_trigger(ally)


class FloweringBud(Skill):
    """Every enemy the player lands a killing blow on permanently adds a
    little more HP regen, on top of the flat regen the card grants up
    front. Detected off the on_damage_dealt hook: if the hit that just
    landed took the target to 0 hp, it was a kill. (Poison ticks call
    take_damage without an attacker, so poison kills don't trigger this -
    a small known gap, same as other on-hit effects in this file.)"""
    name = "flowering_bud"
    REGEN_PER_KILL = 0.02

    def on_damage_dealt(self, attacker, target, amount):
        if getattr(attacker, "is_player", False) and target.stats.hp <= 0:
            attacker.stats.hp_regen += self.REGEN_PER_KILL


# Registry: name -> skill instance. Add new skills above, then register
# them here so enemy configs can reference them by name.
SKILL_REGISTRY = {
    ContactDamage.name: ContactDamage(),
    EyeOfSight.name: EyeOfSight(),
    EyeOfAvoidance.name: EyeOfAvoidance(),
    SelfAnnihilating.name: SelfAnnihilating(),
    BodySlam.name: BodySlam(),
    SlamShark.name: SlamShark(),
    HeadHitter.name: HeadHitter(),
    LingeringPoison.name: LingeringPoison(),
    WayOfNinja.name: WayOfNinja(),
    BountyBump.name: BountyBump(),
    Flagbearer.name: Flagbearer(),
    FloweringBud.name: FloweringBud(),
}


def get_skills(names):
    """Look up skill instances by name, preserving order. Unknown names
    are silently skipped (handy for quickly disabling one without editing
    the enemy's skills list)."""
    return [SKILL_REGISTRY[n] for n in names if n in SKILL_REGISTRY]


# BLUE CARD DEFINITIONS
# SHURIKEN MASTERY: no prerequisite, weight 7, infinitely stackable;
#                   summons one additional full-size shuriken per cast.
# MINI SHURIKENS: no prerequisite, weight 2, one-time purchase;
#                 full-size shurikens split into two mini shurikens when they die.
# SPLIT FORMATION: requires MINI SHURIKENS, weight 7, infinitely stackable;
#                  increases the number of mini shurikens from each split by 1.
# HEAD HITTER: requires SLAM SHARK, weight 10, up to four purchases;
#              each purchase adds a 20% chance to dash again after a body hit
#              and increases the player's rage visual intensity.
# FLAGBEARER: no prerequisite, weight 2, one-time purchase;
#             pulses every 0.75s and force-reaims every ally (including
#             shurikens) at the nearest enemy.
# FLOWERING BUD: no prerequisite, weight 1, one-time purchase;
#                grants +1 HP regen immediately, then +0.02 more, permanently,
#                for every enemy the player kills.
# GREEN PIP PUP: no prerequisite, weight 1, one-time purchase;
#                grants a persistent Green Pip ally (pet tag) - +100 defence,
#                +500 HP, 0.8x speed, +4 attack over a normal Green Pip.
#                Pets respawn at the start of every wave if lost.
# PET POWER!: requires GREEN PIP PUP, weight 10, up to 20 purchases;
#             each purchase adds +20% move speed and +20% attack to every
#             pet the player owns.


# ===========================================================================
# main.py
# ===========================================================================
# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
FPS = 60

# Arena rectangle is computed at runtime once we know the real screen size
# (see setup_arena_rect below). This margin is how far the arena walls sit
# from the edges of the screen.
ARENA_MARGIN = 60

ARENA_COLOR = (30, 30, 40)
ARENA_BORDER_COLOR = (90, 90, 110)
ARENA_BORDER_WIDTH = 6

BG_COLOR = (12, 12, 16)

# Faint background decoration so the screen isn't a flat void.
GRID_SPACING = 48
GRID_COLOR = (255, 255, 255, 12)     # very low alpha
GRID_COLOR_ACCENT = (255, 255, 255, 22)

NUM_DRIFT_PARTICLES = 45
PARTICLE_COLOR = (200, 210, 255, 40)  # low opacity
PARTICLE_MIN_SPEED = 6
PARTICLE_MAX_SPEED = 18
PARTICLE_MIN_RADIUS = 1
PARTICLE_MAX_RADIUS = 3

BALL_RADIUS = 22
GREEN_BALL_COLOR = (60, 220, 100)
GREEN_BALL_OUTLINE = (20, 90, 45)

SWORD_LENGTH = 55       # how far the sword extends from the ball center
SWORD_WIDTH = 6         # thin rectangle
SWORD_COLOR = (230, 230, 240)
SWORD_SPIN_SPEED_BASE = 180  # degrees/sec at attack_speed == 10 (the stat base)

# Converts the move_speed stat (base 10) into actual pixels/sec.
MOVE_SPEED_PIXEL_SCALE = 18

# --- Intro sequence timings (seconds) ---
DELAY_BEFORE_MOVE = 0.5     # ball sits still this long before it starts moving
DELAY_BEFORE_READY = 0.7    # how long it moves before the READY banner hits
READY_DISPLAY_TIME = 0.9    # fast, punchy - the whole hype banner start to finish

# READY banner hype effects
READY_SCALE_IN_TIME = 0.20
READY_FADE_OUT_TIME = 0.22
READY_SHAKE_DURATION = 0.45
READY_SHAKE_MAGNITUDE = 16       # pixels
READY_FLASH_DURATION = 0.06      # pure white impact flash at the very start
READY_FLASH_COLORS = [
    (255, 240, 90),
    (255, 130, 30),
    (255, 255, 255),
]
READY_COLOR_CYCLE_SPEED = 16     # flashes per second, roughly

# HUD
HUD_MARGIN = 24
WAVE_TEXT_COLOR = (235, 235, 245)
WAVE_FONT_SIZE = 36

HEALTHBAR_WIDTH = 280
HEALTHBAR_HEIGHT = 28
HEALTHBAR_BG_COLOR = (35, 35, 40)
HEALTHBAR_BORDER_COLOR = (220, 220, 225)
HEALTHBAR_HIGH_COLOR = (70, 220, 100)
HEALTHBAR_MID_COLOR = (240, 200, 60)
HEALTHBAR_LOW_COLOR = (230, 70, 60)
HEALTHBAR_TEXT_COLOR = (255, 255, 255)

# Coin counter (bottom-right)
COIN_TEXT_COLOR = (255, 215, 60)
COIN_FONT_SIZE = 28
TOKEN_TEXT_COLOR = (185, 195, 210)
TOKEN_FONT_SIZE = 26
PLAYER_STAT_FONT_SIZE = 16
PLAYER_STAT_ALPHA = 190
ENEMY_HEALTHBAR_WIDTH = 42
ENEMY_HEALTHBAR_HEIGHT = 5

CARD_COUNT = 3
CARD_POOL_COLORS = {
    "gray": (160, 175, 195),
    "blue": (80, 170, 255),
}

# Sword-vs-enemy hit pacing.
SWORD_HIT_COOLDOWN = 0.25   # seconds an enemy is safe after being hit, to
                            # avoid the same swing multi-hitting in one pass

# Spawn pacing: the delay before the *next* enemy in the wave's queue
# comes in scales up with how many enemies are currently alive, so the
# queue naturally takes longer to drain the more undefeated enemies
# there are.
SPAWN_BASE_INTERVAL = 0.4
SPAWN_ALIVE_SCALE = 0.15
SPAWN_INTERVAL_MAX = 3.0

# Short visual accent when an enemy enters the arena.
SPAWN_POP_DURATION = 0.18
SPAWN_FLASH_COLOR = (255, 245, 170)

# Thin ring drawn around every Pet so allied Green Pips read as friendly
# at a glance instead of blending into the enemy Green Pip crowd.
PET_RING_COLOR = (120, 210, 255)

# Debug spawn: press Q during gameplay to add a nearly unkillable Green Pip.
DEBUG_GREEN_PIP_HP = 1_000_000_000_000
DEBUG_GREEN_PIP_ATTACK = 1
DEBUG_GREEN_PIP_RADIUS = 30
GREEN_PIP_VARIANT_CHANCE = 0.10
MULTIPLAYER_HEALTH_MULTIPLIER = 1.7
MULTIPLAYER_VARIANT_CHANCE = 0.40

SKILL_FLASH_COLOR = (235, 35, 35)
BODY_SLAM_COLOR = (255, 125, 25)
BODY_SLAM_OUTLINE_COLOR = (255, 205, 80)

# Bounty Bump (Wresler Kai's stacking-speed skill): tints him toward this
# color as stacks build, maxing out at BOUNTY_BUMP_MAX_TINT_STACKS - keep
# in sync with BountyBump.MAX_TINT_STACKS in skills.py.
BOUNTY_BUMP_HOT_COLOR = (235, 40, 40)
BOUNTY_BUMP_MAX_TINT_STACKS = 5

# Flagbearer Pippa: her aura-radius indicator, and the synced "buffed"
# pulse ring drawn on herself + every ally currently in range. The pulse
# tracks Flagbearer.flagbearer_pulse_progress (her own cooldown, 0 -> 1),
# not each ally's individual timer - that's what keeps them all in sync.
FLAG_RADIUS_COLOR = (120, 175, 255)
FLAG_RADIUS_FILL_ALPHA = 22     # very low opacity - just enough to read the zone
FLAG_RADIUS_STROKE_ALPHA = 70
FLAGBEARER_PULSE_COLOR = (140, 195, 255)
FLAGBEARER_PULSE_MIN_ALPHA = 40
FLAGBEARER_PULSE_MAX_ALPHA = 170
FLAGBEARER_PULSE_MIN_PAD = 4
FLAGBEARER_PULSE_MAX_PAD = 14

# --- Wave bosses: every WAVE_BOSS_INTERVAL waves, a random entry from
# WAVE_BOSS_CONFIGS gets its own cinematic entrance instead of trickling
# in with the normal spawn queue. ---
WAVE_BOSS_INTERVAL = 3

BOSS_INTRO_WARNING_TIME = 0.6       # hazard-stripe "WARNING" beat
BOSS_INTRO_SCALE_IN_TIME = 0.25     # name punches in
BOSS_INTRO_HOLD_TIME = 1.15         # name holds so it's readable
BOSS_INTRO_FADE_OUT_TIME = 0.35     # name bursts away
BOSS_INTRO_DURATION = (BOSS_INTRO_WARNING_TIME + BOSS_INTRO_SCALE_IN_TIME
                        + BOSS_INTRO_HOLD_TIME + BOSS_INTRO_FADE_OUT_TIME)
BOSS_INTRO_FLASH_DURATION = 0.08
BOSS_INTRO_SHAKE_DURATION = 0.5
BOSS_INTRO_SHAKE_MAGNITUDE = 22
BOSS_NAME_COLOR_CYCLE = [
    (225, 90, 255),
    (255, 60, 90),
    (255, 255, 255),
]
BOSS_NAME_COLOR_CYCLE_SPEED = 14

BOSS_SPAWN_POP_DURATION = 0.55      # boss "slams down" slower than a normal pop
BOSS_SPAWN_FLASH_COLOR = (215, 130, 255)
BOSS_SPAWN_SHAKE_DURATION = 0.35
BOSS_SPAWN_SHAKE_MAGNITUDE = 20

BOSS_HEALTHBAR_WIDTH = 520
BOSS_HEALTHBAR_HEIGHT = 26

# Floating damage number presentation.
DAMAGE_TEXT_LIFETIME = 0.85
DAMAGE_TEXT_BASE_SIZE = 22
DAMAGE_TEXT_MAX_SCALE = 3.0
DAMAGE_TEXT_SCALE_DAMAGE = 200.0
DAMAGE_TEXT_GRAVITY = 180.0
DAMAGE_TEXT_RISE_SPEED = -100.0

# Pause between one wave's spawn queue emptying and the next wave's queue
# starting. The delay shortens while the wave is being cleared, reaching its
# one-second floor after 15 seconds.
WAVE_GAP_MAX = 2.0
WAVE_GAP_MIN = 1.0
POST_SPAWN_ACCELERATION_TIME = 15.0

# ---------------------------------------------------------------------------
# Stats: see stats.py (shared by the player and all enemies).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------
class Sword:
    """A thin rectangular blade that spins continuously around its owner."""

    def __init__(self, length=SWORD_LENGTH, width=SWORD_WIDTH,
                 spin_speed=SWORD_SPIN_SPEED_BASE, start_angle=0):
        self.length = length
        self.width = width
        self.spin_speed = spin_speed  # degrees/sec, positive = clockwise
        self.angle = start_angle

    def update(self, dt):
        self.angle = (self.angle + self.spin_speed * dt) % 360

    def draw(self, surface, origin):
        ox, oy = origin
        rad = math.radians(self.angle)

        # The blade is a thin rectangle whose long axis points along `angle`,
        # offset outward from the ball center a bit so it looks mounted on it.
        inner_offset = BALL_RADIUS * 0.5
        cx = ox + math.cos(rad) * (inner_offset + self.length / 2)
        cy = oy + math.sin(rad) * (inner_offset + self.length / 2)

        half_l = self.length / 2
        half_w = self.width / 2

        # Rectangle corners in local space (aligned with x-axis), then rotate.
        corners = [(-half_l, -half_w), (half_l, -half_w),
                   (half_l, half_w), (-half_l, half_w)]

        cos_a, sin_a = math.cos(rad), math.sin(rad)
        rotated = []
        for lx, ly in corners:
            rx = lx * cos_a - ly * sin_a
            ry = lx * sin_a + ly * cos_a
            rotated.append((cx + rx, cy + ry))

        pygame.draw.polygon(surface, SWORD_COLOR, rotated)

    def hits(self, origin, target_pos, target_radius):
        """True if a circle at target_pos (with target_radius) overlaps
        the spinning blade right now. Works by rotating the target into
        the blade's local frame (blade axis = local x-axis) and checking
        an expanded bounding box against it."""
        ox, oy = origin
        tx, ty = target_pos
        dx, dy = tx - ox, ty - oy

        rad = math.radians(-self.angle)  # inverse rotation
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        local_x = dx * cos_a - dy * sin_a
        local_y = dx * sin_a + dy * cos_a

        inner_offset = BALL_RADIUS * 0.5
        half_w = self.width / 2

        min_x = inner_offset - target_radius
        max_x = inner_offset + self.length + target_radius
        max_y = half_w + target_radius

        return min_x <= local_x <= max_x and abs(local_y) <= max_y


def bounce_off_walls(entity, arena_rect):
    """Shared wall-collision handling for anything with x/y/radius/vx/vy,
    used by both the player ball and enemies."""
    left = arena_rect.left + entity.radius
    right = arena_rect.right - entity.radius
    top = arena_rect.top + entity.radius
    bottom = arena_rect.bottom - entity.radius
    hit_wall = False

    if entity.x < left:
        entity.x = left
        entity.vx *= -1
        hit_wall = True
    elif entity.x > right:
        entity.x = right
        entity.vx *= -1
        hit_wall = True

    if entity.y < top:
        entity.y = top
        entity.vy *= -1
        hit_wall = True
    elif entity.y > bottom:
        entity.y = bottom
        entity.vy *= -1
        hit_wall = True

    if hit_wall and hasattr(entity, "eye_of_sight_trigger_count"):
        entity.eye_of_sight_trigger_count = 0
    if hit_wall:
        for skill in getattr(entity, "skills", []):
            skill.on_wall_hit(entity)
        handler = getattr(entity, "body_slam_handler", None)
        if handler is not None:
            handler.on_wall_hit(entity)
    return hit_wall


def get_skill_flash_color(base_color, timer, duration, flash_color=SKILL_FLASH_COLOR):
    """Blend an entity from its flash color (hot red by default; some
    skills like Eye of Avoidance use their own) back to its base color."""
    if timer <= 0 or duration <= 0:
        return base_color
    strength = min(1.0, timer / duration)
    return tuple(int(base_color[index] * (1 - strength) + flash_color[index] * strength)
                 for index in range(3))


def keep_movement_speed(entity, speed):
    """Keep a collision response from changing an entity's movement speed."""
    current_speed = math.hypot(entity.vx, entity.vy)
    if current_speed > 0 and speed > 0:
        entity.vx = entity.vx / current_speed * speed
        entity.vy = entity.vy / current_speed * speed


def segment_circle_hit(x1, y1, x2, y2, cx, cy, radius):
    """Return whether a movement segment intersects a circle."""
    dx, dy = x2 - x1, y2 - y1
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.hypot(cx - x1, cy - y1) <= radius
    projection = ((cx - x1) * dx + (cy - y1) * dy) / length_squared
    projection = max(0.0, min(1.0, projection))
    closest_x = x1 + projection * dx
    closest_y = y1 + projection * dy
    return math.hypot(cx - closest_x, cy - closest_y) <= radius


class Combatant:
    """Shared movement_speed/take_damage for Ball, Enemy, and ShurikenProjectile."""

    @property
    def movement_speed(self):
        return self.stats.move_speed * MOVE_SPEED_PIXEL_SCALE

    def take_damage(self, amount, attacker=None, flash_color=(255, 245, 245),
                    fire_skill_hooks=False, emit_damage_event=True):
        if amount <= 0:
            return
        self.stats.hp = max(0.0, self.stats.hp - amount)
        if emit_damage_event:
            self.damage_events.append((amount, self.x, self.y, flash_color))
        if fire_skill_hooks:
            if attacker is not None:
                for skill in getattr(attacker, "skills", []):
                    skill.on_damage_dealt(attacker, self, amount)
            for skill in self.skills:
                skill.on_damaged(self, attacker, amount)
        if hasattr(self, "alive") and self.stats.hp <= 0:
            self.alive = False

    def has_skill(self, skill_name):
        return any(skill.name == skill_name for skill in self.skills)

    def has_tag(self, tag):
        """Entities without a `tags` attribute simply carry no tags."""
        return tag in getattr(self, "tags", ())

    def draw_flagbearer_effects(self, surface):
        """Draw the rally-radius aura (if this entity carries Flagbearer)
        and the buff pulse ring (if currently tagged by one) - shared by
        Ball, Enemy, and ShurikenProjectile so allies of either faction's
        Flagbearer render identically."""
        if self.has_skill("flagbearer"):
            self._draw_flagbearer_aura(surface)
        pulse_progress = getattr(self, "flagbearer_pulse_progress", None)
        if pulse_progress is not None:
            self._draw_flagbearer_pulse(surface, pulse_progress)

    def _draw_flagbearer_aura(self, surface):
        """Low-opacity circle showing Flagbearer's rally radius, with a
        stroke that breathes in time with the owner's own cooldown."""
        radius = int(Flagbearer.RADIUS)
        size = radius * 2 + 4
        aura_surface = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size // 2, size // 2)
        pygame.draw.circle(aura_surface, (*FLAG_RADIUS_COLOR, FLAG_RADIUS_FILL_ALPHA),
                           center, radius)
        progress = getattr(self, "flagbearer_pulse_progress", 0.0) or 0.0
        pulse = math.sin(max(0.0, min(1.0, progress)) * math.pi)
        stroke_alpha = int(FLAG_RADIUS_STROKE_ALPHA + (255 - FLAG_RADIUS_STROKE_ALPHA) * pulse * 0.4)
        pygame.draw.circle(aura_surface, (*FLAG_RADIUS_COLOR, stroke_alpha), center, radius, 2)
        surface.blit(aura_surface, (int(self.x) - center[0], int(self.y) - center[1]))

    def _draw_flagbearer_pulse(self, surface, progress):
        """Buff ring drawn on this entity (owner or a rallied ally),
        synced to the Flagbearer's own cooldown rather than this entity's
        own timer - so every buffed ally pulses in lockstep."""
        pulse = math.sin(max(0.0, min(1.0, progress)) * math.pi)
        pad = FLAGBEARER_PULSE_MIN_PAD + (FLAGBEARER_PULSE_MAX_PAD - FLAGBEARER_PULSE_MIN_PAD) * pulse
        alpha = int(FLAGBEARER_PULSE_MIN_ALPHA
                    + (FLAGBEARER_PULSE_MAX_ALPHA - FLAGBEARER_PULSE_MIN_ALPHA) * pulse)
        ring_radius = int(self.radius + pad)
        size = ring_radius * 2 + 6
        pulse_surface = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size // 2, size // 2)
        pygame.draw.circle(pulse_surface, (*FLAGBEARER_PULSE_COLOR, alpha), center, ring_radius, 3)
        surface.blit(pulse_surface, (int(self.x) - center[0], int(self.y) - center[1]))


class Ball(Combatant):
    """A player/enemy ball with a stat block, a spinning sword, and movement."""

    def __init__(self, x, y, radius, color, outline_color, stats=None):
        self.x = x
        self.y = y
        self.radius = radius
        self.color = color
        self.outline_color = outline_color
        self.stats = stats if stats is not None else Stats()
        self.damage_events = []
        self.last_bump_damage = 0.0
        self.head_hitter_timer = 0.0
        self.unlocked_cards = set()
        self.card_purchases = {}
        self.is_player = True
        self.faction = "allied"
        self.summons = []
        self.pets = []
        # key (PetConfig.key) -> how many of that pet this player should
        # currently have out. Cards add to this via grant_pet(); the
        # actual Pet objects are (re)spawned by respawn_pets().
        self.pet_grants = {}
        self.MOVE_SPEED_PIXEL_SCALE = MOVE_SPEED_PIXEL_SCALE
        self.skills = get_skills(["eye_of_sight", "way_of_ninja"])
        self.skill_flash_timer = 0.0
        self.skill_flash_duration = 0.35
        self.eye_of_sight_fast = False
        self.rage_flash_timer = 0.0
        for skill in self.skills:
            skill.on_spawn(self)

        spin_speed = SWORD_SPIN_SPEED_BASE * (self.stats.attack_speed / 10)
        self.sword = Sword(spin_speed=spin_speed, start_angle=random.uniform(0, 360))

        self.vx = 0.0
        self.vy = 0.0
        self.moving = False

    def start_moving(self):
        """Kick off movement in a random direction, scaled by move_speed."""
        angle = random.uniform(0, 2 * math.pi)
        pixel_speed = self.movement_speed
        self.vx = math.cos(angle) * pixel_speed
        self.vy = math.sin(angle) * pixel_speed
        self.moving = True

    def add_skill(self, skill_name):
        if any(skill.name == skill_name for skill in self.skills):
            return
        skill = get_skills([skill_name])[0]
        self.skills.append(skill)
        skill.on_spawn(self)

    def grant_pet(self, key, count=1):
        """Record that this player should have `count` more of the pet
        named `key` out at all times, then immediately spawn them (rather
        than waiting for the next wave) so buying the card pays off right
        away."""
        self.pet_grants[key] = self.pet_grants.get(key, 0) + count
        respawn_pets(self)

    def summon_shuriken_projectile(self):
        angle = random.uniform(0, 2 * math.pi)
        spawn_distance = self.radius + 4
        self.summons.append(ShurikenProjectile(
            self.x + math.cos(angle) * spawn_distance,
            self.y + math.sin(angle) * spawn_distance,
            self.stats,
            angle,
        ))

    def summon_shuriken_projectiles(self):
        for _ in range(1 + self.stats.shuriken_mastery):
            self.summon_shuriken_projectile()

    def notify_collision(self, other):
        for skill in self.skills:
            skill.on_collision(self, other)
        if self.stats.rage_level > 0 and random.uniform(0, 100) < min(
                100, self.stats.rage_level * 20):
            self.start_moving()
            self.rage_flash_timer = min(1.0, 0.35 + self.stats.rage_level * 0.1)

    def try_hit_enemies(self, enemies, dt):
        """Sweep the spinning sword against every enemy. Returns the list
        of enemies killed by this pass so the caller can hand out coins."""
        killed = []
        for enemy in enemies:
            if enemy.sword_hit_timer > 0:
                enemy.sword_hit_timer -= dt
                continue
            if self.sword.hits((self.x, self.y), (enemy.x, enemy.y), enemy.radius):
                dmg, is_crit, dodged = calculate_damage(self.stats, enemy.stats)
                if not dodged:
                    enemy.take_damage(dmg, attacker=self)
                enemy.sword_hit_timer = SWORD_HIT_COOLDOWN
                if not enemy.alive:
                    killed.append(enemy)
        return killed

    def update(self, dt, arena_rect, skill_targets=None):
        self.sword.update(dt)

        for skill in self.skills:
            skill.update(self, dt, skill_targets or [], arena_rect)
        self.rage_flash_timer = max(0.0, self.rage_flash_timer - dt)

        # Passive hp regen, clamped to max_hp.
        if self.stats.hp_regen:
            self.stats.hp = min(self.stats.max_hp, self.stats.hp + self.stats.hp_regen * dt)

        if not self.moving:
            return

        self.x += self.vx * dt
        self.y += self.vy * dt
        bounce_off_walls(self, arena_rect)

    def draw(self, surface):
        # Sword first so the ball sits visually "on top" of its own hilt.
        self.sword.draw(surface, (self.x, self.y))
        color = get_skill_flash_color(self.color, self.skill_flash_timer,
                                      self.skill_flash_duration,
                                      getattr(self, "skill_flash_color", SKILL_FLASH_COLOR))
        outline = self.outline_color
        rage_level = self.stats.rage_level
        if rage_level > 0:
            rage_strength = min(1.0, rage_level / 5)
            color = tuple(int(base * (1 - rage_strength) + hot * rage_strength)
                          for base, hot in zip(color, (220, 45, 25)))
            outline = (255, 130, 40)
        if getattr(self, "body_slam_pending", False):
            color = BODY_SLAM_COLOR
            outline = BODY_SLAM_OUTLINE_COLOR
        if rage_level > 0:
            rage_radius = self.radius + 7 + rage_level * 2
            rage_alpha = 70 if self.rage_flash_timer <= 0 else 170
            rage_layer = pygame.Surface((rage_radius * 2 + 8, rage_radius * 2 + 8),
                                        pygame.SRCALPHA)
            rage_center = (rage_radius + 4, rage_radius + 4)
            pygame.draw.circle(rage_layer, (255, 55, 20, rage_alpha),
                               rage_center, rage_radius, 3)
            surface.blit(rage_layer,
                         (int(self.x) - rage_center[0], int(self.y) - rage_center[1]))
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(surface, outline, (int(self.x), int(self.y)), self.radius, 3)
        self.draw_flagbearer_effects(surface)


class Enemy(Combatant):
    """An enemy ball built from an EnemyConfig - stats, skills, and an
    optional "graphic nuisance" look that reacts to its own hp."""

    def __init__(self, x, y, config, wave_number, debug_stats=False,
                 variant_type=None, health_multiplier=1.0):
        self.config = config
        self.x = x
        self.y = y

        self.radius_base = config.radius
        self.radius = config.radius
        self.visual_variant = "yellow" if config.key == "yellow_pip" else "green"
        self.is_miniboss = config.miniboss
        self.is_wave_boss = getattr(config, "wave_boss", False)
        self.is_debug_enemy = debug_stats
        self.variant_type = variant_type if config.key == "green_pip" else None
        self.pass_through_enemies = self.variant_type == 4
        if debug_stats:
            self.radius_base = DEBUG_GREEN_PIP_RADIUS
            self.radius = DEBUG_GREEN_PIP_RADIUS
        self.color = config.base_color
        self.outline_color = config.outline_color
        if self.variant_type == 2:
            self.outline_color = (235, 65, 65)
        elif self.variant_type == 3:
            self.outline_color = (245, 245, 245)
        elif self.variant_type == 5:
            self.outline_color = (255, 220, 45)
        self.variant_outline_color = self.outline_color

        stats = copy.deepcopy(config.base_stats)
        bonus = config.spawn_rule.hp_bonus_for_wave(wave_number)
        stats.max_hp = (stats.max_hp + bonus) * health_multiplier
        stats.attack += config.spawn_rule.attack_bonus_for_wave(wave_number)
        if self.variant_type == 1:
            self.radius_base *= 2
            self.radius *= 2
            stats.max_hp *= 2
            stats.attack *= 0.5
        elif self.variant_type == 2:
            stats.crit_rate += 20
        elif self.variant_type == 3:
            stats.attack *= 1.1
        elif self.variant_type == 5:
            stats.move_speed *= 2
            stats.defence += 1
        if debug_stats:
            stats.hp = DEBUG_GREEN_PIP_HP
            stats.max_hp = DEBUG_GREEN_PIP_HP
            stats.attack = DEBUG_GREEN_PIP_ATTACK
        else:
            stats.hp = stats.max_hp
        self.stats = stats
        self.damage_events = []
        self.last_bump_damage = 0.0
        self.poison_effects = []
        self.head_hitter_timer = 0.0

        # Skills reference this for their default movement speed if they
        # need to (re)compute a velocity vector.
        self.MOVE_SPEED_PIXEL_SCALE = MOVE_SPEED_PIXEL_SCALE

        angle = random.uniform(0, 2 * math.pi)
        speed = self.stats.move_speed * MOVE_SPEED_PIXEL_SCALE
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed

        self.sword_hit_timer = 0.0
        self.alive = True
        self.spawn_timer = SPAWN_POP_DURATION
        self.is_player = False
        self.faction = "enemy"
        self.skill_flash_timer = 0.0
        self.skill_flash_duration = 0.35
        self.eye_of_sight_fast = False

        self.skills = get_skills(config.skills)
        for skill in self.skills:
            skill.on_spawn(self)

    def take_damage(self, amount, attacker=None):
        # Enemies fire skill hooks on damage (contact-damage counters, etc).
        super().take_damage(amount, attacker=attacker,
                            flash_color=(255, 235, 90), fire_skill_hooks=True)

    def add_poison(self, damage_per_tick, duration):
        self.poison_effects.append([damage_per_tick, 3, 1.0])

    def update_poison(self, dt):
        damage = 0.0
        remaining = []
        for effect_damage, ticks_left, timer in self.poison_effects:
            timer -= dt
            while timer <= 0 and ticks_left > 0:
                damage += effect_damage
                ticks_left -= 1
                timer += 1.0
            if ticks_left > 0:
                remaining.append([effect_damage, ticks_left, timer])
        self.poison_effects = remaining
        if damage > 0:
            self.take_damage(damage)

    def notify_collision(self, player):
        for skill in self.skills:
            skill.on_collision(self, player)

    def update(self, dt, player, arena_rect, all_enemies=None):
        self.spawn_timer = max(0.0, self.spawn_timer - dt)
        self.update_poison(dt)
        for skill in self.skills:
            skill.update(self, dt, player, arena_rect, all_enemies)

        self.x += self.vx * dt
        self.y += self.vy * dt
        bounce_off_walls(self, arena_rect)

        if self.config.graphic_nuisance:
            self._update_graphic_nuisance()

    def _update_graphic_nuisance(self):
        """Grows toward full size and darkens toward its base color as hp
        rises back to max; shrinks and pales as it takes damage."""
        pct = hp_percent(self.stats)
        self.radius = self.radius_base * (0.5 + 0.5 * pct)

        base = self.config.base_color
        light = tuple(min(255, int(c + (255 - c) * 0.7)) for c in base)
        self.color = tuple(int(light[i] + (base[i] - light[i]) * pct) for i in range(3))

    def draw(self, surface):
        r = max(1, int(self.radius))
        color = get_skill_flash_color(self.color, self.skill_flash_timer,
                                      self.skill_flash_duration,
                                      getattr(self, "skill_flash_color", SKILL_FLASH_COLOR))
        slam_active = getattr(self, "body_slam_pending", False)
        if slam_active:
            color = BODY_SLAM_COLOR
        if self.spawn_timer > 0:
            pop_duration = BOSS_SPAWN_POP_DURATION if self.is_wave_boss else SPAWN_POP_DURATION
            flash_color = BOSS_SPAWN_FLASH_COLOR if self.is_wave_boss else SPAWN_FLASH_COLOR
            progress = 1 - self.spawn_timer / pop_duration
            scale = max(0.1, ease_out_back(progress))
            r = max(1, int(r * scale))
            padding = 20 if self.is_wave_boss else 8
            ring_pad = 14 if self.is_wave_boss else 5
            ring_width = 5 if self.is_wave_boss else 3
            pop_size = (r * 2 + padding * 2, r * 2 + padding * 2)
            pop_surface = pygame.Surface(pop_size, pygame.SRCALPHA)
            center = (pop_size[0] // 2, pop_size[1] // 2)
            pygame.draw.circle(pop_surface, (*flash_color, 150),
                               center, r + ring_pad, ring_width)
            pygame.draw.circle(pop_surface, (*color, 255),
                               center, r)
            pygame.draw.circle(pop_surface, (*self.variant_outline_color, 255),
                               center, r, 2)
            surface.blit(pop_surface, (int(self.x) - center[0], int(self.y) - center[1]))
            return
        self.draw_flagbearer_effects(surface)
        if self.is_debug_enemy:
            center = (int(self.x), int(self.y))
            pulse = 3 + int(3 * (math.sin(pygame.time.get_ticks() * 0.008) + 1) / 2)
            pygame.draw.circle(surface, (120, 255, 150), center, r + 10 + pulse, 3)
            pygame.draw.circle(surface, (35, 255, 115), center, r + 5, 3)
            if getattr(self, "body_slam_pending", False):
                slam_pulse = 2 + int(2 * (math.sin(pygame.time.get_ticks() * 0.012) + 1) / 2)
                pygame.draw.circle(surface, (255, 150, 35), center,
                                   r + 15 + slam_pulse, 4)
                slam_font = pygame.font.SysFont("arial", 14, bold=True)
                slam_label = slam_font.render("SLAM", True, (255, 205, 90))
                surface.blit(slam_label,
                             slam_label.get_rect(center=(center[0], center[1] - r - 18)))
            debug_outline = BODY_SLAM_OUTLINE_COLOR if slam_active else (220, 255, 230)
            debug_core = (255, 195, 60) if slam_active else (10, 90, 35)
            pygame.draw.circle(surface, color, center, r)
            pygame.draw.circle(surface, debug_outline, center, r, 3)
            pygame.draw.circle(surface, debug_core, center, r // 3)
            debug_font = pygame.font.SysFont("arial", 14, bold=True)
            label = debug_font.render("DEBUG", True, (220, 255, 230))
            surface.blit(label, label.get_rect(center=(center[0], center[1] - r - 15)))
            return
        if self.variant_type == 4:
            center = (int(self.x), int(self.y))
            transparent_surface = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            pygame.draw.circle(transparent_surface, (*color, 128), center, r)
            pygame.draw.circle(transparent_surface, (*self.variant_outline_color, 128),
                               center, r, 2)
            surface.blit(transparent_surface, (0, 0))
            return
        if self.is_wave_boss:
            center = (int(self.x), int(self.y))
            ticks = pygame.time.get_ticks() * 0.001
            outer_pulse = 6 + int(6 * (math.sin(ticks * 3) + 1) / 2)
            inner_pulse = 3 + int(3 * (math.sin(ticks * 5 + 1) + 1) / 2)
            stacks = getattr(self, "bounty_bump_stacks", 0)
            tint_strength = min(1.0, stacks / BOUNTY_BUMP_MAX_TINT_STACKS)
            boss_color = tuple(
                int(color[i] * (1 - tint_strength) + BOUNTY_BUMP_HOT_COLOR[i] * tint_strength)
                for i in range(3))
            aura_color = BODY_SLAM_COLOR if slam_active else self.outline_color
            pygame.draw.circle(surface, aura_color, center, r + 16 + outer_pulse, 3)
            pygame.draw.circle(surface, (235, 225, 245), center, r + 8 + inner_pulse, 2)
            pygame.draw.circle(surface, boss_color, center, r)
            pygame.draw.circle(surface, self.variant_outline_color, center, r, 4)
            boss_font = pygame.font.SysFont("arial", 20, bold=True)
            label = boss_font.render(self.config.display_name.upper(), True, (240, 220, 255))
            surface.blit(label, label.get_rect(center=(center[0], center[1] - r - 26)))
            return
        if self.is_miniboss:
            center = (int(self.x), int(self.y))
            pulse = 4 + int(4 * (math.sin(pygame.time.get_ticks() * 0.006) + 1) / 2)
            aura_color = BODY_SLAM_COLOR if slam_active else (45, 190, 70)
            miniboss_outline = BODY_SLAM_OUTLINE_COLOR if slam_active else (120, 255, 130)
            pygame.draw.circle(surface, aura_color, center, r + 10 + pulse, 4)
            pygame.draw.circle(surface, color, center, r)
            pygame.draw.circle(surface, miniboss_outline, center, r, 4)
            boss_font = pygame.font.SysFont("arial", 18, bold=True)
            label = boss_font.render("MINIBOSS", True, (150, 255, 150))
            surface.blit(label, label.get_rect(center=(center[0], center[1] - r - 18)))
            return
        if getattr(self, "body_slam_pending", False):
            center = (int(self.x), int(self.y))
            pulse = 2 + int(2 * (math.sin(pygame.time.get_ticks() * 0.012) + 1) / 2)
            pygame.draw.circle(surface, (255, 150, 35), center, r + 5 + pulse, 3)
            slam_font = pygame.font.SysFont("arial", 12, bold=True)
            label = slam_font.render("SLAM", True, (255, 205, 90))
            surface.blit(label, label.get_rect(center=(center[0], center[1] - r - 12)))
        if self.visual_variant == "yellow":
            center = (int(self.x), int(self.y))
            pygame.draw.circle(surface, color, center, r)
            core_color = BODY_SLAM_OUTLINE_COLOR if slam_active else (255, 250, 150)
            diamond_color = BODY_SLAM_OUTLINE_COLOR if slam_active else (255, 170, 20)
            pygame.draw.circle(surface, core_color, center, max(2, r // 2))
            diamond = [(center[0], center[1] - r // 2),
                       (center[0] + r // 2, center[1]),
                       (center[0], center[1] + r // 2),
                       (center[0] - r // 2, center[1])]
            pygame.draw.polygon(surface, diamond_color, diamond)
            pygame.draw.circle(surface, BODY_SLAM_OUTLINE_COLOR if slam_active else self.variant_outline_color,
                               center, r, 2)
            return
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), r)
        pygame.draw.circle(surface, self.variant_outline_color,
                           (int(self.x), int(self.y)), r, 2)


class ShurikenProjectile(Combatant):
    """An allied, fragile shuriken ball summoned by Way of Ninja."""

    def __init__(self, x, y, summoner_stats, angle, stat_scale=1.0,
                 is_mini=False):
        self.x = x
        self.y = y
        self.radius = max(4, int(BALL_RADIUS * 0.85 * stat_scale))
        self.is_mini = is_mini
        self.lifetime = 2.0 if is_mini else 4.0
        self.color = (155, 165, 175)
        self.outline_color = (225, 230, 235)
        self.faction = "allied"
        self.is_player = False
        self.alive = True
        self.damage_events = []
        self.stats = copy.deepcopy(summoner_stats)
        self.stats.hp = 1
        self.stats.max_hp = 1
        self.stats.attack = summoner_stats.attack * stat_scale
        self.stats.move_speed = max(5, summoner_stats.move_speed * 1.4 * stat_scale)
        self.vx = math.cos(angle) * self.movement_speed
        self.vy = math.sin(angle) * self.movement_speed
        self.previous_x = x
        self.previous_y = y
        self.skills = get_skills(["self_annihilating"])
        self.sword_hit_timer = 0.0
        self.spawn_timer = SPAWN_POP_DURATION
        self.skill_flash_timer = 0.0
        self.skill_flash_duration = 0.0
        self.body_slam_pending = False

    def take_damage(self, amount, attacker=None):
        super().take_damage(amount, attacker=attacker, emit_damage_event=False)

    def update(self, dt, arena_rect):
        self.spawn_timer = max(0.0, self.spawn_timer - dt)
        self.lifetime -= dt
        if self.lifetime <= 0:
            self.alive = False
            return
        self.previous_x = self.x
        self.previous_y = self.y
        self.x += self.vx * dt
        self.y += self.vy * dt
        bounce_off_walls(self, arena_rect)

    def try_hit_enemies(self, enemies):
        killed = []
        for enemy in enemies:
            if not enemy.alive:
                continue
            if segment_circle_hit(self.previous_x, self.previous_y, self.x, self.y,
                                  enemy.x, enemy.y, enemy.radius + self.radius):
                damage, is_crit, dodged = calculate_damage(self.stats, enemy.stats)
                if not dodged:
                    enemy.take_damage(damage, attacker=self)
                    self.alive = False
                    if not enemy.alive:
                        killed.append(enemy)
                return killed
        return killed

    def split(self, summoner_stats):
        """Create mini shurikens when a full-size shuriken is consumed."""
        if self.is_mini or not summoner_stats.mini_shurikens_enabled:
            return []
        mini_shurikens = []
        for _ in range(summoner_stats.shuriken_split_count):
            angle = random.uniform(0, 2 * math.pi)
            mini_shurikens.append(ShurikenProjectile(
                self.x + math.cos(angle) * (self.radius + 2),
                self.y + math.sin(angle) * (self.radius + 2),
                summoner_stats,
                angle,
                stat_scale=0.5,
                is_mini=True,
            ))
        return mini_shurikens

    def draw(self, surface):
        center = (int(self.x), int(self.y))
        alpha = 90
        layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*self.color, alpha), center, self.radius)
        pygame.draw.circle(layer, (*self.outline_color, 150), center, self.radius, 2)
        points = []
        for index in range(8):
            angle = math.radians(index * 45 + pygame.time.get_ticks() * 0.2)
            radius = self.radius + (6 if index % 2 == 0 else 1)
            points.append((center[0] + math.cos(angle) * radius,
                          center[1] + math.sin(angle) * radius))
        pygame.draw.polygon(layer, (205, 215, 225, 105), points, 1)
        surface.blit(layer, (0, 0))
        self.draw_flagbearer_effects(surface)


class Pet(Combatant):
    """A persistent allied ball, built from a PetConfig instead of the
    player's own stats. Unlike a shuriken summon, a Pet doesn't expire or
    consume itself on a hit - it just keeps chasing the nearest living
    enemy and trading contact damage with whatever it touches, and stays
    around (subject to respawn_pets() topping it back up each wave) for
    the rest of the run."""

    RETARGET_MIN, RETARGET_MAX = 1.5, 3.0
    CONTACT_COOLDOWN = 0.6

    def __init__(self, x, y, config, owner):
        self.config = config
        self.owner = owner
        self.x = x
        self.y = y
        self.radius = config.radius
        self.color = config.base_color
        self.outline_color = config.outline_color
        self.tags = tuple(config.tags)
        self.stats = copy.deepcopy(config.base_stats)
        self.stats.hp = self.stats.max_hp
        self.faction = "allied"
        self.is_player = False
        self.is_pet = True
        self.alive = True
        self.damage_events = []
        self.skills = []
        self.MOVE_SPEED_PIXEL_SCALE = MOVE_SPEED_PIXEL_SCALE

        angle = random.uniform(0, 2 * math.pi)
        self.vx = math.cos(angle) * self.movement_speed
        self.vy = math.sin(angle) * self.movement_speed
        self.retarget_timer = random.uniform(0, self.RETARGET_MIN)
        self.contact_cooldown_timer = 0.0
        self.spawn_timer = SPAWN_POP_DURATION
        self.skill_flash_timer = 0.0
        self.skill_flash_duration = 0.0
        self.body_slam_pending = False

    @property
    def movement_speed(self):
        # PET POWER! is read live off the owner's stats, so stacking more
        # copies of the card speeds up pets that already exist.
        bonus_percent = getattr(self.owner.stats, "pet_speed_percent", 0)
        return self.stats.move_speed * MOVE_SPEED_PIXEL_SCALE * (1 + bonus_percent / 100)

    def _effective_attack_stats(self):
        """This pet's stats with PET POWER!'s attack bonus folded in, for
        damage calculations only - the pet's own stat block never gets
        permanently rewritten, so the bonus can go up or down cleanly."""
        bonus_percent = getattr(self.owner.stats, "pet_attack_percent", 0)
        if bonus_percent == 0:
            return self.stats
        boosted = copy.copy(self.stats)
        boosted.attack *= 1 + bonus_percent / 100
        return boosted

    def take_damage(self, amount, attacker=None):
        super().take_damage(amount, attacker=attacker, flash_color=(255, 235, 90))

    def update(self, dt, enemies, arena_rect):
        self.spawn_timer = max(0.0, self.spawn_timer - dt)
        self.contact_cooldown_timer = max(0.0, self.contact_cooldown_timer - dt)
        self.retarget_timer -= dt

        if self.retarget_timer <= 0:
            living = [enemy for enemy in enemies if enemy.alive]
            if living:
                target = min(living, key=lambda enemy: math.hypot(
                    enemy.x - self.x, enemy.y - self.y))
                dx, dy = target.x - self.x, target.y - self.y
                dist = math.hypot(dx, dy) or 1.0
                speed = self.movement_speed
                self.vx = dx / dist * speed
                self.vy = dy / dist * speed
            self.retarget_timer = random.uniform(self.RETARGET_MIN, self.RETARGET_MAX)

        self.x += self.vx * dt
        self.y += self.vy * dt
        bounce_off_walls(self, arena_rect)

    def exchange_contact_damage(self, enemy):
        """Trade contact damage with `enemy` on touch, each side gated by
        its own cooldown so overlapping doesn't melt either of them in a
        single frame. Returns True if this killed the enemy."""
        killed = False
        if self.contact_cooldown_timer <= 0:
            dmg, is_crit, dodged = calculate_damage(
                self._effective_attack_stats(), enemy.stats, tags=["contact"])
            if not dodged:
                enemy.take_damage(dmg, attacker=self)
                if not enemy.alive:
                    killed = True
            self.contact_cooldown_timer = self.CONTACT_COOLDOWN

        enemy_cooldown = getattr(enemy, "contact_cooldown_timer", 0.0)
        if enemy_cooldown <= 0 and self.alive:
            dmg, is_crit, dodged = calculate_damage(enemy.stats, self.stats, tags=["contact"])
            if not dodged:
                self.take_damage(dmg, attacker=enemy)
            enemy.contact_cooldown_timer = ContactDamage.HIT_COOLDOWN
        return killed

    def draw(self, surface):
        r = max(1, int(self.radius))
        if self.spawn_timer > 0:
            progress = 1 - self.spawn_timer / SPAWN_POP_DURATION
            scale = max(0.1, ease_out_back(progress))
            r = max(1, int(r * scale))
            padding = 8
            pop_size = (r * 2 + padding * 2, r * 2 + padding * 2)
            pop_surface = pygame.Surface(pop_size, pygame.SRCALPHA)
            center = (pop_size[0] // 2, pop_size[1] // 2)
            pygame.draw.circle(pop_surface, (*SPAWN_FLASH_COLOR, 150), center, r + 5, 3)
            pygame.draw.circle(pop_surface, (*self.color, 255), center, r)
            pygame.draw.circle(pop_surface, (*PET_RING_COLOR, 255), center, r, 2)
            surface.blit(pop_surface, (int(self.x) - center[0], int(self.y) - center[1]))
            return
        center = (int(self.x), int(self.y))
        pygame.draw.circle(surface, self.color, center, r)
        pygame.draw.circle(surface, self.outline_color, center, r, 2)
        pygame.draw.circle(surface, PET_RING_COLOR, center, r + 3, 2)


def respawn_pets(player):
    """Top every one of a player's pet grants back up to its target count,
    spawning any missing pets right next to the player. Call this once at
    the start of each wave (so casualties come back) and immediately when
    a pet-granting card is bought (so it pays off right away)."""
    player.pets = [pet for pet in player.pets if pet.alive]
    for key, target_count in player.pet_grants.items():
        config = PET_CONFIGS.get(key)
        if config is None:
            continue
        alive_count = sum(1 for pet in player.pets
                          if pet.config.key == key and pet.alive)
        for _ in range(target_count - alive_count):
            angle = random.uniform(0, 2 * math.pi)
            offset = player.radius + config.radius + 12
            x = player.x + math.cos(angle) * offset
            y = player.y + math.sin(angle) * offset
            player.pets.append(Pet(x, y, config, player))


def update_player_pets(player, dt, enemies, arena_rect):
    """Advance one player's pets for a frame: chase/movement, contact
    damage traded with enemies, and coin/token payout on a kill. Shared by
    player and player_two so their pet-handling can't drift apart, the
    same way update_player_summons is shared for shuriken summons."""
    for pet in player.pets:
        pet.update(dt, enemies, arena_rect)

    for pet in player.pets:
        if not pet.alive:
            continue
        for enemy in enemies:
            if not enemy.alive:
                continue
            if resolve_circle_collision(pet, enemy):
                if pet.exchange_contact_damage(enemy):
                    player.stats.coin_count += enemy.stats.coin_count
                    award_gray_token(enemy, player)
                    award_token(enemy, player, "blue")

    player.pets = [pet for pet in player.pets if pet.alive]


# ---------------------------------------------------------------------------
# Arena helpers
# ---------------------------------------------------------------------------
def setup_arena_rect(screen_width, screen_height):
    """Build the arena rectangle inset from the screen edges by ARENA_MARGIN."""
    return pygame.Rect(
        ARENA_MARGIN,
        ARENA_MARGIN,
        screen_width - ARENA_MARGIN * 2,
        screen_height - ARENA_MARGIN * 2,
    )

def random_point_in_arena(rect, margin):
    """Random (x, y) inside the arena rectangle, kept `margin` away from walls."""
    x = random.uniform(rect.left + margin, rect.right - margin)
    y = random.uniform(rect.top + margin, rect.bottom - margin)
    return x, y


def draw_arena(surface, rect):
    pygame.draw.rect(surface, ARENA_COLOR, rect)
    pygame.draw.rect(surface, ARENA_BORDER_COLOR, rect, ARENA_BORDER_WIDTH)


def resolve_circle_collision(first, second):
    """Separate two overlapping balls and bounce them along their collision normal."""
    first_speed = math.hypot(first.vx, first.vy)
    second_speed = math.hypot(second.vx, second.vy)
    dx = second.x - first.x
    dy = second.y - first.y
    distance = math.hypot(dx, dy)
    minimum_distance = first.radius + second.radius

    if distance >= minimum_distance:
        return False

    if distance == 0:
        normal_x, normal_y = 1.0, 0.0
        distance = 1.0
    else:
        normal_x, normal_y = dx / distance, dy / distance

    overlap = minimum_distance - distance
    first.x -= normal_x * overlap / 2
    first.y -= normal_y * overlap / 2
    second.x += normal_x * overlap / 2
    second.y += normal_y * overlap / 2

    first_normal_velocity = first.vx * normal_x + first.vy * normal_y
    second_normal_velocity = second.vx * normal_x + second.vy * normal_y
    if first_normal_velocity > 0:
        first.vx -= 2 * first_normal_velocity * normal_x
        first.vy -= 2 * first_normal_velocity * normal_y
    if second_normal_velocity < 0:
        second.vx -= 2 * second_normal_velocity * normal_x
        second.vy -= 2 * second_normal_velocity * normal_y

    keep_movement_speed(first, first_speed)
    keep_movement_speed(second, second_speed)
    return True


def resolve_ball_collisions(player, enemies, arena_rect):
    """Resolve each player/enemy and enemy/enemy pair once per frame."""
    player_collisions = []
    for enemy in enemies:
        if enemy.alive:
            if resolve_circle_collision(player, enemy):
                player_collisions.append(enemy)

    for index, first in enumerate(enemies):
        if not first.alive:
            continue
        for second in enemies[index + 1:]:
            if second.alive:
                if (first.faction == second.faction
                        or first.pass_through_enemies
                        or second.pass_through_enemies):
                    continue
                if resolve_circle_collision(first, second):
                    for skill in first.skills:
                        skill.on_entity_collision(first, second)
                    for skill in second.skills:
                        skill.on_entity_collision(second, first)
                    for entity, other in ((first, second), (second, first)):
                        handler = getattr(entity, "body_slam_handler", None)
                        if handler is not None:
                            handler.on_entity_collision(entity, other)

    bounce_off_walls(player, arena_rect)
    for enemy in enemies:
        if enemy.alive:
            bounce_off_walls(enemy, arena_rect)
    return player_collisions


def update_player_summons(player, dt, enemies, arena_rect):
    """Advance one player's summons for a frame. Shared by player and
    player_two so their summon-handling can't drift apart."""
    for summon in player.summons:
        summon.update(dt, arena_rect)
    resolve_summon_collisions(player.summons, enemies, arena_rect)
    for summon in list(player.summons):
        for enemy in summon.try_hit_enemies(enemies):
            player.stats.coin_count += enemy.stats.coin_count
            award_gray_token(enemy, player)
            award_token(enemy, player, "blue")
        if not summon.alive:
            player.summons.extend(summon.split(player.stats))
    player.summons = [s for s in player.summons if s.alive]


def resolve_summon_collisions(summons, enemies, arena_rect):
    for summon in summons:
        if not summon.alive:
            continue
        for enemy in enemies:
            if enemy.alive:
                resolve_shuriken_collision(summon, enemy)
        bounce_off_walls(summon, arena_rect)


def resolve_shuriken_collision(shuriken, enemy):
    """Bounce a shuriken off an enemy without moving the enemy.

    Shurikens can travel far enough in one frame to end up well inside an
    enemy.  A normal two-body collision would push both circles apart and
    can leave the shuriken embedded after one correction.  Treat the enemy
    as a static collider instead: place only the shuriken at the contact
    surface, then reflect its incoming velocity.
    """
    dx = shuriken.x - enemy.x
    dy = shuriken.y - enemy.y
    distance = math.hypot(dx, dy)
    minimum_distance = shuriken.radius + enemy.radius

    if distance >= minimum_distance:
        return False

    if distance == 0:
        speed = math.hypot(shuriken.vx, shuriken.vy)
        if speed > 0:
            normal_x = shuriken.vx / speed
            normal_y = shuriken.vy / speed
        else:
            normal_x, normal_y = 1.0, 0.0
    else:
        normal_x, normal_y = dx / distance, dy / distance

    shuriken.x = enemy.x + normal_x * minimum_distance
    shuriken.y = enemy.y + normal_y * minimum_distance

    incoming_velocity = shuriken.vx * normal_x + shuriken.vy * normal_y
    if incoming_velocity < 0:
        shuriken.vx -= 2 * incoming_velocity * normal_x
        shuriken.vy -= 2 * incoming_velocity * normal_y
    return True


def award_token(enemy, player, token_type):
    """Roll an enemy's token drop and the matching player pickup chance."""
    percent_attribute = f"{token_type}_token_percent"
    token_attribute = f"{token_type}_tokens"
    drop_count = (enemy.config.blue_token_drop_count
                  if token_type == "blue" else 1)
    if random.uniform(0, 100) >= getattr(enemy.stats, percent_attribute):
        return False

    pickup_chance = max(0.0, getattr(player.stats, percent_attribute))
    awarded = 0
    for _ in range(drop_count):
        if random.uniform(0, 100) >= min(100.0, pickup_chance):
            continue
        setattr(player.stats, token_attribute,
                getattr(player.stats, token_attribute) + 1)
        awarded += 1
        bonus_chance = max(0.0, pickup_chance - 100.0)
        while bonus_chance > 0 and random.uniform(0, 100) < min(100.0, bonus_chance):
            setattr(player.stats, token_attribute,
                    getattr(player.stats, token_attribute) + 1)
            awarded += 1
            bonus_chance -= 100.0
    return awarded > 0


def award_gray_token(enemy, player):
    return award_token(enemy, player, "gray")


class SpawnManager:
    """Owns the current wave number and its spawn queue.

    Each wave, every enemy type eligible for that wave (wave_number >=
    its spawn_rule.start_wave) rolls a random count between min_per_wave
    and max_per_wave; all of those get shuffled into one queue. Enemies
    trickle in from that queue one at a time - the gap before the next
    one grows with however many enemies are currently alive, so a wave
    with a lot of undefeated enemies takes longer to finish spawning.
    The wave number advances once the queue is fully drained (spawned,
    not necessarily killed), after a short breathing-room pause.
    """

    def __init__(self, enemy_configs, arena_rect, miniboss_configs=None,
                 wave_boss_configs=None, multiplayer=False):
        self.enemy_configs = enemy_configs
        self.miniboss_configs = miniboss_configs or []
        self.wave_boss_configs = wave_boss_configs or []
        self.multiplayer = multiplayer
        self.arena_rect = arena_rect
        self.wave_number = 1
        self.queue = []
        # The wave boss (if any) rolled for the current wave. Held here
        # rather than dropped into the normal queue so main.py can play a
        # full cinematic entrance before it actually appears.
        self.pending_boss_config = None
        self.spawn_timer = 0.0
        self.gap_timer = None  # None while the current wave still has enemies to spawn
        self.post_spawn_elapsed = 0.0
        self.rng = random.Random()
        self._build_wave_queue()

    def _build_wave_queue(self):
        self.queue = []
        for config in self.enemy_configs:
            count = config.spawn_rule.count_for_wave(self.wave_number, self.rng)
            self.queue.extend([config] * count)

        # Only one miniboss *type* per wave: roll among whichever configs
        # are eligible for this wave, then spawn only that one's count
        # (rather than rolling every miniboss config independently, which
        # could stack multiple different minibosses into the same wave).
        eligible_minibosses = [
            config for config in self.miniboss_configs
            if self.wave_number >= config.spawn_rule.start_wave]
        if eligible_minibosses:
            chosen = self.rng.choice(eligible_minibosses)
            count = chosen.spawn_rule.count_for_wave(self.wave_number, self.rng)
            self.queue.extend([chosen] * count)

        self.rng.shuffle(self.queue)
        self.spawn_timer = 0.0
        self.gap_timer = None
        self.post_spawn_elapsed = 0.0

        self.pending_boss_config = None
        if (self.wave_boss_configs and self.wave_number >= WAVE_BOSS_INTERVAL
                and self.wave_number % WAVE_BOSS_INTERVAL == 0):
            self.pending_boss_config = self.rng.choice(self.wave_boss_configs)

    def spawn_boss(self):
        """Build the wave boss rolled for this wave. Call once the boss-intro
        cinematic has finished; returns None if no boss is pending."""
        config = self.pending_boss_config
        self.pending_boss_config = None
        if config is None:
            return None
        x, y = self.arena_rect.centerx, self.arena_rect.centery
        boss = Enemy(x, y, config, self.wave_number,
                     health_multiplier=(MULTIPLAYER_HEALTH_MULTIPLIER
                                        if self.multiplayer else 1.0))
        boss.spawn_timer = BOSS_SPAWN_POP_DURATION
        return boss

    def _spawn_next(self):
        config = self.queue.pop(0)
        margin = config.radius + 10
        x, y = random_point_in_arena(self.arena_rect, margin)
        variant_type = None
        variant_chance = (MULTIPLAYER_VARIANT_CHANCE if self.multiplayer
                          else GREEN_PIP_VARIANT_CHANCE)
        if config.key == "green_pip" and random.random() < variant_chance:
            variant_type = random.randint(1, 5)
        return Enemy(x, y, config, self.wave_number,
                     variant_type=variant_type,
                     health_multiplier=(MULTIPLAYER_HEALTH_MULTIPLIER
                                        if self.multiplayer else 1.0))

    def update(self, dt, alive_count):
        """Returns a newly spawned Enemy this frame, or None."""
        if self.queue:
            self.spawn_timer -= dt
            if self.spawn_timer <= 0:
                enemy = self._spawn_next()
                interval = SPAWN_BASE_INTERVAL + SPAWN_ALIVE_SCALE * alive_count
                self.spawn_timer = min(interval, SPAWN_INTERVAL_MAX)
                return enemy
            return None

        # A wave is complete only after its queue is drained and every
        # enemy from that wave has been defeated.
        self.post_spawn_elapsed += dt
        if alive_count > 0:
            self.gap_timer = None
            return None

        # Queue is empty and no enemies remain: hold briefly, then move on.
        if self.gap_timer is None:
            progress = min(1.0, self.post_spawn_elapsed / POST_SPAWN_ACCELERATION_TIME)
            self.gap_timer = WAVE_GAP_MAX - (WAVE_GAP_MAX - WAVE_GAP_MIN) * progress
        else:
            self.gap_timer -= dt
            if self.gap_timer <= 0:
                self.wave_number += 1
                self._build_wave_queue()
        return None


# ---------------------------------------------------------------------------
# Background decoration (low-opacity grid + drifting particles)
# ---------------------------------------------------------------------------
def build_grid_surface(width, height):
    """Pre-render a faint grid onto a transparent surface (drawn once, reused)."""
    grid_surf = pygame.Surface((width, height), pygame.SRCALPHA)
    for i, x in enumerate(range(0, width, GRID_SPACING)):
        color = GRID_COLOR_ACCENT if i % 4 == 0 else GRID_COLOR
        pygame.draw.line(grid_surf, color, (x, 0), (x, height))
    for i, y in enumerate(range(0, height, GRID_SPACING)):
        color = GRID_COLOR_ACCENT if i % 4 == 0 else GRID_COLOR
        pygame.draw.line(grid_surf, color, (0, y), (width, y))
    return grid_surf


class DriftParticle:
    """A tiny, faint dot slowly floating across the background."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.x = random.uniform(0, width)
        self.y = random.uniform(0, height)
        self.radius = random.uniform(PARTICLE_MIN_RADIUS, PARTICLE_MAX_RADIUS)
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(PARTICLE_MIN_SPEED, PARTICLE_MAX_SPEED)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed

    def update(self, dt):
        self.x = (self.x + self.vx * dt) % self.width
        self.y = (self.y + self.vy * dt) % self.height

    def draw(self, surface):
        # Drawn onto a per-pixel-alpha surface (see particle_layer in main())
        # since pygame ignores alpha when drawing straight onto the display.
        pygame.draw.circle(surface, PARTICLE_COLOR, (int(self.x), int(self.y)), self.radius)


# ---------------------------------------------------------------------------
# Intro state machine
# ---------------------------------------------------------------------------
STATE_PRE_MOVE = "pre_move"           # ball is still sitting still
STATE_MAIN_MENU = "main_menu"         # title screen before a run starts
STATE_MOVING_PRE_READY = "moving"     # ball has started moving, waiting on the banner
STATE_READY_BANNER = "ready_banner"   # fullscreen READY banner is showing
STATE_PLAYING = "playing"             # normal gameplay
STATE_DEAD = "dead"                   # gameplay is frozen on the death screen
STATE_CARD_SELECT = "card_select"     # player chooses a post-wave upgrade
STATE_BOSS_INTRO = "boss_intro"       # cinematic entrance for a wave boss


def ease_out_back(t):
    """Overshoot easing: rockets past 1.0 then settles - great for a punch-in."""
    c1 = 1.70158
    c3 = c1 + 1
    t -= 1
    return 1 + c3 * (t ** 3) + c1 * (t ** 2)


class Card:
    """A weighted upgrade with pool, prerequisites, and repeat behavior."""

    def __init__(self, key, name, token_type, weight, effect,
                 prerequisites=(), max_purchases=None, indicator="+",
                 description=""):
        self.key = key
        self.name = name
        self.token_type = token_type
        self.weight = weight
        self.effect = effect
        self.prerequisites = tuple(prerequisites)
        self.max_purchases = max_purchases
        self.indicator = indicator
        self.description = description

    def apply(self, player):
        self.effect(player)
        player.unlocked_cards.add(self.key)
        player.card_purchases[self.key] = player.card_purchases.get(self.key, 0) + 1

    @property
    def repeatable(self):
        return self.max_purchases is None

    def purchase_count(self, player):
        return player.card_purchases.get(self.key, 0)

    def spend_token(self, player):
        token_attribute = f"{self.token_type}_tokens"
        token_count = getattr(player.stats, token_attribute, 0)
        if token_count <= 0 or (self.max_purchases is not None
                    and self.purchase_count(player) >= self.max_purchases):
            return False
        setattr(player.stats, token_attribute, token_count - 1)
        self.apply(player)
        return True


class SlamRipple:
    """A fading orange ring left by an actively body-slammed entity."""

    LIFETIME = 0.55

    def __init__(self, x, y, radius):
        self.x = x
        self.y = y
        self.radius = radius
        self.age = 0.0

    def update(self, dt):
        self.age += dt

    @property
    def alive(self):
        return self.age < self.LIFETIME

    def draw(self, surface):
        progress = min(1.0, self.age / self.LIFETIME)
        radius = max(1, int(self.radius * (1 + progress * 0.2)))
        alpha = int(210 * (1 - progress))
        padding = 8
        size = radius * 2 + padding * 2
        ripple_surface = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(ripple_surface, (255, 145, 30, alpha),
                           (size // 2, size // 2), radius, 3)
        surface.blit(ripple_surface,
                     (int(self.x) - size // 2, int(self.y) - size // 2))


def update_slam_ripples(entity, dt):
    ripples = getattr(entity, "slam_ripples", [])
    for ripple in ripples:
        ripple.update(dt)
    ripples = [ripple for ripple in ripples if ripple.alive]

    if getattr(entity, "body_slam_pending", False):
        entity.slam_ripple_timer -= dt
        while entity.slam_ripple_timer <= 0:
            ripples.append(SlamRipple(entity.x, entity.y, entity.radius))
            entity.slam_ripple_timer += 0.8
    entity.slam_ripples = ripples


def draw_slam_ripples(surface, entity):
    for ripple in getattr(entity, "slam_ripples", []):
        ripple.draw(surface)


def stat_card(key, name, stat_name, amount, weight):
    return Card(key, name, "gray", weight,
                lambda player: setattr(
                    player.stats, stat_name,
                    getattr(player.stats, stat_name) + amount),
                max_purchases=None)


CARD_CATALOG = (
    stat_card("max_hp", "MAX HP +10", "max_hp", 10, 10),
    stat_card("crit_rate", "CRIT RATE +2%", "crit_rate", 2, 10),
    stat_card("attack", "ATK +5", "attack", 5, 8),
    stat_card("crit_damage", "CRIT DAMAGE +15%", "crit_damage", 15, 7),
    stat_card("defence", "DEFENCE +1", "defence", 1, 7),
    stat_card("hp_regen", "HP REGEN +0.2", "hp_regen", 0.2, 5),
    stat_card("move_speed", "MOVE SPEED +2", "move_speed", 2, 5),
    stat_card("attack_speed", "ATTACK SPEED +2", "attack_speed", 2, 5),
    Card(
        "contact_bump", "CONTACT BUMP", "blue", 10,
        lambda player: (setattr(player.stats, "contact_damage_percent", 40),
                        player.add_skill("contact_damage")),
        max_purchases=1, indicator="SKILL",
        description="When enemies hit your body, deal 40% of your damage back.",
    ),
    Card(
        "bump_up", "BUMP UP +5%", "blue", 14,
        lambda player: setattr(
            player.stats, "contact_damage_percent",
            player.stats.contact_damage_percent + 5),
        prerequisites=("contact_bump",), max_purchases=None, indicator="REPEAT",
        description="Increase Contact Bump damage scaling by 5%. Repeatable.",
    ),
    Card(
        "body_slam", "BODY SLAM", "blue", 2,
        lambda player: (setattr(player.stats, "body_slam_enabled", True),
                player.add_skill("body_slam")),
        prerequisites=("contact_bump",), max_purchases=1, indicator="SKILL",
        description="Bumps boost enemy speed and deal impact damage on collision.",
    ),
    Card(
        "reslamming", "RESLAMMING!", "blue", 4,
        lambda player: setattr(
            player.stats, "body_slam_extra_impacts",
            player.stats.body_slam_extra_impacts + 1),
        prerequisites=("body_slam",), max_purchases=None, indicator="REPEAT",
        description="Require one more wall or enemy impact before a slam ends.",
    ),
    Card(
        "slam_shark", "SLAM SHARK", "blue", 5,
        lambda player: player.add_skill("slam_shark"),
        prerequisites=("contact_bump",), max_purchases=1, indicator="SKILL",
        description="Eye of Sight grants 80% movement speed for 0.8 seconds.",
    ),
    Card(
        "head_hitter", "HEAD HITTER", "blue", 10,
        lambda player: (setattr(player.stats, "rage_level", player.stats.rage_level + 1),
                        player.add_skill("head_hitter")),
        prerequisites=("slam_shark",), max_purchases=4, indicator="REPEAT",
        description="After a body hit, gain a 20% per-stack chance to dash again. Rage intensifies.",
    ),
    Card(
        "lingering_poison", "LINGERING POISON", "blue", 6,
        lambda player: (setattr(player.stats, "lingering_poison_enabled", True),
                        player.add_skill("lingering_poison")),
        max_purchases=1, indicator="SKILL",
        description="Hits inflict poison for 0.6 attack per second for 3 seconds. Stacks.",
    ),
    Card(
        "shuriken_mastery", "SHURIKEN MASTERY", "blue", 7,
        lambda player: setattr(
            player.stats, "shuriken_mastery", player.stats.shuriken_mastery + 1),
        max_purchases=None, indicator="REPEAT",
        description="Summon one additional full-size shuriken each cast. Repeatable.",
    ),
    Card(
        "mini_shurikens", "MINI SHURIKENS", "blue", 2,
        lambda player: setattr(player.stats, "mini_shurikens_enabled", True),
        max_purchases=1, indicator="SKILL",
        description="When a full-size shuriken dies, it splits into two mini shurikens.",
    ),
    Card(
        "split_formation", "SPLIT FORMATION +1", "blue", 7,
        lambda player: setattr(
            player.stats, "shuriken_split_count",
            player.stats.shuriken_split_count + 1),
        prerequisites=("mini_shurikens",), max_purchases=None, indicator="REPEAT",
        description="Each shuriken split creates one additional mini shuriken. Repeatable.",
    ),
    Card(
        "flagbearer", "FLAGBEARER", "blue", 2,
        lambda player: player.add_skill("flagbearer"),
        max_purchases=1, indicator="SKILL",
        description="Every 0.75s, force-reaim every ally (including shurikens) at the nearest enemy.",
    ),
    Card(
        "flowering_bud", "FLOWERING BUD", "blue", 1,
        lambda player: (setattr(player.stats, "hp_regen", player.stats.hp_regen + 1),
                        player.add_skill("flowering_bud")),
        max_purchases=1, indicator="SKILL",
        description="Gain 1 HP regen. Each enemy you kill permanently adds 0.02 more.",
    ),
    Card(
        "green_pip_pup", "GREEN PIP PUP", "blue", 1,
        lambda player: player.grant_pet("green_pip_pup"),
        max_purchases=1, indicator="SKILL",
        description="Spawn a persistent Green Pip ally (pet tag). Tankier and harder-hitting "
                    "than a normal Green Pip: +100 defence, +500 HP, 0.8x speed, +4 attack.",
    ),
    Card(
        "pet_power", "PET POWER!", "blue", 10,
        lambda player: (
            setattr(player.stats, "pet_speed_percent", player.stats.pet_speed_percent + 20),
            setattr(player.stats, "pet_attack_percent", player.stats.pet_attack_percent + 20),
        ),
        prerequisites=("green_pip_pup",), max_purchases=20, indicator="REPEAT",
        description="Increase the move speed and attack of all pets by 20%. Repeatable up to 20 times.",
    ),
)


def eligible_cards(player, token_type):
    eligible = []
    for card in CARD_CATALOG:
        if card.token_type != token_type:
            continue
        token_count = getattr(player.stats, f"{token_type}_tokens", 0)
        if token_count <= 0:
            continue
        if (card.max_purchases is not None
            and card.purchase_count(player) >= card.max_purchases):
            continue
        if not all(requirement in player.unlocked_cards
                   for requirement in card.prerequisites):
            continue
        eligible.append(card)
    return eligible


def active_card_pool(player):
    if player.stats.gray_tokens > 0 and eligible_cards(player, "gray"):
        return "gray"
    if player.stats.blue_tokens > 0 and eligible_cards(player, "blue"):
        return "blue"
    return None


def roll_cards(player, token_type):
    """Roll three cards from one token pool, keeping offers unique when possible."""
    pool = eligible_cards(player, token_type)
    if not pool:
        return []
    if len(pool) < CARD_COUNT:
        return random.choices(pool, weights=[card.weight for card in pool],
                              k=CARD_COUNT)

    remaining = list(pool)
    result = []
    for _ in range(CARD_COUNT):
        card = random.choices(remaining,
                              weights=[entry.weight for entry in remaining],
                              k=1)[0]
        result.append(card)
        remaining.remove(card)
    return result


def draw_card_select_screen(surface, title_font, card_font, token_font,
                            screen_width, screen_height, cards, player, token_type):
    overlay = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
    overlay.fill((7, 9, 15, 242))
    surface.blit(overlay, (0, 0))

    pygame.draw.line(surface, (110, 125, 155),
                     (screen_width // 2 - 250, screen_height // 2 - 215),
                     (screen_width // 2 + 250, screen_height // 2 - 215), 2)

    title = title_font.render("CHOOSE AN UPGRADE", True, (245, 245, 250))
    surface.blit(title, title.get_rect(center=(screen_width // 2, screen_height // 2 - 190)))
    token_count = getattr(player.stats, f"{token_type}_tokens")
    token_text = token_font.render(f"{token_type.upper()} TOKENS: {token_count}", True,
                                  CARD_POOL_COLORS[token_type])
    surface.blit(token_text, token_text.get_rect(center=(screen_width // 2, screen_height // 2 - 145)))

    card_width = min(340 if token_type == "blue" else 260,
                     (screen_width - 120) // CARD_COUNT)
    card_height = 280 if token_type == "blue" else 220
    gap = 20
    first_x = (screen_width - (card_width * len(cards) + gap * (len(cards) - 1))) // 2
    top = screen_height // 2 - card_height // 2
    description_font = pygame.font.SysFont("arial", 17, bold=False)
    for index, card in enumerate(cards):
        rect = pygame.Rect(first_x + index * (card_width + gap), top,
                           card_width, card_height)
        shadow = rect.move(0, 8)
        pygame.draw.rect(surface, (2, 3, 7), shadow, border_radius=8)
        accent = CARD_POOL_COLORS.get(card.token_type, (170, 180, 200))
        pygame.draw.rect(surface, (29, 36, 50), rect, border_radius=8)
        pygame.draw.rect(surface, accent, rect, 3, border_radius=8)
        pygame.draw.rect(surface, (*accent, 35), (rect.x, rect.y, rect.width, 8))
        number = card_font.render(str(index + 1), True, (255, 215, 80))
        name = card_font.render(card.name, True, (245, 245, 250))
        pool = token_font.render(f"{card.token_type.upper()} TOKEN  -  1", True, accent)
        if card.max_purchases is None:
            purchase_label = "infinity"
        else:
            purchase_label = f"{card.purchase_count(player)}/{card.max_purchases}"
        indicator = token_font.render(purchase_label, True, accent)
        surface.blit(number, number.get_rect(topleft=(rect.left + 16, rect.top + 16)))
        surface.blit(name, name.get_rect(center=(rect.centerx, rect.top + 58)))
        description_lines = []
        words = card.description.split()
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if description_font.size(candidate)[0] <= rect.width - 28:
                line = candidate
            else:
                description_lines.append(line)
                line = word
        if line:
            description_lines.append(line)
        description_y = rect.top + 92
        for line in description_lines[:4]:
            description = description_font.render(line, True, (215, 220, 230))
            surface.blit(description, description.get_rect(center=(rect.centerx, description_y)))
            description_y += 20
        surface.blit(pool, pool.get_rect(center=(rect.centerx, rect.bottom - 35)))
        surface.blit(indicator, indicator.get_rect(bottomright=(rect.right - 12, rect.bottom - 10)))

    prompt = token_font.render("PRESS 1, 2, OR 3 TO SPEND A TOKEN", True, (210, 215, 225))
    surface.blit(prompt, prompt.get_rect(center=(screen_width // 2, screen_height // 2 + 175)))


def draw_main_menu(surface, title_font, info_font, screen_width, screen_height,
                   multiplayer_enabled):
    surface.fill((7, 9, 15))
    title = title_font.render("BALL BRAWLERS", True, (245, 245, 250))
    surface.blit(title, title.get_rect(center=(screen_width // 2, screen_height // 2 - 120)))
    play = info_font.render("ENTER / P  PLAY", True, (120, 240, 140))
    mode = info_font.render(
        f"M  MULTIPLAYER: {'ON' if multiplayer_enabled else 'OFF'}",
        True, (120, 190, 255))
    exit_text = info_font.render("ESC / X  EXIT", True, (240, 120, 110))
    surface.blit(play, play.get_rect(center=(screen_width // 2, screen_height // 2)))
    surface.blit(mode, mode.get_rect(center=(screen_width // 2, screen_height // 2 + 55)))
    surface.blit(exit_text, exit_text.get_rect(center=(screen_width // 2, screen_height // 2 + 110)))


class DamageNumber:
    """A damage value that rises, falls under gravity, and fades away."""

    def __init__(self, amount, x, y, color):
        self.amount = amount
        self.x = x
        self.y = y
        self.color = color
        self.age = 0.0
        self.velocity_y = DAMAGE_TEXT_RISE_SPEED

    def update(self, dt):
        self.age += dt
        self.y += self.velocity_y * dt
        self.velocity_y += DAMAGE_TEXT_GRAVITY * dt

    @property
    def alive(self):
        return self.age < DAMAGE_TEXT_LIFETIME

    def draw(self, surface, font):
        progress = min(1.0, self.age / DAMAGE_TEXT_LIFETIME)
        scale = 1 + min(abs(self.amount) / DAMAGE_TEXT_SCALE_DAMAGE, 1.0) * (DAMAGE_TEXT_MAX_SCALE - 1)
        size = max(1, int(DAMAGE_TEXT_BASE_SIZE * scale))
        text = font.render(str(int(round(self.amount))), True, self.color)
        base_width, base_height = text.get_size()
        text = pygame.transform.smoothscale(
            text, (max(1, int(base_width * size / DAMAGE_TEXT_BASE_SIZE)),
                   max(1, int(base_height * size / DAMAGE_TEXT_BASE_SIZE))))
        text.set_alpha(int(255 * (1 - progress)))
        rect = text.get_rect(center=(int(self.x), int(self.y)))
        surface.blit(text, rect)


def draw_wave_counter(surface, font, wave_number):
    text_surf = font.render(f"WAVE {wave_number}", True, WAVE_TEXT_COLOR)
    surface.blit(text_surf, (HUD_MARGIN, HUD_MARGIN))


def draw_coin_counter(surface, font, player, screen_width):
    text_surf = font.render(f"COINS: {player.stats.coin_count}", True, COIN_TEXT_COLOR)
    rect = text_surf.get_rect()
    rect.topright = (screen_width - HUD_MARGIN, HUD_MARGIN)
    surface.blit(text_surf, rect)


def draw_token_counter(surface, font, player, screen_width):
    text_surf = font.render(
        f"GRAY: {player.stats.gray_tokens}  BLUE: {player.stats.blue_tokens}",
        True, TOKEN_TEXT_COLOR)
    rect = text_surf.get_rect()
    rect.topright = (screen_width - HUD_MARGIN, HUD_MARGIN + COIN_FONT_SIZE + 8)
    surface.blit(text_surf, rect)


def draw_player_stat_counter(surface, font, player, screen_height):
    """Draw a semi-transparent live player stat counter at middle-left."""
    rows = [
        ("HP", f"{int(player.stats.hp)} / {int(player.stats.max_hp)}"),
        ("ATK", f"{player.stats.attack:g}"),
        ("DEF", f"{player.stats.defence:g}"),
        ("SPD", f"{player.stats.move_speed:g}"),
        ("CRIT", f"{player.stats.crit_rate:g}%"),
        ("CRIT DMG", f"{player.stats.crit_damage:g}%"),
        ("GRAY", f"{player.stats.gray_tokens}"),
    ]
    row_height = 21
    start_y = screen_height // 2 - row_height * len(rows) // 2
    for index, (label, value) in enumerate(rows):
        y = start_y + index * row_height
        label_surface = font.render(label, True, (175, 185, 200))
        value_surface = font.render(value, True, (245, 245, 250))
        label_surface.set_alpha(PLAYER_STAT_ALPHA)
        value_surface.set_alpha(PLAYER_STAT_ALPHA)
        surface.blit(label_surface, (HUD_MARGIN, y))
        surface.blit(value_surface, (HUD_MARGIN + 78, y))


def hp_percent(stats):
    """Shared clamp-to-[0,1] helper for anything with hp/max_hp."""
    if stats.max_hp <= 0:
        return 0.0
    return max(0.0, min(1.0, stats.hp / stats.max_hp))


def draw_hp_bar(surface, rect, pct, bg_color, fill_color, border_color,
                border_radius=0, border_width=3):
    """Generic HP bar: background rect, proportional fill, border. Used by
    the enemy, player, and boss health bars - only sizing/colors/text
    differ between them."""
    pct = max(0.0, min(1.0, pct))
    fill_rect = pygame.Rect(rect.x, rect.y, int(rect.width * pct), rect.height)
    pygame.draw.rect(surface, bg_color, rect, border_radius=border_radius)
    if fill_rect.width > 0:
        pygame.draw.rect(surface, fill_color, fill_rect, border_radius=border_radius)
    pygame.draw.rect(surface, border_color, rect, border_width, border_radius=border_radius)


def draw_enemy_health_bar(surface, enemy):
    """Draw a small HP bar above an enemy's current visual radius."""
    if not enemy.alive or enemy.stats.max_hp <= 0:
        return
    percent = hp_percent(enemy.stats)
    width = max(ENEMY_HEALTHBAR_WIDTH, int(enemy.radius * 2.2))
    rect = pygame.Rect(int(enemy.x - width / 2),
                       int(enemy.y - enemy.radius - ENEMY_HEALTHBAR_HEIGHT - 5),
                       width, ENEMY_HEALTHBAR_HEIGHT)
    fill_color = (75, 220, 95) if percent > 0.5 else (235, 80, 65)
    draw_hp_bar(surface, rect, percent, (35, 20, 25), fill_color,
               (225, 225, 230), border_radius=2, border_width=1)


def draw_health_bar(surface, font, ball, screen_height):
    bar_x = HUD_MARGIN
    bar_y = screen_height - HUD_MARGIN - HEALTHBAR_HEIGHT
    pct = hp_percent(ball.stats)

    if pct > 0.5:
        fill_color = HEALTHBAR_HIGH_COLOR
    elif pct > 0.25:
        fill_color = HEALTHBAR_MID_COLOR
    else:
        fill_color = HEALTHBAR_LOW_COLOR

    bg_rect = pygame.Rect(bar_x, bar_y, HEALTHBAR_WIDTH, HEALTHBAR_HEIGHT)
    draw_hp_bar(surface, bg_rect, pct, HEALTHBAR_BG_COLOR, fill_color,
               HEALTHBAR_BORDER_COLOR, border_radius=6, border_width=3)

    hp_text = font.render(f"{int(ball.stats.hp)} / {int(ball.stats.max_hp)}", True, HEALTHBAR_TEXT_COLOR)
    text_rect = hp_text.get_rect(center=bg_rect.center)
    surface.blit(hp_text, text_rect)


def draw_death_screen(surface, title_font, info_font, screen_width, screen_height,
                      wave_number, coin_count):
    """Draw a frozen run summary over the last gameplay frame."""
    overlay = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
    overlay.fill((8, 8, 12, 205))
    surface.blit(overlay, (0, 0))

    title = title_font.render("GAME OVER", True, (255, 90, 75))
    title_rect = title.get_rect(center=(screen_width // 2, screen_height // 2 - 90))
    surface.blit(title, title_rect)

    summary = info_font.render(f"WAVE {wave_number}   COINS {coin_count}", True,
                               (245, 245, 250))
    summary_rect = summary.get_rect(center=(screen_width // 2, screen_height // 2))
    surface.blit(summary, summary_rect)

    prompt = info_font.render("R / ENTER TO RESTART    ESC TO EXIT", True, (210, 210, 220))
    prompt_rect = prompt.get_rect(center=(screen_width // 2, screen_height // 2 + 75))
    surface.blit(prompt, prompt_rect)


def draw_boss_health_bar(surface, font, boss, screen_width):
    """Big top-center health bar with the boss's name, shown while any
    wave boss is alive - separate from the small floating enemy bars."""
    if not boss.alive or boss.stats.max_hp <= 0:
        return
    pct = hp_percent(boss.stats)
    bar_x = screen_width // 2 - BOSS_HEALTHBAR_WIDTH // 2
    bar_y = HUD_MARGIN + 6
    bg_rect = pygame.Rect(bar_x, bar_y, BOSS_HEALTHBAR_WIDTH, BOSS_HEALTHBAR_HEIGHT)
    draw_hp_bar(surface, bg_rect, pct, (25, 15, 30), boss.config.base_color,
               (235, 225, 245), border_radius=6, border_width=3)
    name_text = font.render(boss.config.display_name.upper(), True, (240, 225, 250))
    surface.blit(name_text, name_text.get_rect(midbottom=(screen_width // 2, bar_y - 4)))


def get_boss_shake_offset(state_timer):
    """Heavier, slightly longer camera shake than the READY banner's, to
    sell the weight of a boss dropping in."""
    if state_timer >= BOSS_INTRO_SHAKE_DURATION:
        return 0, 0
    amplitude = BOSS_INTRO_SHAKE_MAGNITUDE * (1 - state_timer / BOSS_INTRO_SHAKE_DURATION)
    return random.uniform(-amplitude, amplitude), random.uniform(-amplitude, amplitude)


def draw_boss_intro(surface, name_font, sub_font, warn_font, screen_width, screen_height,
                     state_timer, boss_config):
    """Two-beat boss cinematic: a hazard-striped 'WARNING' beat, then the
    boss's name slamming in (in its own color) before cutting to gameplay."""
    cx, cy = screen_width // 2, screen_height // 2
    overlay = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)

    name_start = BOSS_INTRO_WARNING_TIME
    name_hold_end = name_start + BOSS_INTRO_SCALE_IN_TIME + BOSS_INTRO_HOLD_TIME
    boss_color = boss_config.base_color

    if state_timer < name_start:
        # --- Phase 1: hazard warning ---
        progress = state_timer / max(name_start, 0.0001)
        overlay.fill((25, 5, 20, 210))

        stripe_offset = state_timer * 220
        stripe_width = 46
        diag = pygame.Surface((screen_width, 90), pygame.SRCALPHA)
        for i in range(-2, int(screen_width / stripe_width) + 3):
            x = i * stripe_width * 2 + stripe_offset % (stripe_width * 2)
            pygame.draw.polygon(
                diag, (255, 190, 40, 210),
                [(x, 0), (x + stripe_width, 0), (x - 40, 90), (x - 40 - stripe_width, 90)])
        overlay.blit(diag, (0, cy - 45))

        pulse = (math.sin(state_timer * 24) + 1) / 2
        warn_color = (255, int(60 + 40 * pulse), int(60 + 40 * pulse))
        warn_text = warn_font.render("WARNING", True, warn_color)
        overlay.blit(warn_text, warn_text.get_rect(center=(cx, cy - 110)))

        sub_text = sub_font.render("A CHALLENGER APPROACHES", True, (240, 235, 245))
        sub_text.set_alpha(int(255 * min(1.0, progress * 2)))
        overlay.blit(sub_text, sub_text.get_rect(center=(cx, cy + 100)))
    else:
        # --- Phase 2: name slam ---
        t = state_timer - name_start
        overlay.fill((15, 5, 15, 180))

        if t < BOSS_INTRO_SCALE_IN_TIME:
            progress = t / BOSS_INTRO_SCALE_IN_TIME
            scale = max(ease_out_back(progress), 0.05)
            alpha = min(1.0, progress / 0.5)
        elif state_timer < name_hold_end:
            scale = 1.0
            alpha = 1.0
        else:
            fade_t = (state_timer - name_hold_end) / max(BOSS_INTRO_FADE_OUT_TIME, 0.0001)
            fade_t = min(fade_t, 1.0)
            scale = 1.0 + fade_t * 0.6
            alpha = 1.0 - fade_t

        color_idx = int(t * BOSS_NAME_COLOR_CYCLE_SPEED) % len(BOSS_NAME_COLOR_CYCLE)
        main_color = BOSS_NAME_COLOR_CYCLE[color_idx]
        outline_color = tuple(max(0, c // 4) for c in boss_color)

        base_text = name_font.render(boss_config.display_name.upper(), True, main_color)
        outline_text = name_font.render(boss_config.display_name.upper(), True, outline_color)
        w, h = base_text.get_size()
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        scaled_main = pygame.transform.smoothscale(base_text, new_size)
        scaled_outline = pygame.transform.smoothscale(outline_text, new_size)
        scaled_main.set_alpha(int(255 * alpha))
        scaled_outline.set_alpha(int(255 * alpha))
        rect = scaled_main.get_rect(center=(cx, cy - 10))
        for ox, oy in [(-4, -4), (4, -4), (-4, 4), (4, 4), (0, -6), (0, 6), (-6, 0), (6, 0)]:
            overlay.blit(scaled_outline, (rect.x + ox, rect.y + oy))
        overlay.blit(scaled_main, rect)

        sub_text = sub_font.render("WAVE BOSS", True, boss_color)
        sub_text.set_alpha(int(255 * alpha))
        overlay.blit(sub_text, sub_text.get_rect(center=(cx, cy + 70)))

        bar_width = 360
        bar_surface = pygame.Surface((bar_width, 4), pygame.SRCALPHA)
        pygame.draw.rect(bar_surface, (*boss_color, int(255 * alpha)), bar_surface.get_rect())
        overlay.blit(bar_surface, (cx - bar_width // 2, cy + 100))

    surface.blit(overlay, (0, 0))

    if state_timer < BOSS_INTRO_FLASH_DURATION:
        flash_alpha = int(255 * (1 - state_timer / BOSS_INTRO_FLASH_DURATION))
        flash = pygame.Surface((screen_width, screen_height))
        flash.fill((255, 255, 255))
        flash.set_alpha(flash_alpha)
        surface.blit(flash, (0, 0))


def get_ready_shake_offset(state_timer):
    """Camera-shake offset, strongest at the impact moment and decaying fast."""
    if state_timer >= READY_SHAKE_DURATION:
        return 0, 0
    amplitude = READY_SHAKE_MAGNITUDE * (1 - state_timer / READY_SHAKE_DURATION)
    return random.uniform(-amplitude, amplitude), random.uniform(-amplitude, amplitude)


def draw_ready_banner(surface, font, screen_width, screen_height, state_timer, total_duration):
    """Fast, punchy, over-the-top hype banner: flash, shake, starburst, scale-punch text."""
    cx, cy = screen_width // 2, screen_height // 2

    hold_time = max(0.0, total_duration - READY_SCALE_IN_TIME - READY_FADE_OUT_TIME)

    overlay = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)

    # Pulsing dark-red tint so the whole screen feels charged with energy.
    pulse = (math.sin(state_timer * 30) + 1) / 2
    overlay.fill((60, 10, 10, int(90 + 60 * pulse)))

    # Spinning starburst / speed lines radiating from the center.
    num_lines = 18
    rotation = state_timer * 260  # degrees/sec
    max_len = math.hypot(screen_width, screen_height)
    for i in range(num_lines):
        angle = math.radians(rotation + i * (360 / num_lines))
        x2 = cx + math.cos(angle) * max_len
        y2 = cy + math.sin(angle) * max_len
        pygame.draw.line(overlay, (255, 160, 40, 90), (cx, cy), (x2, y2), 4)

    # --- Scale / alpha timeline: punch in -> hold -> burst out ---
    if state_timer < READY_SCALE_IN_TIME:
        t = state_timer / READY_SCALE_IN_TIME
        scale = max(ease_out_back(t), 0.05)
        alpha = min(1.0, t / 0.5)
    elif state_timer < READY_SCALE_IN_TIME + hold_time:
        scale = 1.0
        alpha = 1.0
    else:
        t = (state_timer - READY_SCALE_IN_TIME - hold_time) / max(READY_FADE_OUT_TIME, 0.0001)
        t = min(t, 1.0)
        scale = 1.0 + t * 0.8
        alpha = 1.0 - t

    # Rapid color flashing between hot colors for extra hype.
    color_idx = int(state_timer * READY_COLOR_CYCLE_SPEED) % len(READY_FLASH_COLORS)
    main_color = READY_FLASH_COLORS[color_idx]

    base_text = font.render("READY", True, main_color)
    outline_text = font.render("READY", True, (110, 15, 10))

    w, h = base_text.get_size()
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    scaled_main = pygame.transform.smoothscale(base_text, new_size)
    scaled_outline = pygame.transform.smoothscale(outline_text, new_size)

    scaled_main.set_alpha(int(255 * alpha))
    scaled_outline.set_alpha(int(255 * alpha))

    rect = scaled_main.get_rect(center=(cx, cy))

    # Bold comic-style outline: stamp the outline copy in a ring around the main text.
    for ox, oy in [(-4, -4), (4, -4), (-4, 4), (4, 4), (0, -6), (0, 6), (-6, 0), (6, 0)]:
        overlay.blit(scaled_outline, (rect.x + ox, rect.y + oy))
    overlay.blit(scaled_main, rect)

    surface.blit(overlay, (0, 0))

    # Pure white impact flash on the very first frames - the "hit" moment.
    if state_timer < READY_FLASH_DURATION:
        flash_alpha = int(255 * (1 - state_timer / READY_FLASH_DURATION))
        flash = pygame.Surface((screen_width, screen_height))
        flash.fill((255, 255, 255))
        flash.set_alpha(flash_alpha)
        surface.blit(flash, (0, 0))


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    screen_width, screen_height = screen.get_size()
    pygame.display.set_caption("Ball Brawlers")
    clock = pygame.time.Clock()

    arena_rect = setup_arena_rect(screen_width, screen_height)

    # Faint decorative background, built once and reused every frame.
    grid_surface = build_grid_surface(screen_width, screen_height)
    particles = [DriftParticle(screen_width, screen_height) for _ in range(NUM_DRIFT_PARTICLES)]
    # Particles need a per-pixel-alpha surface, since pygame.draw ignores
    # alpha when drawing straight onto the (opaque) main display surface.
    particle_layer = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)

    # Fonts
    wave_font = pygame.font.SysFont("arial", WAVE_FONT_SIZE, bold=True)
    hp_font = pygame.font.SysFont("arial", 18, bold=True)
    coin_font = pygame.font.SysFont("arial", COIN_FONT_SIZE, bold=True)
    token_font = pygame.font.SysFont("arial", TOKEN_FONT_SIZE, bold=True)
    card_font = pygame.font.SysFont("arial", 24, bold=True)
    player_stat_font = pygame.font.SysFont("arial", PLAYER_STAT_FONT_SIZE, bold=True)
    ready_font_size = int(screen_height * 0.2)
    ready_font = pygame.font.SysFont("arial", ready_font_size, bold=True)
    game_over_font = pygame.font.SysFont("arial", int(screen_height * 0.11), bold=True)
    death_info_font = pygame.font.SysFont("arial", 30, bold=True)
    damage_font = pygame.font.SysFont("arial", DAMAGE_TEXT_BASE_SIZE, bold=True)
    boss_name_font = pygame.font.SysFont("arial", int(screen_height * 0.13), bold=True)
    boss_warn_font = pygame.font.SysFont("arial", int(screen_height * 0.07), bold=True)
    boss_sub_font = pygame.font.SysFont("arial", int(screen_height * 0.035), bold=True)
    boss_health_font = pygame.font.SysFont("arial", 22, bold=True)

    # Everything except the READY overlay is drawn onto this surface first so
    # the whole scene can be shaken as one unit during the hype banner.
    world_surface = pygame.Surface((screen_width, screen_height))

    # Spawn the green player ball at a random spot inside the arena,
    # leaving room so the ball + sword reach stay inside the wall.
    spawn_margin = BALL_RADIUS + SWORD_LENGTH
    px, py = random_point_in_arena(arena_rect, spawn_margin)
    player = Ball(px, py, BALL_RADIUS, GREEN_BALL_COLOR, GREEN_BALL_OUTLINE, stats=Stats())
    player_two = None
    multiplayer_enabled = False
    active_card_player = 0

    spawn_manager = SpawnManager(ENEMY_CONFIGS, arena_rect, MINIBOSS_CONFIGS,
                                 wave_boss_configs=WAVE_BOSS_CONFIGS,
                                 multiplayer=multiplayer_enabled)
    enemies = []

    # Intro state machine
    state = STATE_MAIN_MENU
    state_timer = 0.0
    damage_numbers = []
    offered_cards = []
    incoming_boss_config = None  # set while STATE_BOSS_INTRO is playing
    impact_shake_timer = 0.0     # short extra shake punch when the boss lands

    def reset_run():
        nonlocal player, player_two, spawn_manager, enemies, state, state_timer, damage_numbers, offered_cards, active_card_player, incoming_boss_config, impact_shake_timer
        px, py = random_point_in_arena(arena_rect, spawn_margin)
        player = Ball(px, py, BALL_RADIUS, GREEN_BALL_COLOR, GREEN_BALL_OUTLINE,
                      stats=Stats())
        player_two = None
        if multiplayer_enabled:
            player_two = Ball(px + 60, py, BALL_RADIUS, (220, 60, 70), (120, 20, 30), stats=Stats())
        spawn_manager = SpawnManager(ENEMY_CONFIGS, arena_rect, MINIBOSS_CONFIGS,
                         wave_boss_configs=WAVE_BOSS_CONFIGS,
                         multiplayer=multiplayer_enabled)
        enemies = []
        state = STATE_PRE_MOVE
        state_timer = 0.0
        damage_numbers = []
        offered_cards = []
        active_card_player = 0
        incoming_boss_config = None
        impact_shake_timer = 0.0

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0  # seconds since last frame

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            elif event.type == pygame.KEYDOWN and state == STATE_MAIN_MENU:
                if event.key in (pygame.K_RETURN, pygame.K_p):
                    reset_run()
                    state = STATE_PRE_MOVE
                    state_timer = 0.0
                elif event.key == pygame.K_m:
                    multiplayer_enabled = not multiplayer_enabled
                elif event.key == pygame.K_x:
                    running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_q:
                if state == STATE_PLAYING:
                    debug_margin = DEBUG_GREEN_PIP_RADIUS + 10
                    debug_x, debug_y = random_point_in_arena(arena_rect, debug_margin)
                    enemies.append(Enemy(debug_x, debug_y, GREEN_PIP,
                                         spawn_manager.wave_number,
                                         debug_stats=True))
            elif (event.type == pygame.KEYDOWN and state == STATE_DEAD
                  and event.key in (pygame.K_r, pygame.K_RETURN)):
                reset_run()
            elif event.type == pygame.KEYDOWN and state == STATE_CARD_SELECT:
                card_player = player if active_card_player == 0 else player_two
                card_index = {
                    pygame.K_1: 0,
                    pygame.K_2: 1,
                    pygame.K_3: 2,
                }.get(event.key)
                if (card_player is not None and card_index is not None
                        and card_index < len(offered_cards)):
                    if offered_cards[card_index].spend_token(card_player):
                        token_type = active_card_pool(card_player)
                        if token_type is not None:
                            offered_cards = roll_cards(card_player, token_type)
                        elif active_card_player == 0 and player_two is not None:
                            active_card_player = 1
                            token_type = active_card_pool(player_two)
                            if token_type is not None:
                                offered_cards = roll_cards(player_two, token_type)
                            else:
                                offered_cards = []
                                state = STATE_PLAYING
                                state_timer = 0.0
                        else:
                            offered_cards = []
                            state = STATE_PLAYING
                            state_timer = 0.0

        # --- Intro state machine ---
        if state not in (STATE_DEAD, STATE_MAIN_MENU):
            state_timer += dt
        if state == STATE_PRE_MOVE and state_timer >= DELAY_BEFORE_MOVE:
            player.start_moving()
            state = STATE_MOVING_PRE_READY
            state_timer = 0.0
        elif state == STATE_MOVING_PRE_READY and state_timer >= DELAY_BEFORE_READY:
            state = STATE_READY_BANNER
            state_timer = 0.0
        elif state == STATE_READY_BANNER and state_timer >= READY_DISPLAY_TIME:
            state = STATE_PLAYING
            state_timer = 0.0
        elif state == STATE_BOSS_INTRO and state_timer >= BOSS_INTRO_DURATION:
            boss_enemy = spawn_manager.spawn_boss()
            if boss_enemy is not None:
                enemies.append(boss_enemy)
                impact_shake_timer = BOSS_SPAWN_SHAKE_DURATION
            token_type = active_card_pool(player)
            if token_type is not None:
                offered_cards = roll_cards(player, token_type)
                state = STATE_CARD_SELECT
            else:
                state = STATE_PLAYING
            state_timer = 0.0

        # --- Updates ---
        if state not in (STATE_DEAD, STATE_MAIN_MENU, STATE_CARD_SELECT,
                         STATE_PLAYING, STATE_BOSS_INTRO):
            player.update(dt, arena_rect, enemies)
        for p in particles:
            p.update(dt)

        if state == STATE_PLAYING:
            previous_wave = spawn_manager.wave_number
            new_enemy = spawn_manager.update(dt, len(enemies))
            if new_enemy is not None:
                enemies.append(new_enemy)

            fast_eye_of_sight = not spawn_manager.queue
            player.eye_of_sight_fast = fast_eye_of_sight
            for enemy in enemies:
                enemy.eye_of_sight_fast = fast_eye_of_sight

            if spawn_manager.wave_number != previous_wave:
                player.stats.hp = player.stats.max_hp
                if player_two is not None:
                    player_two.stats.hp = player_two.stats.max_hp
                active_card_player = 0
                # Pets respawn at the start of every wave.
                respawn_pets(player)
                if player_two is not None:
                    respawn_pets(player_two)
                if spawn_manager.pending_boss_config is not None:
                    # Freeze on a cinematic entrance before this wave's
                    # boss actually appears; card offers (if any) are
                    # resolved once the intro finishes, above.
                    incoming_boss_config = spawn_manager.pending_boss_config
                    state = STATE_BOSS_INTRO
                    state_timer = 0.0
                else:
                    token_type = active_card_pool(player)
                    if token_type is not None:
                        offered_cards = roll_cards(player, token_type)
                        state = STATE_CARD_SELECT
                        state_timer = 0.0

            if state == STATE_PLAYING:
                # Clear last frame's Flagbearer buff-pulse tag from each
                # player's summons before player.update() re-tags whoever's
                # currently in range (mirrors the enemy reset-then-tag pass
                # just below, for the same reason).
                for p in (player, player_two):
                    if p is not None:
                        for summon in p.summons:
                            summon.flagbearer_pulse_progress = None
                player.update(dt, arena_rect, enemies)
                if player_two is not None:
                    player_two.update(dt, arena_rect, enemies)
                # Clear last frame's Flagbearer buff-pulse tag before the
                # update pass re-tags whoever's currently in range - this
                # two-pass reset-then-tag is what lets Flagbearer.update
                # stamp allies regardless of enemy list ordering.
                for enemy in enemies:
                    enemy.flagbearer_pulse_progress = None
                for enemy in enemies:
                    enemy.update(dt, player, arena_rect, enemies)
                for p in (player, player_two):
                    if p is not None:
                        update_player_summons(p, dt, enemies, arena_rect)
                        update_player_pets(p, dt, enemies, arena_rect)

            if state == STATE_PLAYING:
                if player.stats.hp <= 0 and (player_two is None or player_two.stats.hp <= 0):
                    state = STATE_DEAD
                    state_timer = 0.0
                else:
                    for p in (player, player_two):
                        if p is None:
                            continue
                        collided = resolve_ball_collisions(p, enemies, arena_rect)
                        for enemy in collided:
                            enemy.notify_collision(p)
                            p.notify_collision(enemy)

                    if player.stats.hp <= 0:
                        if player_two is None or player_two.stats.hp <= 0:
                            state = STATE_DEAD
                            state_timer = 0.0

                    # NOTE: kept as if/elif to match the original behavior -
                    # when both players are alive, only `player`'s sword
                    # hits are resolved this frame; `player_two`'s sword
                    # only lands once `player` is down. Flagging this as a
                    # likely 2-player bug rather than silently changing it.
                    if state == STATE_PLAYING and player.stats.hp > 0:
                        killed = player.try_hit_enemies(enemies, dt)
                        for enemy in killed:
                            player.stats.coin_count += enemy.stats.coin_count
                            award_gray_token(enemy, player)
                            award_token(enemy, player, "blue")
                    elif state == STATE_PLAYING and player_two is not None:
                        killed = player_two.try_hit_enemies(enemies, dt)
                        for enemy in killed:
                            player_two.stats.coin_count += enemy.stats.coin_count
                            award_gray_token(enemy, player_two)
                            award_token(enemy, player_two, "blue")

            all_pets = list(player.pets) + (list(player_two.pets) if player_two is not None else [])
            for entity in [player, *enemies, *all_pets]:
                for amount, x, y, color in entity.damage_events:
                    damage_numbers.append(DamageNumber(amount, x, y, color))
                entity.damage_events.clear()
                update_slam_ripples(entity, dt)

            enemies = [e for e in enemies if e.alive]

        for damage_number in damage_numbers:
            damage_number.update(dt)
        damage_numbers = [number for number in damage_numbers if number.alive]

        particle_layer.fill((0, 0, 0, 0))  # clear to fully transparent
        for p in particles:
            p.draw(particle_layer)

        # --- Draw ---
        world_surface.fill(BG_COLOR)
        world_surface.blit(grid_surface, (0, 0))
        world_surface.blit(particle_layer, (0, 0))
        draw_arena(world_surface, arena_rect)
        for enemy in enemies:
            draw_slam_ripples(world_surface, enemy)
            enemy.draw(world_surface)
            if not getattr(enemy, "is_wave_boss", False):
                draw_enemy_health_bar(world_surface, enemy)
        draw_slam_ripples(world_surface, player)
        player.draw(world_surface)
        if player_two is not None:
            player_two.draw(world_surface)
        for summon in player.summons:
            summon.draw(world_surface)
        for pet in player.pets:
            pet.draw(world_surface)
            draw_enemy_health_bar(world_surface, pet)
        if player_two is not None:
            for pet in player_two.pets:
                pet.draw(world_surface)
                draw_enemy_health_bar(world_surface, pet)
        for damage_number in damage_numbers:
            damage_number.draw(world_surface, damage_font)
        draw_player_stat_counter(world_surface, player_stat_font, player, screen_height)
        draw_wave_counter(world_surface, wave_font, spawn_manager.wave_number)
        draw_health_bar(world_surface, hp_font, player, screen_height)
        draw_coin_counter(world_surface, coin_font, player, screen_width)
        draw_token_counter(world_surface, token_font, player, screen_width)
        boss_enemy = next((e for e in enemies if getattr(e, "is_wave_boss", False) and e.alive), None)
        if boss_enemy is not None:
            draw_boss_health_bar(world_surface, boss_health_font, boss_enemy, screen_width)

        shake_x, shake_y = 0, 0
        if state == STATE_READY_BANNER:
            shake_x, shake_y = get_ready_shake_offset(state_timer)
        elif state == STATE_BOSS_INTRO:
            shake_x, shake_y = get_boss_shake_offset(state_timer)
        if impact_shake_timer > 0:
            impact_shake_timer = max(0.0, impact_shake_timer - dt)
            impact_amplitude = BOSS_SPAWN_SHAKE_MAGNITUDE * (
                impact_shake_timer / BOSS_SPAWN_SHAKE_DURATION)
            shake_x += random.uniform(-impact_amplitude, impact_amplitude)
            shake_y += random.uniform(-impact_amplitude, impact_amplitude)

        screen.fill(BG_COLOR)
        screen.blit(world_surface, (shake_x, shake_y))

        if state == STATE_MAIN_MENU:
            draw_main_menu(screen, game_over_font, death_info_font,
                           screen_width, screen_height, multiplayer_enabled)
        elif state == STATE_READY_BANNER:
            draw_ready_banner(screen, ready_font, screen_width, screen_height,
                               state_timer, READY_DISPLAY_TIME)
        elif state == STATE_BOSS_INTRO:
            draw_boss_intro(screen, boss_name_font, boss_sub_font, boss_warn_font,
                            screen_width, screen_height, state_timer, incoming_boss_config)
        elif state == STATE_DEAD:
            draw_death_screen(screen, game_over_font, death_info_font,
                              screen_width, screen_height,
                              spawn_manager.wave_number, player.stats.coin_count)
        elif state == STATE_CARD_SELECT:
            token_type = offered_cards[0].token_type if offered_cards else "gray"
            card_player = player if active_card_player == 0 else player_two
            draw_card_select_screen(screen, game_over_font, card_font, token_font,
                                    screen_width, screen_height, offered_cards, card_player,
                                    token_type)

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
