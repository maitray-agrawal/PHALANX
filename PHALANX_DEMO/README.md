# PHALANX — Interactive Product Demo & Competition Presentation

> **PayPal AI Hackathon 2026 Entry**  
> **Tagline:** *Let agents act. Keep humans and policy in control.*  
> **Track:** FinTech & Autonomous Agent Governance

---

## 🚀 Quick Start (Running the Presentation)

### Option 1: One-Click Windows PowerShell Launcher (Recommended)
Right-click `launch.ps1` and select **Run with PowerShell**, or execute:

```powershell
cd PHALANX_DEMO
.\launch.ps1
```

This starts a lightweight presentation server at `http://localhost:3000` and automatically opens it in your default browser.

### Option 2: Direct Browser Execution
Double-click `PHALANX_DEMO/index.html` to open directly in Google Chrome or Microsoft Edge. All interactive presentation and Web Speech API narration features work standalone without external server dependencies.

---

## 🎙️ Spoken Narration & Web Speech API

The presentation features an integrated narration engine powered by the browser's **Web Speech API**:
- **Indian English Voice Priority:** The presentation automatically searches for installed `en-IN` voices (such as *Microsoft Heera*, *Microsoft Ravi*, or *Google Indian English*). If unavailable, it falls back to the system's preferred English voice.
- **Playback Controls:** Click the **Play Narration** button in the bottom bar or press **SPACE** on your keyboard to toggle voiceover.
- **Synchronized Subtitles:** The real-time teleprompter bar displays and updates spoken lines for each scene.
- **Speed Adjustment:** Select between `0.9x`, `1.0x`, `1.1x`, and `1.2x` speaking pace in the bottom-right corner.

---

## ⌨️ Presentation Keyboard Shortcuts

| Key | Action |
| :--- | :--- |
| **Right Arrow (▶) / Page Down** | Advance to next scene |
| **Left Arrow (◀) / Page Up** | Return to previous scene |
| **Spacebar** | Toggle spoken narration play/pause |
| **F** | Toggle 16:9 cinematic fullscreen mode |
| **Escape (ESC)** | Close high-resolution screenshot modal |

---

## 🎬 8 Presentation Scenes Breakdown

1. **Scene 01: Hero & Identity (0:00 – 0:45)**
   - Project emblem, core philosophy, and headline metrics ($0.00 Leakage, <0.5ms Policy Latency, 100% Auditability).
2. **Scene 02: The Urgent Dilemma (0:45 – 1:15)**
   - The uncontrolled AI spending threat: prompt injections, hallucinated invoices, and runaway autonomous loops.
3. **Scene 03: System Architecture (1:15 – 2:00)**
   - Interactive SVG flow diagram: LLM parsing -> Security Boundary -> **Pure Deterministic Policy Core (0ms I/O)** -> ALLOW / STEP_UP / DENY -> PayPal Settlement.
4. **Scene 04: Cryptographic Guarantees (2:00 – 2:45)**
   - Ed25519 asymmetric signatures, RFC 8785 canonical JSON digest, SHA-256 hash chains, and PostgreSQL append-only write triggers.
5. **Scene 05: Live Application Walkthrough (2:45 – 4:15)**
   - Interactive invoice decision tester:
     - **Sample A (ALLOW):** $25.00 cloud hosting bill passes instantly.
     - **Sample B (STEP_UP):** $1,200.00 annual license safely routes to the human supervisor queue.
     - **Sample C (DENY):** $9,999.00 hidden prompt injection killed on the spot.
6. **Scene 06: Adversarial Robustness & Attack Lab (4:15 – 4:55)**
   - Continuous testing across 6 canned attack vectors with a verified 0% bypass rate.
7. **Scene 07: Immutable Ledger & PayPal Settlement (4:55 – 5:35)**
   - Real PayPal Sandbox Orders v2 two-phase authorization and capture linked to the SHA-256 tamper-evident ledger.
8. **Scene 08: The Winning Pitch & Closing (5:35 – 6:00)**
   - Comparative differentiation matrix, GitHub repository link, and closing vision.

---

## 🎥 Recording a Video Demo (OBS / Screen Capture)

To capture a video recording of the demo:
1. Launch `launch.ps1` and press **F** to enter fullscreen mode (1920×1080 or 3840×2160).
2. Start your recording software (e.g., OBS Studio, Windows Game Bar `Win + G`, or Chrome Screen Recorder).
3. Press **SPACE** to start the voiceover and follow along with the right arrow key to transition through scenes.
4. The high-resolution thumbnail asset is available at `PHALANX_DEMO/output/PHALANX_Thumbnail.svg`.

---

## 📁 Package File Structure

```text
PHALANX_DEMO/
├── index.html                  # Runnable interactive HTML5 presentation engine
├── launch.ps1                  # One-click Windows PowerShell launcher
├── README.md                   # This instruction guide
├── narration.txt               # Full continuous voiceover script
├── storyboard.md               # Detailed scene-by-scene storyboard matrix
├── styles/
│   └── presentation.css        # Cinematic dark-mode fintech stylesheet
├── scripts/
│   └── presentation.js         # Navigation, Web Speech API & telemetry engine
├── assets/
│   ├── logo/logo.svg           # Authentic geometric PHALANX seal mark
│   ├── screenshots/            # 15 high-res production interface captures
│   ├── graphics/               # Vector illustrations and badges
│   ├── audio/                  # Audio asset directory
│   └── video/                  # Video clip directory
└── output/
    └── PHALANX_Thumbnail.svg   # 16:9 4K presentation thumbnail
```

---

## 🔒 Truthfulness & Disclosures
- **No Direct FFmpeg MP4 Encoding:** FFmpeg is not installed on this system. In accordance with project truthfulness rules, no fake binary `.mp4` is claimed. The interactive presentation provides full real-time rendering, Web Speech API narration, and synchronized visual cues.
- **Deterministic Pure Core:** The policy engine performs 0 network I/O and 0 clock operations during evaluation.
- **PayPal Sandbox:** All transactions execute on PayPal Sandbox Orders v2; no real money is transferred.
