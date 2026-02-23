import pygame
from game.engine import Game
from game.models import Level
from game.menu import MenuManager

SONG_PATH = "assets/audios/"
SONG_NAMES = [
    "BurgeraX - Scorpion.mp3",
    "Toby Fox - THE WORLD REVOLVING.mp3",
    "Toby Fox - Finale.mp3",
    "miley.mp3",
    "ICARIUS.mp3",
    "Fluffing A Duck.mp3",
    "Megalovania.mp3",
    "Malo Kart.mp3",
    "tidalwave.mp3",
    "hustle.mp3",
    "what is love?.mp3"
]

WORD_BANK_1 = ["cat", "test", "me", "rhythm", "beat", "fish", "moon", "derp", "noki", "yeah"]
WORD_BANK_2 = ["cat", "here", "me", "chosen", "beat", "hope", "soul", "true", "love", "stay"]


def main():
    pygame.init()
    info = pygame.display.Info()
    screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.RESIZABLE)
    pygame.display.set_caption("Key Dash")
    clock = pygame.time.Clock()

    while True:
        menu = MenuManager(screen, clock, SONG_NAMES)
        result = menu.run()

        if result is None:
            break

        selected, difficulty = result

        level = Level(
            word_bank=WORD_BANK_2,
            song_path=SONG_PATH + SONG_NAMES[selected],
            difficulty=difficulty,
        )

        # ==========================TO DO LIST

        # for the bounce mode mode -> reverse on arrows (bounces off of arrows and reverses) almost like going back in the timeline. the measure bars should also kinda accelerae backwards and reverse too. so not like a reverse, but almost like the hitmarker bounces off (so like momentum in the opposite direction with the measure and beat markers reflecting that)
        # don't move the hitmarker. 
        # make style
        # when skipping a word (like the word is gonna get cut off in the slot, add two "ghost words", blue circles (like sans's fake hits) where the player shouldn't press but complete the word)

        #save all the beatmaps manually of al the existing levels (so they don't have to load).
        # on pause screen, make the timeline and notes freeze not disappear
        # add restart button 

        #on simpler/calmer songs, don't just end words because the melody is slow/sparse, just drag it along for longer (ex. instead of givin "cat", "blob" "yeah" and cutting off half the words, just do "blob" and "cats"). if not many slots available.
        # for complex/faster/more pacey songs/sections, just add the blue stuff

        # on finish, add some finish thing for 2-3 seconds the open 'finish' menu
        
        #make it to where, on wrong note, the next char isn't immediately deactivated.

        # some speed-ups seem to happen 

        #timeline rotate
        #EVENTUALLY
        # work on file system, saving files to cloud (so the files are there for that user every time, etc)
        #integrate font
        # doesn't understand climax sections well

        # ===== BUGS
        # doesn't wait until last char is finished in dual section before transitioning back
        # sometimes has ghost letters (skips on its own) (only bounce mode). 
        # sometimes doesn't have grace period when starting dual mode

        # Ariana Grande - Problem ft. Iggy Azalea 
        # words synced to song? is word detection from audio possible?

        game = Game(level=level, screen=screen, clock=clock)
        game.run()

    pygame.quit()


if __name__ == "__main__":
    main()
