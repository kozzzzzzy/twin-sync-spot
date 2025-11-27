# TwinSync Spot

**Does this match YOUR definition?**

TwinSync Spot is a Home Assistant integration that compares camera snapshots to *your own description* of how a space should look. No more generic "is this tidy?" — you define what "ready" means for each spot.

## 🌟 The Big Idea

| Old Way | TwinSync Way |
|---------|--------------|
| "AI, is this room tidy?" | "Does this match MY definition?" |
| Generic cleaning advice | Compare to YOUR words |
| "dust things" | "that coffee mug you mentioned" |
| No memory | **Remembers patterns** |

## 🎯 Key Concepts

| Term | Meaning |
|------|---------|
| **Spot** | A specific location you're tracking |
| **Ready State** | YOUR description of how it should look |
| **Definition** | Your natural language description |
| **Check** | Scan the spot with camera |
| **To sort** | Things that don't match your definition |
| **Looking good** | Things that do match |
| **Reset** | You've fixed it — updates streak |

## 📸 Example

You define your work desk:
```
This is my work area. I need a clear surface to focus.

Things that should be here:
- Laptop on stand
- Notebook and pen
- Water bottle

Things that shouldn't be here:
- Dirty dishes or cups
- Random papers
- Clothes
```

TwinSync checks and reports:
```
📍 My Work Desk ⚠️ Needs Attention

To sort:
• Coffee mug on left side 🔄 (again!)
• Papers by keyboard

Looking good:
• Laptop on stand ✓
• Notebook in place ✓

---
*That mug's been there 4 days running.*
📊 Coffee mug appears in 80% of morning checks.

🔥 Streak: 0 days (best: 5)
```

## 🧠 Memory System

TwinSync remembers:
- **Recurring items** — "coffee mug (12x in 30 days)"
- **Patterns** — "Usually sorted by 10am"
- **Tough days** — "Mondays are worst"
- **Streaks** — consecutive days sorted

## 🎤 Voices

Choose how TwinSync talks to you:

| Voice | Style |
|-------|-------|
| **Direct** | Just the facts, no fluff |
| **Supportive** | Encouraging, acknowledges effort |
| **Analytical** | Spots patterns, references history |
| **Minimal** | List only, no commentary |
| **Gentle Nudge** | Soft suggestions for tough days |
| **Custom** | Your own prompt |

## 📋 Requirements

- Home Assistant 2024.6.0+
- Camera entity for each spot
- [Gemini API key](https://aistudio.google.com/app/apikey) (free tier works!)

## 🚀 Installation

### Via HACS

1. Open HACS → Integrations
2. Click ⋮ → Custom repositories
3. Add `https://github.com/kozzzzzzy/cleanme` as Integration
4. Download and restart Home Assistant

### Manual

1. Download the latest release
2. Copy `custom_components/cleanme` to your config
3. Restart Home Assistant

## ⚙️ Setup

1. **Settings** → **Devices & Services** → **Add Integration**
2. Search for **CleanMe** (domain name, displays as TwinSync Spot)
3. Follow the two-step flow:
   - **Step 1**: Name, camera, spot type, voice
   - **Step 2**: Edit your definition, set frequency, enter API key

## 📊 Entities Created

For a spot named "My Work Desk":

| Entity | What it shows |
|--------|---------------|
| `binary_sensor.my_work_desk_sorted` | Does it match your definition? |
| `sensor.my_work_desk_to_sort` | Count + list of items to sort |
| `sensor.my_work_desk_looking_good` | Count + list of matching items |
| `sensor.my_work_desk_notes` | AI observations |
| `sensor.my_work_desk_streak` | Current streak (days sorted) |
| `button.my_work_desk_check` | Trigger a check |
| `button.my_work_desk_reset` | Mark as fixed |

## 🔧 Services

| Service | What it does |
|---------|--------------|
| `cleanme.check` | Check a spot now |
| `cleanme.reset` | Mark spot as fixed |
| `cleanme.snooze` | Pause checks for a duration |
| `cleanme.unsnooze` | Cancel snooze |
| `cleanme.check_all` | Check all spots |

## 🎨 Dashboard

TwinSync auto-generates a dashboard at `Settings → Dashboards`.

Uses only standard HA cards — no custom cards required!

## 💰 Cost

Gemini API free tier is plenty for home use:
- 15 requests/minute
- 1500 requests/day
- Typical usage: 2-4 checks × 3 spots = 6-12/day

## 📄 License

MIT — do whatever you want with it.

---

**Made with 🎯 for people who know what "clean" means to them.**
