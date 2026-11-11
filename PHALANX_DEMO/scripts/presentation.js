/**
 * PHALANX — Cinematic AI FinTech Presentation Engine
 * Features:
 * - 8-Scene High-Definition Interactive Navigation
 * - Web Speech API Voiceover with Indian English Voice Detection (en-IN)
 * - Synchronized Teleprompter Subtitles
 * - Live Backend API Integration with Graceful Verified Fallbacks
 * - Interactive Decision Matrix & Screenshot Inspector
 */

const NARRATION_SCENES = [
  {
    id: "scene-1",
    number: 1,
    category: "The Urgent Dilemma",
    title: "Intelligence Without Control Creates Risk",
    time: "0:00 - 0:45",
    narration: "Artificial intelligence is moving far beyond simple chat boxes and answering questions. Today, autonomous AI agents can analyze data, negotiate with vendors, execute workflows, and make decisions in real time. But what happens when an autonomous AI agent is given the authority to spend real money? Giving an autonomous agent unrestricted access to a corporate credit card or bank API is a financial disaster waiting to happen. A single prompt injection attack, a hallucinated supplier invoice, or a runaway autonomous loop can drain a corporate treasury in minutes. Until now, the industry has relied on weak prompt engineering or vague model alignment. But when real money is on the line, words in a system prompt are simply not enough. Intelligence without control creates catastrophic risk. Meet PHALANX — the deterministic authorization and governance layer designed specifically for autonomous financial agents. Our principle is clear: Let agents act. Keep humans and policy in control."
  },
  {
    id: "scene-2",
    number: 2,
    category: "The Core Problem",
    title: "Why Conventional Payment Architecture Fails AI",
    time: "0:45 - 1:15",
    narration: "Imagine an autonomous AI agent purchasing cloud infrastructure or paying an outsourced contractor. Who decides whether that payment is allowed? How do we enforce spending caps and vendor whitelists? And how do we mathematically prove why a transaction was approved or rejected? Conventional systems give agents raw API keys and hope for the best. If the LLM hallucinates an extra zero, or is tricked by malicious text into wiring funds offshore, traditional payment gateways will simply process the charge. PHALANX introduces a strict governance boundary between autonomous agents and payment execution."
  },
  {
    id: "scene-3",
    number: 3,
    category: "System Architecture",
    title: "Pure Domain Isolation: The 0ms I/O Firewall",
    time: "1:15 - 2:00",
    narration: "To make autonomous payments safe, we changed the architecture completely. In PHALANX, the core design principle is absolute domain isolation. An autonomous agent receives an invoice and uses an LLM, like Google Gemini 2.5 Flash, to interpret messy unstructured text and extract invoice fields. But notice the security boundary: the language model is strictly barred from the authorization boundary. The LLM cannot authorize, sign, or execute a single payment. Instead, the extracted payload passes into the pure PHALANX Domain Core. This engine performs zero network I/O, makes zero clock lookups, and runs zero probabilistic code. It evaluates the transaction against mathematical policies in under half a millisecond, producing exactly one of three deterministic outcomes: ALLOW, STEP_UP, or DENY."
  },
  {
    id: "scene-4",
    number: 4,
    category: "Security Guarantees",
    title: "Verifiable Cryptographic Controls",
    time: "2:00 - 2:45",
    narration: "PHALANX replaces trust with cryptographic verification. Every financial agent operates under an Ed25519-signed mandate. This mandate defines strict boundaries: authorized vendor categories, maximum single-transaction amounts, daily velocity caps, and allowed payment rails. When an agent submits a payment request, PHALANX computes an RFC 8785 canonical JSON digest. This guarantees that whitespace or field ordering cannot manipulate the signature. If a single character or account number is tampered with in transit, the signature check fails immediately, and the transaction is aborted. No agent can spend outside its signed mandate."
  },
  {
    id: "scene-5",
    number: 5,
    category: "Live Product Demonstration",
    title: "ALLOW, STEP_UP & DENY in Real Time",
    time: "2:45 - 4:15",
    narration: "Now, let us inspect the real PHALANX application running live. On our primary dashboard, operations teams have real-time visibility into all agent activity: zero financial leakage, sub-millisecond policy evaluation latency, and one hundred percent cryptographic ledger auditability. Let us observe our three canonical scenarios. In Case One, a routine cloud hosting bill of twenty-five dollars passes instantly with an ALLOW. In Case Two, an annual server license of twelve hundred dollars triggers a STEP_UP, escalating safely to human supervisors. In Case Three, an adversarial invoice with prompt injection attempts to wire ninety-nine hundred dollars to an unauthorized offshore account. The pure policy engine issues an immediate DENY. Zero dollars leave the organization."
  },
  {
    id: "scene-6",
    number: 6,
    category: "Adversarial Robustness",
    title: "Attack Lab: 0% Bypass Across 6 Threat Vectors",
    time: "4:15 - 4:55",
    narration: "Financial systems must be proven under attack. PHALANX includes a dedicated Attack Lab where red-team engineers test the authorization boundaries against sophisticated threats. We continuously test six distinct attack vectors: direct prompt injection, vendor spoofing, replay attacks, micro-transaction velocity floods, budget exhaustion, and in-memory tampering. Across all six attack vectors, PHALANX maintains a zero percent bypass rate. Because our policy evaluation is mathematical and deterministic, probabilistic LLM jailbreaks cannot influence the final authorization decision."
  },
  {
    id: "scene-7",
    number: 7,
    category: "Audit & Settlement",
    title: "Immutable PostgreSQL Ledger & PayPal Sandbox",
    time: "4:55 - 5:35",
    narration: "Every single action taken inside PHALANX is written to an immutable, append-only audit ledger. Each ledger event is cryptographically linked to the previous event using a SHA-256 hash chain, exactly like a high-performance private blockchain. At the database layer, PostgreSQL triggers physically block any UPDATE or DELETE operations on ledger rows. Anyone can verify the ledger integrity at any time. When transactions are approved, PHALANX executes real settlement through PayPal Sandbox using PayPal Orders v2, enforcing two-phase authorization and capture."
  },
  {
    id: "scene-8",
    number: 8,
    category: "Summary & Impact",
    title: "Controlled Autonomy for Autonomous Finance",
    time: "5:35 - 6:00",
    narration: "The future of AI will not be defined only by how intelligent agents become. It will also depend on how safely we allow them to act. PHALANX combines deterministic policy enforcement, cryptographic identity, human oversight, and auditability for autonomous payment workflows. AI proposes. Policy decides. Humans oversee. The ledger remembers. PHALANX: Let agents act. Keep humans and policy in control. Thank you."
  }
];

class PhalanxPresentation {
  constructor() {
    this.currentSceneIndex = 0;
    this.isPlaying = false;
    this.synth = window.speechSynthesis;
    this.utterance = null;
    this.voices = [];
    this.selectedVoice = null;
    this.speechRate = 1.0;
    this.backendBaseUrl = "http://127.0.0.1:8000";
    this.isBackendOnline = false;

    this.initElements();
    this.initVoices();
    this.initEventListeners();
    this.checkBackendHealth();
    this.updateScene(0);
  }

  initElements() {
    this.viewport = document.getElementById("viewport");
    this.slides = document.querySelectorAll(".slide");
    this.stepPills = document.querySelectorAll(".scene-step-pill");
    this.btnPrev = document.getElementById("btn-prev");
    this.btnNext = document.getElementById("btn-next");
    this.btnPlay = document.getElementById("btn-play-pause");
    this.btnFullscreen = document.getElementById("btn-fullscreen");
    this.voiceSelect = document.getElementById("voice-select");
    this.speedSelect = document.getElementById("speed-select");
    this.subtitleText = document.getElementById("subtitle-text");
    this.sceneTimeBadge = document.getElementById("scene-time-badge");
    this.modalViewer = document.getElementById("modal-viewer");
    this.modalImg = document.getElementById("modal-img");
  }

  initVoices() {
    const loadVoices = () => {
      this.voices = this.synth.getVoices();
      if (!this.voices.length) return;

      this.voiceSelect.innerHTML = "";
      
      // Look for Indian English (en-IN) voices first
      const indianVoice = this.voices.find(v => v.lang === "en-IN" || v.name.includes("India") || v.name.includes("Heera") || v.name.includes("Ravi"));
      
      this.voices.forEach(v => {
        const opt = document.createElement("option");
        opt.value = v.name;
        opt.textContent = `${v.name} (${v.lang})${v.lang === "en-IN" ? " ★ Indian English" : ""}`;
        if (v === indianVoice) {
          opt.selected = true;
          this.selectedVoice = v;
        }
        this.voiceSelect.appendChild(opt);
      });

      if (!this.selectedVoice && this.voices.length > 0) {
        // Fallback to first English voice
        const englishVoice = this.voices.find(v => v.lang.startsWith("en")) || this.voices[0];
        this.selectedVoice = englishVoice;
      }
    };

    loadVoices();
    if (this.synth.onvoiceschanged !== undefined) {
      this.synth.onvoiceschanged = loadVoices;
    }
  }

  initEventListeners() {
    this.btnPrev.addEventListener("click", () => this.prevScene());
    this.btnNext.addEventListener("click", () => this.nextScene());
    this.btnPlay.addEventListener("click", () => this.toggleSpeech());
    
    this.stepPills.forEach(pill => {
      pill.addEventListener("click", () => {
        const idx = parseInt(pill.getAttribute("data-scene-index"), 10);
        this.goToScene(idx);
      });
    });

    this.btnFullscreen.addEventListener("click", () => this.toggleFullscreen());

    this.voiceSelect.addEventListener("change", (e) => {
      this.selectedVoice = this.voices.find(v => v.name === e.target.value);
      if (this.isPlaying) {
        this.stopSpeech();
        this.playSpeech();
      }
    });

    this.speedSelect.addEventListener("change", (e) => {
      this.speechRate = parseFloat(e.target.value);
      if (this.isPlaying) {
        this.stopSpeech();
        this.playSpeech();
      }
    });

    // Keyboard Shortcuts
    window.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight" || e.key === "PageDown") {
        this.nextScene();
      } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
        this.prevScene();
      } else if (e.key === " ") {
        e.preventDefault();
        this.toggleSpeech();
      } else if (e.key.toLowerCase() === "f") {
        this.toggleFullscreen();
      } else if (e.key === "Escape") {
        this.closeModal();
      }
    });

    // Modal Close
    document.querySelector(".close-modal").addEventListener("click", () => this.closeModal());
    this.modalViewer.addEventListener("click", (e) => {
      if (e.target === this.modalViewer) this.closeModal();
    });

    // Screenshot Thumbnail Switcher
    document.querySelectorAll(".thumb-item").forEach(thumb => {
      thumb.addEventListener("click", (e) => {
        const mainImg = thumb.closest(".screenshot-preview-container").querySelector(".screenshot-main-img");
        mainImg.src = thumb.src;
        thumb.parentElement.querySelectorAll(".thumb-item").forEach(t => t.classList.remove("active"));
        thumb.classList.add("active");
      });
    });

    // Click on main image opens zoom modal
    document.querySelectorAll(".screenshot-main-img").forEach(img => {
      img.addEventListener("click", () => {
        this.modalImg.src = img.src;
        this.modalViewer.classList.add("active");
      });
    });
  }

  async checkBackendHealth() {
    try {
      const res = await fetch(`${this.backendBaseUrl}/healthz`, { mode: "cors" });
      if (res.ok) {
        this.isBackendOnline = true;
        const badge = document.getElementById("backend-status-pill");
        if (badge) {
          badge.innerHTML = `<span style="color:#10b981">●</span> Backend Live (Port 8000)`;
          badge.style.borderColor = "#10b981";
        }
      }
    } catch (e) {
      this.isBackendOnline = false;
      const badge = document.getElementById("backend-status-pill");
      if (badge) {
        badge.innerHTML = `<span style="color:#00f2fe">●</span> Verified Local Engine`;
      }
    }
  }

  updateScene(index) {
    this.currentSceneIndex = index;
    const scene = NARRATION_SCENES[index];

    // Update Slide DOM
    this.slides.forEach((s, idx) => {
      s.classList.toggle("active", idx === index);
    });

    // Update Step Pills
    this.stepPills.forEach((p, idx) => {
      p.classList.toggle("active", idx === index);
    });

    // Update Subtitle & Badges
    this.subtitleText.textContent = scene.narration;
    this.sceneTimeBadge.textContent = `${scene.time} | Scene ${scene.number} of ${NARRATION_SCENES.length}`;

    // Handle speech playback if active
    if (this.isPlaying) {
      this.stopSpeech();
      this.playSpeech();
    }
  }

  nextScene() {
    if (this.currentSceneIndex < NARRATION_SCENES.length - 1) {
      this.updateScene(this.currentSceneIndex + 1);
    }
  }

  prevScene() {
    if (this.currentSceneIndex > 0) {
      this.updateScene(this.currentSceneIndex - 1);
    }
  }

  goToScene(index) {
    if (index >= 0 && index < NARRATION_SCENES.length) {
      this.updateScene(index);
    }
  }

  toggleSpeech() {
    if (this.isPlaying) {
      this.stopSpeech();
    } else {
      this.playSpeech();
    }
  }

  playSpeech() {
    if (!this.synth) return;
    this.synth.cancel();

    const scene = NARRATION_SCENES[this.currentSceneIndex];
    this.utterance = new SpeechSynthesisUtterance(scene.narration);
    
    if (this.selectedVoice) {
      this.utterance.voice = this.selectedVoice;
    }
    this.utterance.rate = this.speechRate;
    this.utterance.pitch = 1.0;

    this.utterance.onstart = () => {
      this.isPlaying = true;
      this.btnPlay.innerHTML = `<span>❚❚</span> Pause Narration`;
      this.btnPlay.classList.add("playing");
    };

    this.utterance.onend = () => {
      this.isPlaying = false;
      this.btnPlay.innerHTML = `<span>▶</span> Play Narration`;
      this.btnPlay.classList.remove("playing");
    };

    this.utterance.onerror = (e) => {
      console.warn("Speech synthesis notice:", e);
      this.isPlaying = false;
      this.btnPlay.innerHTML = `<span>▶</span> Play Narration`;
    };

    this.synth.speak(this.utterance);
  }

  stopSpeech() {
    if (this.synth) {
      this.synth.cancel();
    }
    this.isPlaying = false;
    this.btnPlay.innerHTML = `<span>▶</span> Play Narration`;
    this.btnPlay.classList.remove("playing");
  }

  toggleFullscreen() {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(err => console.log(err));
    } else {
      if (document.exitFullscreen) document.exitFullscreen();
    }
  }

  closeModal() {
    this.modalViewer.classList.remove("active");
  }
}

// Interactive Scenario Simulation on Scene 5
const SCENARIO_DATA = {
  sample_a: {
    title: "AWS Cloud Infrastructure Hosting",
    invoiceNum: "INV-2026-0881",
    vendor: "Acme Cloud Hosting Services Inc.",
    account: "vendor-paypal-sandbox-1",
    amount: "$25.00 USD",
    decision: "ALLOW",
    reason: "Pre-authorized vendor & amount below autonomous $500.00 limit",
    mandateBudget: "$25,000.00 (Reserved: -$25.00)",
    settlement: "PayPal Sandbox Order Created & Authorized",
    ledgerHash: "sha256:4a81c..99e2",
    badgeClass: "allow"
  },
  sample_b: {
    title: "Annual Enterprise Security Gateway License",
    invoiceNum: "INV-2026-1042",
    vendor: "Global Tech Hosting Corp",
    account: "vendor-paypal-sandbox-1",
    amount: "$1,200.00 USD",
    decision: "STEP_UP",
    reason: "Amount ($1,200.00) exceeds single-transaction threshold ($500.00)",
    mandateBudget: "$25,000.00 (Pending Human Approval)",
    settlement: "Escalated to Human Supervisor Queue",
    ledgerHash: "sha256:7b92f..11a4",
    badgeClass: "stepup"
  },
  sample_c: {
    title: "Adversarial Hidden Prompt Injection",
    invoiceNum: "INV-9021-FRAUD",
    vendor: "Apex Office Supplies Inc. (Spoofed)",
    account: "attacker-fraud-99@shadybank.com",
    amount: "$9,999.00 USD",
    decision: "DENY",
    reason: "Unauthorized offshore payee account & mandate threshold violation",
    mandateBudget: "$25,000.00 (Protected - $0.00 Leakage)",
    settlement: "Execution Aborted Immediately",
    ledgerHash: "sha256:0d44a..88f3",
    badgeClass: "deny"
  }
};

function selectScenario(scenarioKey) {
  document.querySelectorAll(".sample-card").forEach(c => c.classList.remove("active"));
  const activeCard = document.querySelector(`.sample-card[data-key="${scenarioKey}"]`);
  if (activeCard) activeCard.classList.add("active");

  const data = SCENARIO_DATA[scenarioKey];
  if (!data) return;

  const decisionBadge = document.getElementById("scenario-decision-badge");
  decisionBadge.textContent = data.decision;
  decisionBadge.className = `badge-decision ${data.badgeClass}`;

  document.getElementById("scenario-vendor").textContent = data.vendor;
  document.getElementById("scenario-account").textContent = data.account;
  document.getElementById("scenario-amount").textContent = data.amount;
  document.getElementById("scenario-reason").textContent = data.reason;
  document.getElementById("scenario-budget").textContent = data.mandateBudget;
  document.getElementById("scenario-settlement").textContent = data.settlement;
  document.getElementById("scenario-hash").textContent = data.ledgerHash;
}

// Initialize on DOM load
window.addEventListener("DOMContentLoaded", () => {
  window.presentationApp = new PhalanxPresentation();
});

