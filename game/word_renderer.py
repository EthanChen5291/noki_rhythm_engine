"""
WordRenderer — carousel word animation and typography drawing.
Instantiated and owned by Game; accesses game state via self.game.
"""
import pygame
import math
from . import constants as C
from .menu_utils import _FONT


class WordRenderer:

    def __init__(self, game) -> None:
        self.game = game

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_next_word(self) -> str | None:
        """Get the next word that will be typed after current word completes."""
        g = self.game
        if not g.rhythm.beat_map:
            return None

        next_word_text = None
        for i in range(g.rhythm.char_event_idx, len(g.rhythm.beat_map)):
            event = g.rhythm.beat_map[i]
            if event.word_text and event.char_idx == 0 and not event.is_rest:
                if event.word_text != g.rhythm.current_expected_word():
                    next_word_text = event.word_text
                    break

        if next_word_text is None:
            return None

        max_char_idx = -1
        for i in range(g.rhythm.char_event_idx, len(g.rhythm.beat_map)):
            ev = g.rhythm.beat_map[i]
            if ev.is_rest or ev.word_text != next_word_text:
                continue
            if ev.char_idx > max_char_idx:
                max_char_idx = ev.char_idx

        if max_char_idx < 0:
            return next_word_text
        return next_word_text[:max_char_idx + 1]

    # ------------------------------------------------------------------
    # Draw methods
    # ------------------------------------------------------------------

    def draw_word_animated(
        self,
        word: str,
        position: str,
        transition_progress: float,
        is_current: bool,
        fading_out: bool = False,
        adjacent_word_width: int = 0,
        y_offset: float = 0,
    ) -> None:
        """Draw a word with 3D carousel rotation animation."""
        g = self.game
        if not word:
            return

        base_char_spacing = 60

        if position == 'right':
            char_spacing = base_char_spacing * 0.7
        elif position == 'left':
            char_spacing = base_char_spacing * 0.7
        else:
            char_spacing = base_char_spacing

        total_width = len(word) * char_spacing

        radius = 350
        center_offset = base_char_spacing / 2
        center_x = g.screen.get_width() // 2 + center_offset
        center_y = 180 + y_offset

        base_spacing = 100

        if position == 'center':
            target_angle = 0
            target_scale = 1.0
            target_alpha = 255
            target_color = (255, 255, 255)
            target_char_spacing = base_char_spacing
        elif position == 'right':
            width_factor = (total_width + adjacent_word_width) / 2
            dynamic_spacing = base_spacing + width_factor * 0.3
            target_angle = dynamic_spacing / radius
            target_scale = 0.75
            target_alpha = 180
            target_color = (150, 150, 150)
            target_char_spacing = base_char_spacing * 0.7
        else:
            width_factor = (total_width + adjacent_word_width) / 2
            dynamic_spacing = base_spacing + width_factor * 0.3
            target_angle = -dynamic_spacing / radius
            target_scale = 0.75
            target_alpha = int(180 * (1 - transition_progress)) if fading_out else 180
            target_color = (150, 150, 150)
            target_char_spacing = base_char_spacing * 0.7

        if position == 'center' and transition_progress < 1.0:
            width_factor = (total_width + adjacent_word_width) / 2
            dynamic_spacing = base_spacing + width_factor * 0.3
            start_angle = dynamic_spacing / radius
            current_angle = start_angle + (target_angle - start_angle) * transition_progress

            current_scale = 0.75 + (target_scale - 0.75) * transition_progress
            current_alpha = int(180 + (target_alpha - 180) * transition_progress)

            gray_amount = int(150 + (255 - 150) * transition_progress)
            current_color = (gray_amount, gray_amount, gray_amount)

            start_char_spacing = base_char_spacing * 0.7
            current_char_spacing = start_char_spacing + (target_char_spacing - start_char_spacing) * transition_progress
        else:
            current_angle = target_angle
            current_scale = target_scale
            current_alpha = target_alpha
            current_color = target_color
            current_char_spacing = char_spacing

        x_offset = radius * math.sin(current_angle)
        z = radius * (1 - math.cos(current_angle))

        perspective_scale = 1.0 / (1.0 + z / 1000)
        final_scale = current_scale * perspective_scale
        final_alpha = int(current_alpha * perspective_scale)

        animated_total_width = len(word) * current_char_spacing * final_scale

        current_x = center_x + x_offset - animated_total_width / 2

        for i, char in enumerate(word):
            font_size = int(48 * final_scale)
            char_font = pygame.font.Font(_FONT, font_size)

            char_surface = char_font.render(char, True, current_color)
            char_surface.set_alpha(final_alpha)

            char_x = current_x + i * (current_char_spacing * final_scale)
            char_y = center_y

            g.screen.blit(char_surface, (int(char_x), int(char_y)))

            if position == 'center' and is_current and g.rhythm.char_event_idx < len(g.rhythm.beat_map):
                current_event = g.rhythm.beat_map[g.rhythm.char_event_idx]
                if (not current_event.is_rest
                        and current_event.word_text.startswith(word)
                        and current_event.char_idx == i):
                    underline_width = int(C.UNDERLINE_LEN * final_scale)
                    line_x = char_x - 10 * final_scale
                    line_y = char_y + 50

                    pygame.draw.line(
                        g.screen,
                        (255, 255, 255),
                        (int(line_x), int(line_y)),
                        (int(line_x + underline_width), int(line_y)),
                        3,
                    )

    def draw_background_word(self, word: str) -> None:
        """Draw the current word as a large, faded background element during dual-side mode."""
        g = self.game
        if not word:
            return

        font_size = 180
        bg_font = pygame.font.Font(_FONT, font_size)
        bg_color = (60, 60, 60)

        char_spacing = 120
        total_width = len(word) * char_spacing
        start_x = (g.screen.get_width() - total_width) // 2
        center_y = g.screen.get_height() // 2 - 50

        for i, char in enumerate(word):
            char_surface = bg_font.render(char, True, bg_color)
            char_x = start_x + i * char_spacing
            char_rect = char_surface.get_rect(center=(char_x + char_spacing // 2, center_y))
            g.screen.blit(char_surface, char_rect)

    def draw_text(self, txt: str, left: bool) -> None:
        g = self.game
        text_surface = g.font.render(txt, True, (255, 255, 255))
        if left:
            g.screen.blit(text_surface, (100, 100))
        else:
            text_rect = text_surface.get_rect(center=(1100, 250))
            g.screen.blit(text_surface, text_rect)

    def draw_curr_word(self, txt: str) -> None:
        self.draw_text(txt, True)

    # ------------------------------------------------------------------
    # Main render call
    # ------------------------------------------------------------------

    def render(self, current_time: float) -> None:
        """Render the word carousel (current / next / previous words)."""
        g = self.game

        current_word = g.rhythm.current_display_word()
        next_word = self.get_next_word()

        char_spacing = 60
        current_word_width = len(current_word) * char_spacing if current_word else 0
        next_word_width = len(next_word) * char_spacing if next_word else 0

        if current_word != g._last_displayed_word:
            g._word_transition_start = current_time
            g._last_displayed_word = current_word

        transition_duration = 0.3
        transition_progress = min(1.0, (current_time - g._word_transition_start) / transition_duration)
        ease_progress = 1 - (1 - transition_progress) ** 3

        word_y_offset = g.word_current_y - g.word_normal_y

        if current_word:
            self.draw_word_animated(
                current_word,
                position='center',
                transition_progress=ease_progress,
                is_current=True,
                adjacent_word_width=next_word_width,
                y_offset=word_y_offset,
            )

        if next_word:
            self.draw_word_animated(
                next_word,
                position='right',
                transition_progress=ease_progress,
                is_current=False,
                adjacent_word_width=current_word_width,
                y_offset=word_y_offset,
            )

        if g._previous_word is not None and transition_progress < 1.0:
            self.draw_word_animated(
                g._previous_word,
                position='left',
                transition_progress=ease_progress,
                is_current=False,
                fading_out=True,
                adjacent_word_width=current_word_width,
                y_offset=word_y_offset,
            )

        if transition_progress >= 1.0:
            g._previous_word = current_word
