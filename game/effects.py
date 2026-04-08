"""
EffectsMixin — particle effects, shockwaves, and hit bursts for the Game class.
Mixed into Game via multiple inheritance; all methods use `self` freely.
"""
import pygame
from typing import Optional, Any
from . import models as M


class EffectsMixin:
    screen: pygame.Surface
    rhythm: Any  # Or import and use the actual RhythmManager type
    song: M.Song
    drop_note_indices: dict[int, int]
    drops_triggered: set[int]
    
    # ── Animation / Asset expected attributes ──
    _hurt_frames: list[pygame.Surface]
    _hurt_playing: bool
    _hurt_frame_idx: float
    _hurt_fps: float
    _bop_frames: list[pygame.Surface]
    _bop_surf: Optional[pygame.Surface]

    # ── Particle/Effect lists ──
    shockwaves: list[M.Shockwave]
    _hold_particles: list[dict[str, Any]]
    _hit_bursts: list[dict[str, Any]]

    def trigger_hurt(self):
        """Queue one playthrough of noki_hurt on top of noki_bop."""
        if not self._hurt_frames:
            return
        if self._hurt_playing:
            self._hurt_frame_idx = 0.0
        else:
            self._hurt_playing = True
            self._hurt_frame_idx = 0.0

    def update_hurt_animation(self, dt: float):
        """Advance hurt frame at 115% speed. Returns the current hurt surface, or None when done."""
        if not self._hurt_playing or not self._hurt_frames:
            return None
        self._hurt_frame_idx += self._hurt_fps * dt * 1.15
        n = len(self._hurt_frames)
        if self._hurt_frame_idx >= n:
            self._hurt_playing = False
            self._hurt_frame_idx = 0.0
            return None
        return self._hurt_frames[int(self._hurt_frame_idx)]

    def update_cat_animation(self):
        """Select noki_bop frame, synced to song beat_times."""
        import time
        if not self._bop_frames:
            return

        n = len(self._bop_frames)
        elapsed   = time.perf_counter() - self.rhythm.start_time
        song_time = elapsed - self.rhythm.lead_in
        beat_times = self.song.beat_times

        if beat_times and len(beat_times) >= 2 and song_time >= beat_times[0]:
            current_beat_idx = 0
            for i, bt in enumerate(beat_times):
                if bt <= song_time:
                    current_beat_idx = i
                else:
                    break
            if current_beat_idx < len(beat_times) - 1:
                beat_start = beat_times[current_beat_idx]
                beat_end   = beat_times[current_beat_idx + 1]
                phase = (song_time - beat_start) / (beat_end - beat_start)
            else:
                phase = 0.0
            normalized = ((current_beat_idx % 2) + phase) / 2.0
        else:
            beat_dur   = 60.0 / self.song.bpm
            normalized = (elapsed / beat_dur % 2.0) / 2.0

        frame_idx = int(normalized * n) % n
        self._bop_surf = self._bop_frames[frame_idx]

    def trigger_shockwave(self):
        """Spawn multiple expanding shockwave rings."""
        center_x = self.screen.get_width() // 2
        center_y = self.screen.get_height() // 2

        num_rings = 5
        for i in range(num_rings):
            initial_radius = i * 30
            shockwave = M.Shockwave(
                center_x=center_x,
                center_y=center_y,
                radius=initial_radius,
                max_radius=800,
                alpha=150,
                thickness=4,
                speed=400 + i * 50
            )
            self.shockwaves.append(shockwave)

    def _spawn_hit_particles(self, x: int, y: int):
        """Spawn golden + white particles at (x, y) for any correct hit."""
        import random as _rnd
        for _ in range(2):
            self._hold_particles.append({
                'x': float(x) + _rnd.uniform(-12, 12),
                'y': float(y) + _rnd.uniform(-14, 14),
                'vx': _rnd.uniform(-130, 130),
                'vy': _rnd.uniform(-160, 40),
                'alpha': 220.0,
                'radius': _rnd.uniform(3.75, 7.5),
                'color': (255, 210, 60),
            })
        for _ in range(3):
            self._hold_particles.append({
                'x': float(x) + _rnd.uniform(-10, 10),
                'y': float(y) + _rnd.uniform(-12, 12),
                'vx': _rnd.uniform(-220, 220),
                'vy': _rnd.uniform(-260, 60),
                'alpha': 190.0,
                'radius': _rnd.uniform(1.5, 3.3),
                'color': (240, 240, 255),
            })

    def trigger_hit_ripple(self, x: int, y: int):
        """Spawn the bubble-style 3-layer hit burst at (x, y)."""
        import random as _rnd
        NOTE_R = 14 * 0.6 * 0.6 * 1.1
        _palette = _rnd.choice([
            {'l3': (157, 187, 223), 'l2o': (124, 154, 208), 'l2i': (155, 179, 227), 'l1': (197, 215, 239)},
            {'l3': (214, 166, 196), 'l2o': (200, 140, 176), 'l2i': (225, 165, 201), 'l1': (238, 202, 220)},
            {'l3': (220, 195, 100), 'l2o': (205, 170,  75), 'l2i': (235, 205, 120), 'l1': (248, 232, 165)},
        ])
        self._hit_bursts.append({
            'x': x, 'y': y,
            'age': 0.0,
            'l1_dur': 0.10,
            'l1_r': NOTE_R,
            'l2_dur': 0.20,
            'l2_r0': NOTE_R * 0.8,
            'l2_r1': NOTE_R * 2.5,
            'l3_delay': 0.03,
            'l3_dur': 0.25,
            'l3_r0': NOTE_R * 1.0,
            'l3_r1': NOTE_R * 3.2,
            'pal': _palette,
        })

    def trigger_miss_shockwave(self, x: int, y: int):
        """Spawn a small shockwave at a missed note position."""
        shockwave = M.Shockwave(
            center_x=x,
            center_y=y,
            radius=5,
            max_radius=40,
            alpha=200,
            thickness=2,
            speed=150
        )
        self.shockwaves.append(shockwave)

    def check_drop_note_hit(self, hit_note_idx: int):
        """Check if the hit note is any drop note and trigger shockwave."""
        for drop_idx, note_idx in self.drop_note_indices.items():
            if drop_idx not in self.drops_triggered and hit_note_idx == note_idx:
                self.trigger_shockwave()
                self.drops_triggered.add(drop_idx)

    def update_shockwaves(self, dt: float):
        """Update and render active shockwaves."""
        surviving = []
        for wave in self.shockwaves:
            if wave.update(dt):
                surviving.append(wave)
                self.render_shockwave(wave)
        self.shockwaves = surviving

    def update_hold_particles(self, dt: float):
        """Tick and render hold-note impact particles."""
        surviving = []
        for p in self._hold_particles:
            p['x']     += p['vx'] * dt
            p['y']     += p['vy'] * dt
            p['vy']    += 120 * dt
            p['alpha'] -= 420 * dt
            if p['alpha'] > 0:
                surviving.append(p)
                r = int(p['radius'])
                sz = r * 2 + 1
                surf = pygame.Surface((sz, sz), pygame.SRCALPHA)
                col = p.get('color', (255, 210, 60))
                pygame.draw.circle(surf, (*col, int(p['alpha'])), (r, r), r)
                self.screen.blit(surf, (int(p['x'] - r), int(p['y'] - r)))
        self._hold_particles = surviving

    def update_hit_bursts(self, dt: float):
        """Tick and render osu!-style 3-layer hit bursts."""
        surviving = []
        for b in self._hit_bursts:
            b['age'] += dt
            age = b['age']
            x, y = b['x'], b['y']
            surf_sz = int(b['l3_r1'] * 2 + 12)
            if surf_sz < 4:
                surviving.append(b)
                continue
            surf = pygame.Surface((surf_sz, surf_sz), pygame.SRCALPHA)
            cx = cy = surf_sz // 2

            _A = 0.4
            pal = b.get('pal', {'l3': (140,148,180), 'l2o': (120,110,155), 'l2i': (155,138,185), 'l1': (210,210,225)})

            # ── Layer 3: trailing ring ──
            l3_age = age - b['l3_delay']
            if 0 < l3_age < b['l3_dur']:
                t3 = l3_age / b['l3_dur']
                r3 = b['l3_r0'] + (b['l3_r1'] - b['l3_r0']) * t3
                a3 = int(160 * (1.0 - t3) * _A)
                thick3 = max(9, min(11, int(11 * (1.0 - t3 * 0.3))))
                for k in range(3):
                    fade = int(a3 * (1.0 - k * 0.28))
                    if fade <= 0:
                        break
                    pygame.draw.circle(surf, (*pal['l3'], fade),
                                       (cx, cy), max(1, int(r3) + k), max(1, thick3 - k))

            # ── Layer 2: primary ring ──
            if age < b['l2_dur']:
                t2 = age / b['l2_dur']
                r2 = b['l2_r0'] + (b['l2_r1'] - b['l2_r0']) * t2
                a2 = int(255 * (1.0 - t2) * _A)
                thick2 = max(9, min(11, int(11 * (1.0 - t2 * 0.3))))
                pygame.draw.circle(surf, (*pal['l2o'], a2),
                                   (cx, cy), max(1, int(r2)), thick2)
                pygame.draw.circle(surf, (*pal['l2i'], min(255, int(a2 * 1.15))),
                                   (cx, cy), max(1, int(r2) - thick2 // 2), max(2, thick2 // 2 + 1))

            # ── Layer 1: soft center flash ──
            if age < b['l1_dur']:
                t1 = age / b['l1_dur']
                a1 = int(220 * (1.0 - t1) ** 1.5 * _A)
                r1 = int(b['l1_r'] * (1.0 - t1 * 0.35))
                if r1 > 0:
                    pygame.draw.circle(surf, (*pal['l1'], a1), (cx, cy), r1)

            self.screen.blit(surf, (x - cx, y - cy),
                             special_flags=pygame.BLEND_RGBA_ADD)

            if age < b['l3_delay'] + b['l3_dur']:
                surviving.append(b)

        self._hit_bursts = surviving

    def render_shockwave(self, wave: M.Shockwave):
        """Render a single shockwave ring."""
        if wave.alpha <= 0 or wave.radius <= 0:
            return

        diameter = int(wave.radius * 2) + wave.thickness * 2
        if diameter <= 0:
            return

        surface = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
        gray_value = 180
        color = (gray_value, gray_value, gray_value, wave.alpha)
        center = diameter // 2
        if wave.thickness > 0 and wave.radius > 0:
            pygame.draw.circle(surface, color, (center, center), int(wave.radius), wave.thickness)

        blit_x = int(wave.center_x - center)
        blit_y = int(wave.center_y - center)
        self.screen.blit(surface, (blit_x, blit_y))
