# Macro Recorder

A minimal dark-mode mouse & keyboard macro recorder for Windows. Records every mouse movement, click, drag, scroll, and key press with precise timing — then replays them exactly. Built with Python + Tkinter, single file, one dependency.

โปรแกรมอัดและเล่นซ้ำเมาส์/คีย์บอร์ดสำหรับ Windows ธีมมืด เรียบง่าย อัดทุกการขยับ คลิก ลาก สกรอลล์ และคีย์บอร์ดพร้อมจังหวะเวลาแม่นยำ แล้วเล่นซ้ำได้เป๊ะๆ ไฟล์เดียวจบ

## ✨ Features / ฟีเจอร์

- **Record everything** — mouse position (up to 500 samples/s), clicks, drags, scroll, and full keyboard with real timing
- **Precise replay** — 1 ms high-resolution timer, parallel mouse + keyboard streams, fractional-delta accumulation
- **Loop playback** — fixed count or infinite ∞, adjustable speed (0.5×–3×) and gap between loops
- **Roblox / game mode** — records **raw mouse deltas** (Raw Input) and replays them only while right-click is held, so camera rotation matches the game exactly; absolute coordinates everywhere else
- **Scancode key injection** — keys are sent as hardware scancodes so games (raw input) can see them; hold multiple keys at once (WASD + mouse together)
- **Multiple macros** — auto-saved with timestamp names; rename, multi-select delete (drag / Ctrl+A / Delete), open folder
- **Progress bar** with live percentage per loop
- **TH / EN interface** — click the flag to switch language, the choice is remembered
- **Dark mode** including the Windows title bar

## 📦 Install / ติดตั้ง

1. Install [Python 3.10+](https://www.python.org/downloads/) — tick **Add Python to PATH**
2. Install the one dependency / ติดตั้งไลบรารีตัวเดียว:

```
pip install pynput
```

3. Double-click `MacroRecorder.pyw` (no console window) / ดับเบิลคลิกไฟล์ได้เลย

## 🎮 Usage / วิธีใช้

| Hotkey | Action |
|--------|--------|
| **F3** | Start / stop recording (auto-saves) — เริ่ม/หยุดบันทึก เซฟอัตโนมัติ |
| **F4** | Play / stop selected macro — เล่น/หยุดเล่น |
| **Esc** | Stop playback — หยุดเล่น |

Hotkeys are global — they work inside any app or game.

- **Loops / วนซ้ำ** — repeat count, or tick *Loop forever ∞*
- **Speed / ความเร็ว** — replay faster or slower than recorded
- **Gap / หน่วง (วิ)** — pause between loops
- **Roblox mode / โหมด Roblox** — tick when replaying in games that lock the cursor while right-dragging. *Turn ×* 1.0 = camera rotation identical to the recording
- Macros are stored as JSON in `Documents\MacroRecorder`

### Roblox tips
- Keep the game window in the same position/size as when recording
- Turn off *Enhance pointer precision* in Windows mouse settings for best consistency

## ⚙️ How it works / หลักการทำงาน

- **Recording** — `pynput` listeners capture cursor positions, clicks, scroll, and keys (stored as virtual-key codes). A Raw Input hook (`WM_INPUT`) on the Tk window additionally captures hardware mouse deltas — the same values games use for camera rotation, which survive cursor-locking.
- **Replay** — events are split into a mouse stream and a keyboard stream that run in parallel against one shared high-precision clock (`timeBeginPeriod(1)` + `perf_counter`). Mouse moves are injected with `SendInput` (absolute, or relative raw deltas during right-drag in game mode); keys are injected as scancodes.
- The process is per-monitor **DPI-aware**, so coordinates stay correct on scaled displays (125 % / 150 %).

## ⚠️ Notes

- Windows only (uses Win32 `SendInput` / Raw Input)
- Use responsibly — automating input in online games may violate that game's Terms of Service. Intended for repetitive document/office workflows and personal convenience.

## 📄 License

[MIT](LICENSE)
