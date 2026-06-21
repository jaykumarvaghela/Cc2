# Canvas & Conflict — Terminal Edition

An interactive visual-novel-style story, playable in the terminal. Built so the
story content, the game logic, and the rendering are all separate — which
means we can swap the terminal renderer for a graphical one (web, Ren'Py,
Pygame, etc.) later without touching the story itself.

## Quick Start

```bash
cd canvas_and_conflict
pip install -r requirements.txt   # optional — only adds color, game runs fine without it
python main.py
```

You'll get a menu: **New Game**, **Load Game**, **Quit**.

While playing, at any choice prompt you can type:

| Command | Effect |
|---|---|
| `1`, `2`, `3`... | pick that choice |
| `save` | save your progress to a named slot |
| `load` | load a previously saved slot |
| `restart` | start the story over |
| `quit` | exit |
| `help` | show this list again |

## Project Structure

```
canvas_and_conflict/
├── main.py                 # entry point — menu, ties everything together
├── requirements.txt
├── src/
│   ├── models.py            # Scene / Choice / DialogueLine data classes
│   ├── engine.py             # GameEngine — navigation, save/load hooks, main loop
│   ├── display.py            # ALL terminal rendering lives here
│   └── save_manager.py       # reads/writes save files as JSON
├── data/
│   └── story_data.py         # the entire story, as structured data (no logic)
├── saves/                    # save files get written here (gitignored content)
└── tests/
    └── test_engine.py        # validates the story graph (no broken links,
                               # no infinite loops, every path reaches an ending)
```

### Why it's split up this way

- **`data/story_data.py`** is pure content — title, background, characters
  present, dialogue, choices. No code logic. This is the file you'll edit
  most often to add or change story content.
- **`src/models.py`** defines the *shape* of a scene (a dataclass), so the
  story data has a predictable structure.
- **`src/engine.py`** only knows how to navigate between scenes by id and
  manage save/load. It has zero knowledge of *what* the story says.
- **`src/display.py`** is the only file that prints anything. When we add a
  graphical front-end, this is the file that gets replaced — engine.py and
  story_data.py stay untouched.

## Story Structure

- **35 scenes total**, starting at `SCENE_001`.
- **7 different endings** depending on the choices you make.
- Every scene has a unique ID (e.g. `SCENE_003C`) so choices can reference
  any other scene directly — this is what makes branching/looping-back
  possible.

Run the validator any time you edit the story:

```bash
python -m tests.test_engine
```

It checks that:
1. Every choice points to a scene that actually exists.
2. Every scene is reachable from the start.
3. There are no infinite loops (every path reaches an ending within a
   reasonable number of steps).
4. Lists all the endings it found.

## Adding / Editing Scenes

Open `data/story_data.py` and add a new entry to the `STORY` dict:

```python
"SCENE_999": {
    "title": "Scene Title",
    "background": "Where we are, what it looks like.",
    "time": "When this happens.",
    "characters_present": "Who's on screen.",
    "atmosphere": "Mood / music notes.",
    "visuals": {
        "Arjun": "What he looks like / how he's positioned right now.",
    },
    "dialogue": [
        {"speaker": "ARJUN", "line": '''(action) "Spoken line."'''},
        {"speaker": "NARRATOR", "line": "Stage direction with no specific speaker."},
    ],
    "choices": [
        {"text": "What the player sees as an option.", "next": "SCENE_WHATEVER"},
    ],
    # For ending scenes instead of choices:
    # "is_ending": True,
    # "ending_label": "ENDING X: Short Name",
},
```

Notes:
- Use **triple double-quoted strings** (`"""..."""`) for dialogue lines —
  spoken dialogue is full of `"quotes"`, and triple-quoting avoids having to
  escape every single one.
- `NARRATOR` is a pseudo-speaker for stage directions that aren't tied to one
  character.
- After editing, run `python -m tests.test_engine` to make sure you haven't
  introduced a broken link or a loop.

## Roadmap (next steps)

- [ ] Swap `src/display.py` for a graphical front-end (web/Ren'Py/Pygame)
      while reusing `engine.py` and `data/story_data.py` unchanged.
- [ ] Add character sprites / background images, referenced from `visuals`.
- [ ] Add a "history / replay" view using the `history` list already tracked
      by `GameEngine`.
- [ ] Optional: track simple relationship "flags" (e.g. Priya trust level)
      to let some choices be gated on prior decisions.
