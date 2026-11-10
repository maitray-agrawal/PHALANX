import React, { useState, useEffect } from "react";
import {
  Shield,
  Home,
  Send,
  CheckSquare,
  Activity,
  Menu,
  X,
  User,
  ExternalLink,
  Lock,
  Zap,
  Moon,
  Sun,
} from "lucide-react";
import { api } from "./api";
import { PillButton } from "./components/PillButton";
import { Toast } from "./components/Toast";
import { HomeScreen } from "./screens/HomeScreen";
import { PayScreen } from "./screens/PayScreen";
import { ApprovalsScreen } from "./screens/ApprovalsScreen";
import { ActivityScreen } from "./screens/ActivityScreen";
import { MandatesScreen } from "./screens/MandatesScreen";
import { AttackLabScreen } from "./screens/AttackLabScreen";
import { ReceiptVerifyScreen } from "./screens/ReceiptVerifyScreen";
import { InvoiceAgentScreen } from "./screens/InvoiceAgentScreen";

export type RoleType = "APPROVER" | "AGENT" | "PRINCIPAL" | "AUDITOR";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>("home");
  const [selectedReceiptId, setSelectedReceiptId] = useState<string | null>(null);
  const [currentRole, setCurrentRole] = useState<RoleType>("APPROVER");
  const [token, setToken] = useState<string>("");
  const [isDemoMode, setIsDemoMode] = useState<boolean>(true);
  const [theme, setTheme] = useState<"light" | "dark">("light");

  const [isMoreMenuOpen, setIsMoreMenuOpen] = useState(false);
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const [toasts, setToasts] = useState<Array<{ id: string; message: string; type: "success" | "error" | "info" }>>([]);

  // Apply theme to document element
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  // Handle URL hash routing
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace("#", "");
      if (hash.startsWith("receipt/")) {
        setSelectedReceiptId(hash.replace("receipt/", ""));
        setActiveTab("receipt");
      } else if (hash) {
        setActiveTab(hash);
      }
    };

    handleHashChange();
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  // Fetch initial token for selected role
  useEffect(() => {
    const fetchToken = async () => {
      try {
        const resp = await api.getDemoToken(
          currentRole.toLowerCase(),
          "principal_treasury",
          currentRole === "AGENT" ? "agent-auto-1" : undefined
        );
        setToken(resp.access_token);
        setIsDemoMode(true);
      } catch {
        // Production mode without demo token endpoint
        setIsDemoMode(false);
      }
    };
    fetchToken();
  }, [currentRole]);

  const addToast = (message: string, type: "success" | "error" | "info" = "info") => {
    const id = `toast_${Date.now()}_${Math.random()}`;
    setToasts((prev) => [...prev, { id, message, type }]);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const navigateTo = (tab: string, receiptId?: string) => {
    if (receiptId) {
      setSelectedReceiptId(receiptId);
      window.location.hash = `receipt/${receiptId}`;
    } else {
      window.location.hash = tab;
    }
    setActiveTab(tab);
    setIsMoreMenuOpen(false);
    setIsProfileMenuOpen(false);
    if (typeof window !== "undefined" && typeof window.scrollTo === "function") {
      try {
        window.scrollTo({ top: 0, behavior: "smooth" });
      } catch {
        // Fallback for jsdom
      }
    }
  };

  const toggleTheme = () => {
    setTheme((prev) => (prev === "light" ? "dark" : "light"));
  };

  return (
    <div className="phalanx-app-shell">
      {/* Toast Notification Container */}
      <div className="toast-viewport" aria-live="assertive">
        {toasts.map((t) => (
          <Toast
            key={t.id}
            id={t.id}
            type={t.type}
            message={t.message}
            onDismiss={() => removeToast(t.id)}
          />
        ))}
      </div>

      {/* Top Navigation Bar (Desktop & Mobile Header) */}
      <header className="app-topbar">
        <div className="topbar-inner">
          {/* Brand Wordmark & Subtle Shield */}
          <div
            className="brand-group"
            onClick={() => navigateTo("home")}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && navigateTo("home")}
          >
            <div className="brand-shield-icon" aria-hidden="true">
              <Shield size={20} className="shield-svg" />
            </div>
            <h1 className="brand-wordmark">PHALANX</h1>
            <span className="sandbox-indicator" title="PayPal Sandbox Guard Active">
              SANDBOX
            </span>
          </div>

          {/* Desktop Navigation Links */}
          <nav className="desktop-nav-links" aria-label="Main Navigation">
            <button
              type="button"
              className={`nav-link-btn ${activeTab === "home" ? "active" : ""}`}
              onClick={() => navigateTo("home")}
            >
              Home
            </button>
            <button
              type="button"
              className={`nav-link-btn ${activeTab === "pay" ? "active" : ""}`}
              onClick={() => navigateTo("pay")}
            >
              Pay
            </button>
            <button
              type="button"
              className={`nav-link-btn ${activeTab === "approvals" ? "active" : ""}`}
              onClick={() => navigateTo("approvals")}
            >
              Approvals
            </button>
            <button
              type="button"
              className={`nav-link-btn ${activeTab === "activity" ? "active" : ""}`}
              onClick={() => navigateTo("activity")}
            >
              Activity
            </button>
            <button
              type="button"
              className={`nav-link-btn ${activeTab === "mandates" ? "active" : ""}`}
              onClick={() => navigateTo("mandates")}
            >
              Mandates
            </button>
            <button
              type="button"
              className={`nav-link-btn ${activeTab === "invoice-agent" ? "active" : ""}`}
              onClick={() => navigateTo("invoice-agent")}
            >
              Invoice Agent
            </button>
            <button
              type="button"
              className={`nav-link-btn ${activeTab === "attack-lab" ? "active" : ""}`}
              onClick={() => navigateTo("attack-lab")}
            >
              Attack Lab
            </button>
          </nav>

          {/* Desktop Right Controls (Theme & Profile Persona) */}
          <div className="desktop-right-controls">
            <button
              type="button"
              className="theme-toggle-btn"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
            >
              {theme === "light" ? <Moon size={18} aria-hidden="true" /> : <Sun size={18} aria-hidden="true" />}
            </button>

            {/* Profile Menu Trigger */}
            <div className="profile-menu-container">
              <button
                type="button"
                className="profile-pill-trigger"
                onClick={() => setIsProfileMenuOpen(!isProfileMenuOpen)}
                aria-expanded={isProfileMenuOpen}
                aria-haspopup="true"
                aria-label={`Current persona: ${currentRole}. Click to switch role.`}
              >
                <User size={16} className="inline-icon" aria-hidden="true" />
                <span className="current-role-label mono">{currentRole}</span>
              </button>

              {/* Profile Dropdown */}
              {isProfileMenuOpen && (
                <div className="profile-dropdown-menu card" role="menu">
                  <div className="dropdown-header">
                    <span className="dropdown-title">Active Persona Role</span>
                    <span className="dropdown-hint">Object-Level Authorization</span>
                  </div>
                  <div className="role-switcher-grid">
                    {(["APPROVER", "AGENT", "PRINCIPAL", "AUDITOR"] as RoleType[]).map((r) => (
                      <button
                        key={r}
                        type="button"
                        className={`role-option-btn ${currentRole === r ? "selected" : ""}`}
                        onClick={() => {
                          setCurrentRole(r);
                          setIsProfileMenuOpen(false);
                          addToast(`Switched active persona to ${r}`, "info");
                        }}
                        role="menuitem"
                      >
                        <span className="mono">{r}</span>
                        {currentRole === r && <span className="active-dot" />}
                      </button>
                    ))}
                  </div>
                  {isDemoMode && (
                    <div className="demo-mode-note">
                      Demo mode active: Signed role tokens minted automatically.
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Envelope (Max Width 1120px) */}
      <main className="app-main-content">
        <div className="content-container">
          {activeTab === "home" && (
            <HomeScreen
              token={token}
              onNavigate={navigateTo}
              onNotify={addToast}
            />
          )}

          {activeTab === "pay" && (
            <PayScreen
              token={token}
              onNavigate={navigateTo}
              onNotify={addToast}
            />
          )}

          {activeTab === "approvals" && (
            <ApprovalsScreen
              token={token}
              role={currentRole}
              onNavigate={navigateTo}
              onNotify={addToast}
            />
          )}

          {activeTab === "activity" && (
            <ActivityScreen
              token={token}
              onNavigate={navigateTo}
              onNotify={addToast}
            />
          )}

          {activeTab === "mandates" && (
            <MandatesScreen
              token={token}
              onNavigate={navigateTo}
              onNotify={addToast}
            />
          )}

          {activeTab === "invoice-agent" && (
            <InvoiceAgentScreen
              token={token}
              onNotify={addToast}
            />
          )}

          {activeTab === "attack-lab" && (
            <AttackLabScreen
              token={token}
              onNotify={addToast}
            />
          )}

          {activeTab === "receipt" && (
            <ReceiptVerifyScreen
              receiptId={selectedReceiptId}
              token={token}
              onBack={() => navigateTo("activity")}
              onNotify={addToast}
            />
          )}
        </div>
      </main>

      {/* Mobile Sticky Action (Below 768px on Home) */}
      {activeTab === "home" && (
        <div className="mobile-sticky-action-bar">
          <PillButton
            variant="primary"
            size="lg"
            icon={<Send size={18} />}
            className="w-full"
            onClick={() => navigateTo("pay")}
          >
            Pay & Request
          </PillButton>
        </div>
      )}

      {/* Mobile Bottom Tab Bar (Below 768px) */}
      <nav className="mobile-bottom-tabbar" aria-label="Mobile Navigation">
        <button
          type="button"
          className={`tabbar-item ${activeTab === "home" ? "active" : ""}`}
          onClick={() => navigateTo("home")}
          aria-label="Home"
        >
          <Home size={20} aria-hidden="true" />
          <span>Home</span>
        </button>

        <button
          type="button"
          className={`tabbar-item ${activeTab === "pay" ? "active" : ""}`}
          onClick={() => navigateTo("pay")}
          aria-label="Pay"
        >
          <Send size={20} aria-hidden="true" />
          <span>Pay</span>
        </button>

        <button
          type="button"
          className={`tabbar-item ${activeTab === "approvals" ? "active" : ""}`}
          onClick={() => navigateTo("approvals")}
          aria-label="Approvals"
        >
          <CheckSquare size={20} aria-hidden="true" />
          <span>Approvals</span>
        </button>

        <button
          type="button"
          className={`tabbar-item ${activeTab === "activity" ? "active" : ""}`}
          onClick={() => navigateTo("activity")}
          aria-label="Activity"
        >
          <Activity size={20} aria-hidden="true" />
          <span>Activity</span>
        </button>

        <button
          type="button"
          className={`tabbar-item ${isMoreMenuOpen ? "active" : ""}`}
          onClick={() => setIsMoreMenuOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={isMoreMenuOpen}
          aria-label="More"
        >
          <Menu size={20} aria-hidden="true" />
          <span>More</span>
        </button>
      </nav>

      {/* Mobile "More" Sheet Modal */}
      {isMoreMenuOpen && (
        <div className="mobile-more-backdrop" onClick={() => setIsMoreMenuOpen(false)}>
          <div
            className="mobile-more-sheet"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="More Navigation Options"
          >
            <div className="sheet-handle-bar" />
            <div className="sheet-header">
              <h3 className="sheet-title">More Services & Options</h3>
              <button
                type="button"
                className="sheet-close-btn"
                onClick={() => setIsMoreMenuOpen(false)}
                aria-label="Close menu"
              >
                <X size={20} aria-hidden="true" />
              </button>
            </div>

            <div className="sheet-nav-list">
              <button
                type="button"
                className="sheet-nav-item"
                onClick={() => navigateTo("mandates")}
              >
                <Lock size={18} className="sheet-icon" aria-hidden="true" />
                <div className="sheet-text">
                  <span className="sheet-item-title">Ed25519 Authority Mandate</span>
                  <span className="sheet-item-sub">Budget limits and allowlists</span>
                </div>
              </button>

              <button
                type="button"
                className="sheet-nav-item"
                onClick={() => navigateTo("invoice-agent")}
              >
                <Zap size={18} className="sheet-icon text-blue-500" aria-hidden="true" />
                <div className="sheet-text">
                  <span className="sheet-item-title">Invoice Agent (Autonomous AI)</span>
                  <span className="sheet-item-sub">Gemini parsing with PHALANX guardrails</span>
                </div>
              </button>

              <button
                type="button"
                className="sheet-nav-item"
                onClick={() => navigateTo("attack-lab")}
              >
                <Zap size={18} className="sheet-icon text-accent" aria-hidden="true" />
                <div className="sheet-text">
                  <span className="sheet-item-title">Adversarial Attack Lab</span>
                  <span className="sheet-item-sub">Test 6 canned threat vectors</span>
                </div>
              </button>

              <button
                type="button"
                className="sheet-nav-item"
                onClick={() => navigateTo("receipt")}
              >
                <ExternalLink size={18} className="sheet-icon" aria-hidden="true" />
                <div className="sheet-text">
                  <span className="sheet-item-title">Receipt & Proof Verifier</span>
                  <span className="sheet-item-sub">Public SHA-256 chain verification</span>
                </div>
              </button>
            </div>

            {/* Persona Switcher in More Sheet */}
            {isDemoMode && (
              <div className="sheet-persona-section">
                <span className="sheet-section-title">Demo Persona Switcher</span>
                <div className="persona-grid">
                  {(["APPROVER", "AGENT", "PRINCIPAL", "AUDITOR"] as RoleType[]).map((r) => (
                    <button
                      key={r}
                      type="button"
                      className={`persona-pill ${currentRole === r ? "active" : ""}`}
                      onClick={() => {
                        setCurrentRole(r);
                        setIsMoreMenuOpen(false);
                        addToast(`Switched active persona to ${r}`, "info");
                      }}
                    >
                      <span className="mono">{r}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="sheet-theme-row">
              <span>Theme Appearance</span>
              <PillButton
                variant="secondary"
                size="sm"
                icon={theme === "light" ? <Moon size={14} /> : <Sun size={14} />}
                onClick={toggleTheme}
              >
                {theme === "light" ? "Dark Theme" : "Light Theme"}
              </PillButton>
            </div>
          </div>
        </div>
      )}

      {/* Global Footer on All Views */}
      <footer className="app-footer">
        <div className="footer-inner">
          <p className="footer-disclaimer">Not affiliated with PayPal.</p>
          <p className="footer-meta">
            PHALANX Autonomous Financial Agent Authorization Layer • PayPal AI Hackathon 2026 Entry • Sandbox Only
          </p>
        </div>
      </footer>
    </div>
  );
};

export default App;
