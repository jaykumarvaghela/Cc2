#!/usr/bin/env python3
"""
main.py
-------
Entry point for Canvas & Conflict (terminal edition).

Run with:
    python main.py
"""

import sys

from src import display, save_manager
from src.engine import GameEngine, StoryError
from data.story_data import STORY


def main_menu(engine: GameEngine) -> None:
    while True:
        display.clear_screen()
        display.print_title_banner("CANVAS & CONFLICT\nAn Interactive Story")
        print()
        print("  [1] New Game")
        print("  [2] Load Game")
        print("  [3] Quit")
        print()
        choice = display.prompt()

        if choice == "1":
            engine.restart()
            engine.play()
        elif choice == "2":
            saves = save_manager.list_saves()
            if not saves:
                print("\nNo save files found.\n")
                display.prompt("Press enter to go back... ")
                continue
            print()
            for slot, saved_at in saves:
                print(f"  - {slot}  (saved {saved_at})")
            print()
            slot = display.prompt("Slot name to load: ")
            data = save_manager.load_game(slot)
            if data is None:
                print("\nNo save found with that name.\n")
                display.prompt("Press enter to go back... ")
                continue
            engine.current_scene_id = data["current_scene_id"]
            engine.history = data.get("history", [engine.current_scene_id])
            engine.play()
        elif choice in ("3", "quit", "exit", "q"):
            print("\nGoodbye!\n")
            return
        else:
            print("\nPlease choose 1, 2, or 3.\n")
            display.prompt("Press enter to continue... ")


if __name__ == "__main__":
    try:
        engine = GameEngine(STORY)
    except StoryError as e:
        print("Story data failed validation:\n")
        print(e)
        sys.exit(1)

    try:
        main_menu(engine)
    except SystemExit:
        pass
    except KeyboardInterrupt:
        print("\n\nGoodbye!\n")
