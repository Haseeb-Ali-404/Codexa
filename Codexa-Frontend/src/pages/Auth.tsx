import React, { useState, useEffect, useRef, useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

/* ═══════════════════════════════════════════════════════
   TYPE DEFINITIONS
═══════════════════════════════════════════════════════ */
interface AuthFormData {
  name?: string;
  email: string;
  password: string;
  confirm_password?: string;
}

interface FieldError {
  name?: string;
  email?: string;
  password?: string;
  confirm_password?: string;
}

type AuthMode = "login" | "signup";
type AppState = "idle" | "loading" | "success" | "error" | "forgot";

/* ═══════════════════════════════════════════════════════
   PASSWORD STRENGTH CALCULATOR
═══════════════════════════════════════════════════════ */
function getPasswordStrength(password: string): {
  score: number;
  label: string;
  color: string;
  gradient: string;
} {
  let score = 0;
  if (password.length >= 8) score++;
  if (password.length >= 12) score++;
  if (/[A-Z]/.test(password)) score++;
  if (/[0-9]/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;

  const levels = [
    {
      label: "Too weak",
      color: "#ef4444",
      gradient: "linear-gradient(90deg,#ef4444,#f97316)",
    },
    {
      label: "Weak",
      color: "#f97316",
      gradient: "linear-gradient(90deg,#f97316,#eab308)",
    },
    {
      label: "Fair",
      color: "#eab308",
      gradient: "linear-gradient(90deg,#eab308,#84cc16)",
    },
    {
      label: "Strong",
      color: "#22c55e",
      gradient: "linear-gradient(90deg,#22c55e,#10b981)",
    },
    {
      label: "Very strong",
      color: "#8b5cf6",
      gradient: "linear-gradient(90deg,#8b5cf6,#6366f1)",
    },
  ];

  const idx = Math.max(0, Math.min(score - 1, 4));
  return { score, ...levels[Math.max(0, password.length === 0 ? -1 : idx)] };
}

/* ═══════════════════════════════════════════════════════
   VALIDATION
═══════════════════════════════════════════════════════ */
function validateField(
  name: string,
  value: string,
  formData?: AuthFormData,
): string {
  switch (name) {
    case "name":
      if (!value.trim()) return "Full name is required";
      if (value.trim().length < 2) return "Name must be at least 2 characters";
      return "";
    case "email":
      if (!value) return "Email is required";
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value))
        return "Enter a valid email address";
      return "";
    case "password":
      if (!value) return "Password is required";
      if (value.length < 8) return "Password must be at least 8 characters";
      return "";
    case "confirm_password":
      if (!value) return "Please confirm your password";
      if (formData && value !== formData.password)
        return "Passwords do not match";
      return "";
    default:
      return "";
  }
}

/* ═══════════════════════════════════════════════════════
   SVG ICONS
═══════════════════════════════════════════════════════ */
const IconGoogle = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <path
      d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"
      fill="#4285F4"
    />
    <path
      d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z"
      fill="#34A853"
    />
    <path
      d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"
      fill="#FBBC05"
    />
    <path
      d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"
      fill="#EA4335"
    />
  </svg>
);

const IconGithub = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
  </svg>
);

const IconCheck = () => (
  <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
    <path
      d="M6 16l7 7L26 9"
      stroke="white"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{
        strokeDasharray: 30,
        strokeDashoffset: 30,
        animation: "drawCheck 0.5s 0.1s ease forwards",
      }}
    />
  </svg>
);

const IconEyeOn = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

const IconEyeOff = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" />
    <line x1="1" y1="1" x2="23" y2="23" />
  </svg>
);

const IconMail = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
    <polyline points="22,6 12,13 2,6" />
  </svg>
);

const IconUser = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);

const IconLock = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
    <path d="M7 11V7a5 5 0 0110 0v4" />
  </svg>
);

/* ═══════════════════════════════════════════════════════
   ANIMATED FLOAT BLOBS
═══════════════════════════════════════════════════════ */
const FloatBlob: React.FC<{
  style?: React.CSSProperties;
  className?: string;
}> = ({ style, className }) => (
  <div
    className={className}
    style={{
      position: "absolute",
      borderRadius: "50%",
      filter: "blur(50px)",
      pointerEvents: "none",
      ...style,
    }}
  />
);

/* ═══════════════════════════════════════════════════════
   FLOATING LABEL INPUT
═══════════════════════════════════════════════════════ */
interface FloatingInputProps {
  label: string;
  name: string;
  type?: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onBlur?: (e: React.FocusEvent<HTMLInputElement>) => void;
  error?: string;
  icon?: React.ReactNode;
  rightElement?: React.ReactNode;
  autoComplete?: string;
  disabled?: boolean;
}

const FloatingInput: React.FC<FloatingInputProps> = ({
  label,
  name,
  type = "text",
  value,
  onChange,
  onBlur,
  error,
  icon,
  rightElement,
  autoComplete,
  disabled,
}) => {
  const [focused, setFocused] = useState(false);
  const isFloating = focused || value.length > 0;

  return (
    <div style={{ position: "relative", marginBottom: "4px" }}>
      <div
        style={{
          position: "relative",
          borderRadius: "12px",
          background: "rgba(255,255,255,0.04)",
          border: `1px solid ${error ? "rgba(239,68,68,0.6)" : focused ? "rgba(139,92,246,0.7)" : "rgba(255,255,255,0.09)"}`,
          transition: "border-color 0.2s ease, box-shadow 0.2s ease",
          boxShadow:
            focused && !error
              ? "0 0 0 3px rgba(124,58,237,0.12), 0 0 20px rgba(124,58,237,0.08)"
              : error
                ? "0 0 0 3px rgba(239,68,68,0.08)"
                : "none",
        }}
      >
        {/* Icon */}
        {icon && (
          <div
            style={{
              position: "absolute",
              left: "14px",
              top: "50%",
              transform: "translateY(-50%)",
              color: focused ? "#a78bfa" : "#5a5a72",
              transition: "color 0.2s ease",
              pointerEvents: "none",
              zIndex: 2,
            }}
          >
            {icon}
          </div>
        )}

        {/* Floating label */}
        <label
          style={{
            position: "absolute",
            left: icon ? "42px" : "14px",
            top: isFloating ? "8px" : "50%",
            transform: isFloating
              ? "translateY(0) scale(0.78)"
              : "translateY(-50%)",
            transformOrigin: "left center",
            color: error ? "#f87171" : focused ? "#a78bfa" : "#5a5a72",
            fontSize: "14px",
            fontWeight: 500,
            pointerEvents: "none",
            transition: "all 0.2s cubic-bezier(0.4,0,0.2,1)",
            zIndex: 2,
            whiteSpace: "nowrap",
          }}
        >
          {label}
        </label>

        <input
          className="auth-input"
          name={name}
          type={type}
          value={value}
          onChange={onChange}
          onFocus={() => setFocused(true)}
          onBlur={(e) => {
            setFocused(false);
            onBlur?.(e);
          }}
          autoComplete={autoComplete}
          disabled={disabled}
          style={{
            width: "100%",
            background: "transparent",
            border: "none",
            outline: "none",
            color: "#f0f0f8",
            caretColor: "#a78bfa",
            colorScheme: "dark",
            fontSize: "14.5px",
            fontWeight: 400,
            fontFamily: "'Outfit', sans-serif",
            padding: isFloating
              ? `${icon ? "22px 44px 8px" : "22px 14px 8px"}`
              : `${icon ? "16px 44px 16px" : "16px 14px"}`,
            paddingLeft: icon ? "42px" : "14px",
            paddingRight: rightElement ? "44px" : "14px",
            paddingTop: isFloating ? "22px" : "16px",
            paddingBottom: isFloating ? "8px" : "16px",
            transition: "padding 0.2s ease",
            cursor: disabled ? "not-allowed" : "text",
            opacity: disabled ? 0.5 : 1,
          }}
        />

        {/* Right element (eye toggle etc) */}
        {rightElement && (
          <div
            style={{
              position: "absolute",
              right: "12px",
              top: "50%",
              transform: "translateY(-50%)",
              zIndex: 2,
            }}
          >
            {rightElement}
          </div>
        )}
      </div>

      {/* Error message */}
      {error && (
        <p
          style={{
            color: "#f87171",
            fontSize: "11.5px",
            marginTop: "5px",
            paddingLeft: "14px",
            display: "flex",
            alignItems: "center",
            gap: "5px",
            animation: "slideDown 0.2s ease",
          }}
        >
          <span style={{ fontSize: "10px" }}>⚠</span> {error}
        </p>
      )}
    </div>
  );
};

/* ═══════════════════════════════════════════════════════
   AI LOADER
═══════════════════════════════════════════════════════ */
const AILoader: React.FC<{ text?: string }> = ({ text = "Authenticating" }) => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      gap: "10px",
    }}
  >
    <div style={{ display: "flex", gap: "4px", alignItems: "center" }}>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          style={{
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            background: "linear-gradient(135deg, #a78bfa, #818cf8)",
            animation: `aiDot 1.2s ease-in-out infinite`,
            animationDelay: `${i * 0.2}s`,
          }}
        />
      ))}
    </div>
    <span
      style={{
        color: "#a78bfa",
        fontSize: "14px",
        fontWeight: 500,
        letterSpacing: "0.02em",
      }}
    >
      {text}
    </span>
  </div>
);

/* ═══════════════════════════════════════════════════════
   SUCCESS ANIMATION
═══════════════════════════════════════════════════════ */
const SuccessState: React.FC<{ mode: AuthMode }> = ({ mode }) => (
  <div
    style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      padding: "32px 0",
      gap: "16px",
      animation: "fadeScaleIn 0.4s ease forwards",
    }}
  >
    <div
      style={{
        width: "72px",
        height: "72px",
        borderRadius: "50%",
        background:
          "linear-gradient(135deg, rgba(124,58,237,0.25), rgba(79,70,229,0.25))",
        border: "2px solid rgba(139,92,246,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow:
          "0 0 40px rgba(124,58,237,0.4), 0 0 80px rgba(124,58,237,0.15)",
        animation: "successPulse 1.5s ease-in-out infinite",
      }}
    >
      <IconCheck />
    </div>
    <div style={{ textAlign: "center" }}>
      <p
        style={{
          color: "#f0f0f8",
          fontWeight: 700,
          fontSize: "18px",
          margin: 0,
        }}
      >
        {mode === "login" ? "Welcome back!" : "Account created!"}
      </p>
      <p style={{ color: "#9898b0", fontSize: "13px", marginTop: "6px" }}>
        Redirecting you to the dashboard…
      </p>
    </div>
    <div
      style={{
        display: "flex",
        gap: "4px",
      }}
    >
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          style={{
            width: "4px",
            height: "4px",
            borderRadius: "50%",
            background: "linear-gradient(135deg, #8b5cf6, #4f46e5)",
            animation: `aiDot 1s ease-in-out infinite`,
            animationDelay: `${i * 0.12}s`,
          }}
        />
      ))}
    </div>
  </div>
);

/* ═══════════════════════════════════════════════════════
   FORGOT PASSWORD PANEL
═══════════════════════════════════════════════════════ */
const ForgotPanel: React.FC<{ onBack: () => void }> = ({ onBack }) => {
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    const err = validateField("email", email);
    if (err) {
      setEmailError(err);
      return;
    }
    setLoading(true);
    await new Promise((r) => setTimeout(r, 1800));
    setLoading(false);
    setSent(true);
  };

  return (
    <div
      style={{
        animation: "slideRight 0.35s cubic-bezier(0.4,0,0.2,1) forwards",
      }}
    >
      {/* Back button */}
      <button
        onClick={onBack}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "#9898b0",
          fontSize: "13px",
          fontWeight: 500,
          padding: "0 0 20px 0",
          transition: "color 0.2s",
          fontFamily: "'Outfit', sans-serif",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = "#a78bfa")}
        onMouseLeave={(e) => (e.currentTarget.style.color = "#9898b0")}
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Back to login
      </button>

      {!sent ? (
        <>
          <div style={{ marginBottom: "24px" }}>
            <div
              style={{
                width: "48px",
                height: "48px",
                borderRadius: "12px",
                background:
                  "linear-gradient(135deg, rgba(124,58,237,0.2), rgba(79,70,229,0.2))",
                border: "1px solid rgba(139,92,246,0.3)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                marginBottom: "16px",
                boxShadow: "0 0 20px rgba(124,58,237,0.2)",
              }}
            >
              <IconMail />
            </div>
            <h3
              style={{
                color: "#f0f0f8",
                fontSize: "22px",
                fontWeight: 700,
                margin: "0 0 8px 0",
                letterSpacing: "-0.02em",
              }}
            >
              Reset password
            </h3>
            <p
              style={{
                color: "#9898b0",
                fontSize: "13.5px",
                lineHeight: 1.6,
                margin: 0,
              }}
            >
              Enter the email associated with your CODEXA account. We'll send
              you a secure reset link.
            </p>
          </div>

          <FloatingInput
            label="Email address"
            name="reset-email"
            type="email"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              setEmailError("");
            }}
            onBlur={() => setEmailError(validateField("email", email))}
            error={emailError}
            icon={<IconMail />}
            autoComplete="email"
          />

          <button
            onClick={handleSend}
            disabled={loading}
            style={{
              width: "100%",
              marginTop: "16px",
              padding: "13px",
              background: loading
                ? "rgba(124,58,237,0.4)"
                : "linear-gradient(135deg, #7c3aed, #4f46e5)",
              border: "none",
              borderRadius: "12px",
              color: "#fff",
              fontSize: "14.5px",
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
              fontFamily: "'Outfit', sans-serif",
              transition: "all 0.25s ease",
              boxShadow: loading ? "none" : "0 0 24px rgba(124,58,237,0.35)",
            }}
          >
            {loading ? (
              <AILoader text="Sending reset link" />
            ) : (
              "Send Reset Link →"
            )}
          </button>
        </>
      ) : (
        <div
          style={{
            textAlign: "center",
            padding: "20px 0",
            animation: "fadeScaleIn 0.4s ease forwards",
          }}
        >
          <div
            style={{
              width: "64px",
              height: "64px",
              borderRadius: "50%",
              background:
                "linear-gradient(135deg, rgba(16,185,129,0.2), rgba(5,150,105,0.2))",
              border: "1px solid rgba(16,185,129,0.4)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 16px",
              boxShadow: "0 0 30px rgba(16,185,129,0.25)",
            }}
          >
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
              <path
                d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"
                stroke="#10b981"
                strokeWidth="1.5"
              />
              <polyline
                points="22,6 12,13 2,6"
                stroke="#10b981"
                strokeWidth="1.5"
              />
              <path
                d="M9 12l2 2 4-4"
                stroke="#10b981"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{
                  strokeDasharray: 10,
                  strokeDashoffset: 10,
                  animation: "drawCheck 0.4s 0.2s ease forwards",
                }}
              />
            </svg>
          </div>
          <p
            style={{
              color: "#f0f0f8",
              fontWeight: 700,
              fontSize: "17px",
              margin: "0 0 8px 0",
            }}
          >
            Check your inbox
          </p>
          <p style={{ color: "#9898b0", fontSize: "13px", lineHeight: 1.65 }}>
            We sent a reset link to{" "}
            <span style={{ color: "#a78bfa" }}>{email}</span>.<br />
            It expires in 15 minutes.
          </p>
          <button
            onClick={onBack}
            style={{
              marginTop: "20px",
              padding: "10px 24px",
              background: "rgba(124,58,237,0.12)",
              border: "1px solid rgba(124,58,237,0.25)",
              borderRadius: "10px",
              color: "#a78bfa",
              fontSize: "13.5px",
              fontWeight: 600,
              cursor: "pointer",
              fontFamily: "'Outfit', sans-serif",
              transition: "all 0.2s",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "rgba(124,58,237,0.2)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "rgba(124,58,237,0.12)";
            }}
          >
            ← Back to login
          </button>
        </div>
      )}
    </div>
  );
};

/* ═══════════════════════════════════════════════════════
   PASSWORD TOGGLE BUTTON
═══════════════════════════════════════════════════════ */
const EyeToggle: React.FC<{ show: boolean; onToggle: () => void }> = ({
  show,
  onToggle,
}) => {
  const [pulse, setPulse] = useState(false);

  const handleClick = () => {
    setPulse(true);
    onToggle();
    setTimeout(() => setPulse(false), 400);
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      style={{
        background: "none",
        border: "none",
        cursor: "pointer",
        color: show ? "#a78bfa" : "#5a5a72",
        padding: "4px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        transition: "color 0.2s ease, transform 0.15s ease",
        transform: pulse ? "scale(0.85)" : "scale(1)",
        borderRadius: "6px",
        outline: "none",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.color = "#a78bfa")}
      onMouseLeave={(e) => !show && (e.currentTarget.style.color = "#5a5a72")}
      tabIndex={-1}
    >
      <div
        style={{
          position: "relative",
          filter: show ? "drop-shadow(0 0 6px rgba(167,139,250,0.7))" : "none",
          transition: "filter 0.2s ease",
        }}
      >
        {show ? <IconEyeOn /> : <IconEyeOff />}
      </div>
    </button>
  );
};

/* ═══════════════════════════════════════════════════════
   PASSWORD STRENGTH BAR
═══════════════════════════════════════════════════════ */
const PasswordStrengthBar: React.FC<{ password: string }> = ({ password }) => {
  const strength = getPasswordStrength(password);
  const width =
    password.length === 0 ? 0 : Math.max(10, (strength.score / 5) * 100);

  if (!password) return null;

  return (
    <div
      style={{
        marginTop: "8px",
        paddingLeft: "2px",
        animation: "slideDown 0.2s ease",
      }}
    >
      <div
        style={{
          height: "3px",
          background: "rgba(255,255,255,0.07)",
          borderRadius: "2px",
          overflow: "hidden",
          marginBottom: "5px",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${width}%`,
            background: strength.gradient,
            borderRadius: "2px",
            transition:
              "width 0.4s cubic-bezier(0.4,0,0.2,1), background 0.3s ease",
            boxShadow: `0 0 8px ${strength.color}60`,
          }}
        />
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", gap: "3px" }}>
          {[1, 2, 3, 4, 5].map((i) => (
            <div
              key={i}
              style={{
                width: "20px",
                height: "2.5px",
                borderRadius: "2px",
                background:
                  i <= strength.score
                    ? strength.gradient
                    : "rgba(255,255,255,0.07)",
                transition: "background 0.3s ease",
              }}
            />
          ))}
        </div>
        <span
          style={{
            fontSize: "11px",
            color: strength.color,
            fontWeight: 600,
            transition: "color 0.3s",
          }}
        >
          {strength.label}
        </span>
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════
   DIVIDER
═══════════════════════════════════════════════════════ */
const Divider: React.FC = () => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      gap: "12px",
      margin: "20px 0",
    }}
  >
    <div
      style={{ flex: 1, height: "1px", background: "rgba(255,255,255,0.07)" }}
    />
    <span
      style={{
        color: "#5a5a72",
        fontSize: "12px",
        fontWeight: 500,
        whiteSpace: "nowrap",
      }}
    >
      or continue with
    </span>
    <div
      style={{ flex: 1, height: "1px", background: "rgba(255,255,255,0.07)" }}
    />
  </div>
);

/* ═══════════════════════════════════════════════════════
   SOCIAL BUTTON
═══════════════════════════════════════════════════════ */
const SocialButton: React.FC<{
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
}> = ({ icon, label, onClick }) => {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "8px",
        background: hovered
          ? "rgba(255,255,255,0.07)"
          : "rgba(255,255,255,0.04)",
        border: `1px solid ${hovered ? "rgba(255,255,255,0.14)" : "rgba(255,255,255,0.09)"}`,
        borderRadius: "10px",
        padding: "10px 14px",
        color: hovered ? "#f0f0f8" : "#9898b0",
        fontSize: "13.5px",
        fontWeight: 500,
        cursor: "pointer",
        fontFamily: "'Outfit', sans-serif",
        transition: "all 0.2s ease",
        transform: hovered ? "translateY(-1px)" : "translateY(0)",
        boxShadow: hovered ? "0 4px 16px rgba(0,0,0,0.2)" : "none",
      }}
    >
      {icon}
      {label}
    </button>
  );
};

/* ═══════════════════════════════════════════════════════
   RIPPLE BUTTON
═══════════════════════════════════════════════════════ */
const RippleButton: React.FC<{
  children: React.ReactNode;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  type?: "button" | "submit" | "reset";
  style?: React.CSSProperties;
}> = ({ children, onClick, disabled, type = "submit", style }) => {
  const [ripples, setRipples] = useState<
    Array<{ id: number; x: number; y: number }>
  >([]);
  const btnRef = useRef<HTMLButtonElement>(null);
  const [hovered, setHovered] = useState(false);

  const createRipple = (e: React.MouseEvent<HTMLButtonElement>) => {
    if (!btnRef.current || disabled) return;
    const rect = btnRef.current.getBoundingClientRect();
    const id = Date.now();
    setRipples((prev) => [
      ...prev,
      { id, x: e.clientX - rect.left, y: e.clientY - rect.top },
    ]);
    setTimeout(
      () => setRipples((prev) => prev.filter((r) => r.id !== id)),
      700,
    );
    onClick?.(e);
  };

  return (
    <button
      ref={btnRef}
      type={type}
      disabled={disabled}
      onClick={createRipple}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: "relative",
        overflow: "hidden",
        width: "100%",
        padding: "13px 20px",
        background: disabled
          ? "rgba(124,58,237,0.35)"
          : "linear-gradient(135deg, #7c3aed, #4f46e5)",
        border: "none",
        borderRadius: "12px",
        color: "#fff",
        fontSize: "15px",
        fontWeight: 600,
        cursor: disabled ? "not-allowed" : "pointer",
        fontFamily: "'Outfit', sans-serif",
        transition: "all 0.25s ease",
        transform: hovered && !disabled ? "translateY(-1px)" : "translateY(0)",
        boxShadow: disabled
          ? "none"
          : hovered
            ? "0 0 40px rgba(124,58,237,0.55), 0 8px 24px rgba(0,0,0,0.3)"
            : "0 0 24px rgba(124,58,237,0.35), 0 4px 14px rgba(0,0,0,0.2)",
        letterSpacing: "0.01em",
        ...style,
      }}
    >
      {/* Shimmer sweep */}
      {hovered && !disabled && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(105deg, transparent 40%, rgba(255,255,255,0.1) 50%, transparent 60%)",
            animation: "shimmerSweep 0.55s ease",
            pointerEvents: "none",
          }}
        />
      )}

      {/* Ripples */}
      {ripples.map((r) => (
        <span
          key={r.id}
          style={{
            position: "absolute",
            left: r.x,
            top: r.y,
            width: "4px",
            height: "4px",
            borderRadius: "50%",
            background: "rgba(255,255,255,0.35)",
            transform: "translate(-50%,-50%) scale(0)",
            animation: "rippleOut 0.7s ease-out forwards",
            pointerEvents: "none",
          }}
        />
      ))}

      {children}
    </button>
  );
};

/* ═══════════════════════════════════════════════════════
   MODE TOGGLE TAB
═══════════════════════════════════════════════════════ */
const ModeToggle: React.FC<{
  mode: AuthMode;
  onChange: (m: AuthMode) => void;
  disabled?: boolean;
}> = ({ mode, onChange, disabled }) => (
  <div
    style={{
      display: "flex",
      background: "rgba(255,255,255,0.04)",
      border: "1px solid rgba(255,255,255,0.08)",
      borderRadius: "12px",
      padding: "4px",
      marginBottom: "28px",
      position: "relative",
    }}
  >
    {/* Sliding indicator */}
    <div
      style={{
        position: "absolute",
        top: "4px",
        bottom: "4px",
        left: mode === "login" ? "4px" : "calc(50% + 2px)",
        width: "calc(50% - 6px)",
        background:
          "linear-gradient(135deg, rgba(124,58,237,0.3), rgba(79,70,229,0.3))",
        border: "1px solid rgba(124,58,237,0.35)",
        borderRadius: "9px",
        transition: "left 0.3s cubic-bezier(0.4,0,0.2,1)",
        boxShadow: "0 0 16px rgba(124,58,237,0.2)",
      }}
    />
    {(["login", "signup"] as AuthMode[]).map((m) => (
      <button
        key={m}
        type="button"
        onClick={() => !disabled && onChange(m)}
        disabled={disabled}
        style={{
          flex: 1,
          padding: "9px 14px",
          background: "none",
          border: "none",
          color: mode === m ? "#c4b5fd" : "#5a5a72",
          fontWeight: mode === m ? 600 : 500,
          fontSize: "13.5px",
          cursor: disabled ? "not-allowed" : "pointer",
          transition: "color 0.25s ease",
          fontFamily: "'Outfit', sans-serif",
          position: "relative",
          zIndex: 1,
          letterSpacing: "0.01em",
        }}
      >
        {m === "login" ? "Sign In" : "Sign Up"}
      </button>
    ))}
  </div>
);

/* ═══════════════════════════════════════════════════════
   PARTICLE BG (canvas)
═══════════════════════════════════════════════════════ */
const ParticleCanvas: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    const particles: Array<{
      x: number;
      y: number;
      vx: number;
      vy: number;
      r: number;
      opacity: number;
      twinkle: number;
      ts: number;
    }> = [];

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };

    const init = () => {
      particles.length = 0;
      const n = Math.floor((canvas.width * canvas.height) / 14000);
      for (let i = 0; i < n; i++) {
        particles.push({
          x: Math.random() * canvas.width,
          y: Math.random() * canvas.height,
          vx: (Math.random() - 0.5) * 0.12,
          vy: (Math.random() - 0.5) * 0.12,
          r: Math.random() * 1.1 + 0.2,
          opacity: Math.random() * 0.5 + 0.1,
          twinkle: Math.random() * Math.PI * 2,
          ts: Math.random() * 0.02 + 0.005,
        });
      }
    };
    canvas.style.willChange = "transform";
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;
        p.twinkle += p.ts;
        if (p.x < 0) p.x = canvas.width;
        if (p.x > canvas.width) p.x = 0;
        if (p.y < 0) p.y = canvas.height;
        if (p.y > canvas.height) p.y = 0;
        const op = p.opacity * (0.6 + 0.4 * Math.sin(p.twinkle));
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(167,139,250,${op})`;
        ctx.fill();
      });
      animId = requestAnimationFrame(draw);
    };

    resize();
    init();
    draw();
    window.addEventListener("resize", () => {
      resize();
      init();
    });
    return () => {
      cancelAnimationFrame(animId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "fixed",
        inset: 0,
        width: "100vw", // ✅ ADD
        height: "100vh", // ✅ ADD
        pointerEvents: "none",
        zIndex: 0,
        opacity: 0.45,
      }}
    />
  );
};

/* ═══════════════════════════════════════════════════════
   MAIN AUTH PAGE
═══════════════════════════════════════════════════════ */
const AuthPage: React.FC = () => {
  const [mode, setMode] = useState<AuthMode>(() => {
    const modeParam = new URLSearchParams(window.location.search).get("mode");
    return modeParam === "signup" ? "signup" : "login";
  });
  const [appState, setAppState] = useState<AppState>("idle");
  const [showForgot, setShowForgot] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [errors, setErrors] = useState<FieldError>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [formData, setFormData] = useState<AuthFormData>({
    name: "",
    email: "",
    password: "",
    confirm_password: "",
  });

  const navigate = useNavigate();
  const location = useLocation();
  const { setToken } = useAuth();

  /* ── Mode switch: reset everything ── */
  const switchMode = useCallback(
    (m: AuthMode) => {
      if (appState !== "idle") return;
      setMode(m);
      setErrors({});
      setTouched({});
      setShowPassword(false);
      setShowConfirm(false);
      setFormData({ name: "", email: "", password: "", confirm_password: "" });
      navigate(`/auth?mode=${m}`, { replace: true });
    },
    [appState, navigate],
  );

  useEffect(() => {
    if (appState !== "idle") return;

    const modeParam = new URLSearchParams(location.search).get("mode");
    const nextMode: AuthMode = modeParam === "signup" ? "signup" : "login";

    if (nextMode === mode) return;

    setMode(nextMode);
    setErrors({});
    setTouched({});
    setShowPassword(false);
    setShowConfirm(false);
    setShowForgot(false);
    setFormData({ name: "", email: "", password: "", confirm_password: "" });
  }, [appState, location.search, mode]);

  /* ── Field change ── */
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (touched[name]) {
      const err = validateField(name, value, { ...formData, [name]: value });
      setErrors((prev) => ({ ...prev, [name]: err }));
    }
  };

  /* ── Field blur ── */
  const handleBlur = (e: React.FocusEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setTouched((prev) => ({ ...prev, [name]: true }));
    const err = validateField(name, value, formData);
    setErrors((prev) => ({ ...prev, [name]: err }));
  };

  /* ── Validate whole form ── */
  const validateForm = (): boolean => {
    const fields =
      mode === "signup"
        ? ["name", "email", "password", "confirm_password"]
        : ["email", "password"];
    const newErrors: FieldError = {};
    let valid = true;
    fields.forEach((f) => {
      const err = validateField(
        f,
        (formData as Record<string, string>)[f] || "",
        formData,
      );
      if (err) {
        (newErrors as Record<string, string>)[f] = err;
        valid = false;
      }
    });
    setErrors(newErrors);
    setTouched(fields.reduce((acc, f) => ({ ...acc, [f]: true }), {}));
    return valid;
  };

  /* ── Signup submit ── */
  const handleSignUpSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;
    setAppState("loading");
    try {
      const res = await fetch("http://localhost:8000/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: formData.name,
          email: formData.email,
          password: formData.password,
          confirm_password: formData.confirm_password,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setAppState("error");
        setErrors((prev) => ({
          ...prev,
          email: data.detail || "Signup failed",
        }));
        setTouched((prev) => ({ ...prev, email: true }));
        setTimeout(() => setAppState("idle"), 100);
        return;
      }
      setToken(data.token);
      setAppState("success");
      setTimeout(() => navigate("/"), 2000);
    } catch {
      setAppState("error");
      setErrors((prev) => ({
        ...prev,
        email: "Network error. Please try again.",
      }));
      setTimeout(() => setAppState("idle"), 100);
    }
  };

  /* ── Login submit ── */
  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;
    setAppState("loading");
    try {
      const res = await fetch("http://localhost:8000/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: formData.email,
          password: formData.password,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setAppState("error");
        setErrors((prev) => ({
          ...prev,
          email: data.detail || "Invalid credentials",
        }));
        setTouched((prev) => ({ ...prev, email: true }));
        setTimeout(() => setAppState("idle"), 100);
        return;
      }
      setToken(data.token);
      setAppState("success");
      setTimeout(() => navigate("/"), 2000);
    } catch {
      setAppState("error");
      setErrors((prev) => ({
        ...prev,
        email: "Network error. Please try again.",
      }));
      setTimeout(() => setAppState("idle"), 100);
    }
  };

  const isLoading = appState === "loading";
  const isSuccess = appState === "success";

  /* ═══════════════════════════════════════════════
     RENDER
  ═══════════════════════════════════════════════ */
  return (
    <>
      {/* ── Global keyframes ── */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

        @keyframes aiDot {
          0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
          40% { transform: scale(1); opacity: 1; }
        }
        @keyframes slideDown {
          from { opacity: 0; transform: translateY(-6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes slideRight {
          from { opacity: 0; transform: translateX(-14px); }
          to   { opacity: 1; transform: translateX(0); }
        }
        @keyframes fadeScaleIn {
          from { opacity: 0; transform: scale(0.92); }
          to   { opacity: 1; transform: scale(1); }
        }
        @keyframes rippleOut {
          to { transform: translate(-50%,-50%) scale(80); opacity: 0; }
        }
        @keyframes shimmerSweep {
          from { transform: translateX(-100%) skewX(-20deg); }
          to   { transform: translateX(200%) skewX(-20deg); }
        }
        @keyframes drawCheck {
          to { stroke-dashoffset: 0; }
        }
        @keyframes successPulse {
          0%, 100% { box-shadow: 0 0 40px rgba(124,58,237,0.4), 0 0 80px rgba(124,58,237,0.15); }
          50%       { box-shadow: 0 0 60px rgba(124,58,237,0.65), 0 0 120px rgba(124,58,237,0.25); }
        }
        @keyframes blobFloat1 {
          0%,100% { transform: translate(0,0) scale(1); }
          33%  { transform: translate(40px,60px) scale(1.08); }
          66%  { transform: translate(-30px,30px) scale(0.96); }
        }
        @keyframes blobFloat2 {
          0%,100% { transform: translate(0,0); }
          50%  { transform: translate(-60px,40px) scale(1.1); }
        }
        @keyframes blobFloat3 {
          0%,100% { transform: translate(0,0); }
          40%  { transform: translate(50px,-40px); }
        }
        @keyframes cardIn {
          from { opacity: 0; transform: translateY(30px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes formIn {
          from { opacity: 0; transform: translateX(16px); }
          to   { opacity: 1; transform: translateX(0); }
        }
        @keyframes logoGlow {
          0%,100% { box-shadow: 0 0 20px rgba(124,58,237,0.5), inset 0 1px 0 rgba(255,255,255,0.15); }
          50%      { box-shadow: 0 0 36px rgba(124,58,237,0.75), inset 0 1px 0 rgba(255,255,255,0.2); }
        }
        @keyframes gridMove {
          0%   { background-position: 0 0; }
          100% { background-position: 60px 60px; }
        }

        * { box-sizing: border-box; }
        html, body, #root { height: 100%; }

        .auth-input,
        .auth-input:hover,
        .auth-input:focus,
        .auth-input:active {
          background-color: transparent !important;
          color: #f0f0f8 !important;
          caret-color: #a78bfa;
          color-scheme: dark;
          appearance: none;
          -webkit-appearance: none;
        }

        .auth-input:-webkit-autofill,
        .auth-input:-webkit-autofill:hover,
        .auth-input:-webkit-autofill:focus,
        .auth-input:-webkit-autofill:active {
          -webkit-text-fill-color: #f0f0f8 !important;
          box-shadow: 0 0 0 1000px rgba(19,19,28,0.98) inset !important;
          -webkit-box-shadow: 0 0 0 1000px rgba(19,19,28,0.98) inset !important;
          transition: background-color 99999s ease-out, color 99999s ease-out;
          caret-color: #a78bfa;
        }
          /* ── Custom Scrollbar ── */

/* Chrome, Edge, Safari */
::-webkit-scrollbar {
  width: 10px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, #7c3aed, #4f46e5);
  border-radius: 10px;
  border: 2px solid transparent;
  background-clip: padding-box;
}

::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(180deg, #8b5cf6, #6366f1);
}

/* Firefox */
* {
  scrollbar-width: thin;
  scrollbar-color: #7c3aed transparent;
}
      `}</style>

      {/* ── Canvas particles ── */}
      <ParticleCanvas />

      {/* ── Animated gradient blobs ── */}
      <div
        style={{
          position: "fixed",
          inset: 0,
          overflow: "hidden",
          zIndex: 0,
        }}
      >
        <FloatBlob
          style={{
            width: "600px",
            height: "600px",
            background:
              "radial-gradient(circle, rgba(109,40,217,0.22) 0%, transparent 70%)",
            top: "-180px",
            left: "-180px",
            animation: "blobFloat1 18s ease-in-out infinite",
          }}
        />
        <FloatBlob
          style={{
            width: "500px",
            height: "500px",
            background:
              "radial-gradient(circle, rgba(79,70,229,0.18) 0%, transparent 70%)",
            top: "20%",
            right: "-150px",
            animation: "blobFloat2 22s ease-in-out infinite",
          }}
        />
        <FloatBlob
          style={{
            width: "380px",
            height: "380px",
            background:
              "radial-gradient(circle, rgba(124,58,237,0.15) 0%, transparent 70%)",
            bottom: "5%",
            left: "25%",
            animation: "blobFloat3 16s ease-in-out infinite",
          }}
        />
      </div>
      {/* ── Grid overlay ── */}
      <div
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 1,
          pointerEvents: "none",
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.016) 1px,transparent 1px), linear-gradient(90deg,rgba(255,255,255,0.016) 1px,transparent 1px)",
          backgroundSize: "60px 60px",
          maskImage:
            "radial-gradient(ellipse 80% 80% at 50% 50%,black 20%,transparent 100%)",
          animation: "gridMove 8s linear infinite",
        }}
      />

      {/* ── Noise texture ── */}
      <div
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 2,
          pointerEvents: "none",
          opacity: 0.022,
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='1'/%3E%3C/svg%3E")`,
        }}
      />

      {/* ── Page wrapper ── */}
      <a
        href="/home.html"
        aria-label="Back to main website"
        style={{
          position: "fixed",
          top: "22px",
          left: "22px",
          zIndex: 5,
          display: "inline-flex",
          alignItems: "center",
          gap: "8px",
          padding: "10px 14px",
          borderRadius: "999px",
          border: "1px solid rgba(255,255,255,0.1)",
          background: "rgba(255,255,255,0.045)",
          color: "#d8d5e8",
          textDecoration: "none",
          fontFamily: "'Outfit', sans-serif",
          fontSize: "13px",
          fontWeight: 600,
          backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)",
          boxShadow: "0 12px 32px rgba(0,0,0,0.22)",
        }}
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <line x1="19" y1="12" x2="5" y2="12" />
          <polyline points="12 19 5 12 12 5" />
        </svg>
        Back to Website
      </a>

      <div
        style={{
          minHeight: "100vh",
          background: "#080810",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "24px 16px",
          fontFamily: "'Outfit', sans-serif",
          position: "relative",
          zIndex: 3,
        }}
      >
        {/* ── Two-column layout (left brand + right card) on wide screens ── */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr) min(480px, 100%)",
            gap: "60px",
            alignItems: "center",
            maxWidth: "1100px",
            width: "100%",
            margin: "0 auto",
          }}
        >
          {/* ── LEFT BRAND PANEL (hides on small screens) ── */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "32px",
              minWidth: "300px",
            }}
          >
            {/* Logo */}
            <div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "12px",
                  marginBottom: "24px",
                }}
              >
                <div
                  style={{
                    width: "42px",
                    height: "42px",
                    borderRadius: "12px",
                    background: "linear-gradient(135deg, #7c3aed, #4f46e5)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontFamily: "'Syne', sans-serif",
                    fontSize: "0.9rem",
                    fontWeight: 800,
                    color: "#fff",
                    animation: "logoGlow 3s ease-in-out infinite",
                    position: "relative",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      position: "absolute",
                      inset: 0,
                      background:
                        "linear-gradient(135deg, rgba(255,255,255,0.15), transparent)",
                    }}
                  />
                  CX
                </div>
                <span
                  style={{
                    fontFamily: "'Syne', sans-serif",
                    fontWeight: 800,
                    fontSize: "1.4rem",
                    letterSpacing: "-0.04em",
                    color: "#f0f0f8",
                  }}
                >
                  CODEXA
                </span>
              </div>

              <h2
                style={{
                  fontFamily: "'Syne', sans-serif",
                  fontSize: "clamp(1.8rem, 3vw, 2.5rem)",
                  fontWeight: 800,
                  lineHeight: 1.1,
                  letterSpacing: "-0.04em",
                  color: "#f0f0f8",
                  margin: "0 0 14px 0",
                }}
              >
                Build complete
                <br />
                <span
                  style={{
                    background:
                      "linear-gradient(135deg, #c4b5fd 0%, #8b5cf6 40%, #818cf8 80%)",
                    WebkitBackgroundClip: "text",
                    WebkitTextFillColor: "transparent",
                    backgroundClip: "text",
                  }}
                >
                  software with AI.
                </span>
              </h2>
              <p
                style={{
                  color: "#9898b0",
                  fontSize: "0.9rem",
                  lineHeight: 1.7,
                  margin: 0,
                }}
              >
                Four specialized agents — Planner, Developer, Debugger, and Chat
                — that take your idea from concept to deployed code.
              </p>
            </div>

            {/* Feature pills */}
            {[
              {
                icon: "◆",
                label: "Planner Agent",
                sub: "Architecture generation",
              },
              {
                icon: "◈",
                label: "Developer Agent",
                sub: "Multi-file code output",
              },
              {
                icon: "◉",
                label: "Debugger Agent",
                sub: "Autonomous validation",
              },
            ].map((item, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "14px",
                  padding: "14px 18px",
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.07)",
                  borderRadius: "12px",
                  backdropFilter: "blur(10px)",
                }}
              >
                <div
                  style={{
                    width: "36px",
                    height: "36px",
                    borderRadius: "9px",
                    flexShrink: 0,
                    background: "rgba(124,58,237,0.12)",
                    border: "1px solid rgba(124,58,237,0.2)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "#a78bfa",
                    fontSize: "1rem",
                  }}
                >
                  {item.icon}
                </div>
                <div>
                  <p
                    style={{
                      color: "#f0f0f8",
                      fontSize: "13px",
                      fontWeight: 600,
                      margin: "0 0 2px 0",
                    }}
                  >
                    {item.label}
                  </p>
                  <p style={{ color: "#5a5a72", fontSize: "12px", margin: 0 }}>
                    {item.sub}
                  </p>
                </div>
                <div
                  style={{
                    marginLeft: "auto",
                    width: "6px",
                    height: "6px",
                    borderRadius: "50%",
                    background: "#10b981",
                    boxShadow: "0 0 8px rgba(16,185,129,0.7)",
                    animation: `aiDot ${1.5 + i * 0.3}s ease-in-out infinite`,
                  }}
                />
              </div>
            ))}

            {/* Trust badge */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                borderTop: "1px solid rgba(255,255,255,0.06)",
                paddingTop: "20px",
              }}
            >
              <div style={{ display: "flex" }}>
                {[
                  "#f59e0b,#ef4444",
                  "#10b981,#3b82f6",
                  "#8b5cf6,#ec4899",
                  "#06b6d4,#3b82f6",
                ].map((grad, i) => (
                  <div
                    key={i}
                    style={{
                      width: "26px",
                      height: "26px",
                      borderRadius: "50%",
                      background: `linear-gradient(135deg, ${grad})`,
                      border: "2px solid #080810",
                      marginLeft: i === 0 ? 0 : "-8px",
                    }}
                  />
                ))}
              </div>
              <p style={{ color: "#9898b0", fontSize: "12px", margin: 0 }}>
                <span style={{ color: "#f0f0f8", fontWeight: 600 }}>50K+</span>{" "}
                projects built
              </p>
            </div>
          </div>

          {/* ── RIGHT CARD ── */}
          <div
            style={{
              width: "100%",
              maxWidth: "480px",
              background: "rgba(255,255,255,0.032)",
              backdropFilter: "blur(16px) saturate(1.2)",
              WebkitBackdropFilter: "blur(28px) saturate(1.4)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "24px",
              padding: "36px 32px",
              boxShadow:
                "0 32px 80px rgba(0,0,0,0.55), 0 0 80px rgba(124,58,237,0.06), inset 0 1px 0 rgba(255,255,255,0.06)",
              position: "relative",
              overflow: "hidden",
              animation: "cardIn 0.65s cubic-bezier(0.4,0,0.2,1) forwards",
            }}
          >
            {/* Card top glow line */}
            <div
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
                height: "1px",
                background:
                  "linear-gradient(90deg, transparent, rgba(139,92,246,0.5), transparent)",
              }}
            />

            {/* Card bg accent */}
            <div
              style={{
                position: "absolute",
                top: "-60px",
                right: "-60px",
                width: "200px",
                height: "200px",
                borderRadius: "50%",
                background:
                  "radial-gradient(circle, rgba(124,58,237,0.12) 0%, transparent 70%)",
                pointerEvents: "none",
              }}
            />

            {/* ── SUCCESS STATE ── */}
            {isSuccess ? (
              <SuccessState mode={mode} />
            ) : showForgot ? (
              /* ── FORGOT PASSWORD ── */
              <ForgotPanel onBack={() => setShowForgot(false)} />
            ) : (
              /* ── MAIN FORM ── */
              <form
                onSubmit={
                  mode === "login" ? handleLoginSubmit : handleSignUpSubmit
                }
                noValidate
                style={{ animation: "formIn 0.3s ease" }}
              >
                {/* Mode toggle tabs */}
                <ModeToggle
                  mode={mode}
                  onChange={switchMode}
                  disabled={isLoading}
                />

                {/* Header */}
                <div style={{ marginBottom: "24px" }}>
                  <h2
                    style={{
                      fontFamily: "'Syne', sans-serif",
                      fontSize: "1.65rem",
                      fontWeight: 800,
                      letterSpacing: "-0.035em",
                      color: "#f0f0f8",
                      margin: "0 0 6px 0",
                    }}
                  >
                    {mode === "login" ? "Welcome back" : "Create account"}
                  </h2>
                  <p
                    style={{
                      color: "#9898b0",
                      fontSize: "13.5px",
                      margin: 0,
                      lineHeight: 1.6,
                    }}
                  >
                    {mode === "login"
                      ? "Sign in to continue building with AI."
                      : "Start building production software today."}
                  </p>
                </div>

                {/* Social buttons */}
                <div
                  style={{ display: "flex", gap: "10px", marginBottom: "4px" }}
                >
                  <SocialButton icon={<IconGoogle />} label="Google" />
                  <SocialButton icon={<IconGithub />} label="GitHub" />
                </div>

                <Divider />

                {/* Fields */}
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "12px",
                  }}
                >
                  {mode === "signup" && (
                    <FloatingInput
                      label="Full Name"
                      name="name"
                      type="text"
                      value={formData.name || ""}
                      onChange={handleChange}
                      onBlur={handleBlur}
                      error={touched.name ? errors.name : ""}
                      icon={<IconUser />}
                      autoComplete="name"
                      disabled={isLoading}
                    />
                  )}

                  <FloatingInput
                    label="Email address"
                    name="email"
                    type="email"
                    value={formData.email}
                    onChange={handleChange}
                    onBlur={handleBlur}
                    error={touched.email ? errors.email : ""}
                    icon={<IconMail />}
                    autoComplete="email"
                    disabled={isLoading}
                  />

                  <div>
                    <FloatingInput
                      label="Password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      value={formData.password}
                      onChange={handleChange}
                      onBlur={handleBlur}
                      error={touched.password ? errors.password : ""}
                      icon={<IconLock />}
                      rightElement={
                        <EyeToggle
                          show={showPassword}
                          onToggle={() => setShowPassword((v) => !v)}
                        />
                      }
                      autoComplete={
                        mode === "login" ? "current-password" : "new-password"
                      }
                      disabled={isLoading}
                    />
                    {mode === "signup" && (
                      <PasswordStrengthBar password={formData.password} />
                    )}
                  </div>

                  {mode === "signup" && (
                    <FloatingInput
                      label="Confirm Password"
                      name="confirm_password"
                      type={showConfirm ? "text" : "password"}
                      value={formData.confirm_password || ""}
                      onChange={handleChange}
                      onBlur={handleBlur}
                      error={
                        touched.confirm_password ? errors.confirm_password : ""
                      }
                      icon={<IconLock />}
                      rightElement={
                        <EyeToggle
                          show={showConfirm}
                          onToggle={() => setShowConfirm((v) => !v)}
                        />
                      }
                      autoComplete="new-password"
                      disabled={isLoading}
                    />
                  )}
                </div>

                {/* Forgot password (login only) */}
                {mode === "login" && (
                  <div style={{ textAlign: "right", margin: "10px 0 16px 0" }}>
                    <button
                      type="button"
                      onClick={() => setShowForgot(true)}
                      style={{
                        background: "none",
                        border: "none",
                        color: "#9898b0",
                        fontSize: "12.5px",
                        fontWeight: 500,
                        cursor: "pointer",
                        transition: "color 0.2s",
                        fontFamily: "'Outfit', sans-serif",
                        padding: 0,
                      }}
                      onMouseEnter={(e) =>
                        (e.currentTarget.style.color = "#a78bfa")
                      }
                      onMouseLeave={(e) =>
                        (e.currentTarget.style.color = "#9898b0")
                      }
                    >
                      Forgot password?
                    </button>
                  </div>
                )}

                {/* Submit button */}
                <div style={{ marginTop: mode === "signup" ? "20px" : "4px" }}>
                  <RippleButton disabled={isLoading} type="submit">
                    {isLoading ? (
                      <AILoader
                        text={
                          mode === "login" ? "Signing in" : "Creating account"
                        }
                      />
                    ) : (
                      <span
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          gap: "8px",
                        }}
                      >
                        {mode === "login" ? "Sign In" : "Create Account"}
                        <svg
                          width="16"
                          height="16"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <line x1="5" y1="12" x2="19" y2="12" />
                          <polyline points="12 5 19 12 12 19" />
                        </svg>
                      </span>
                    )}
                  </RippleButton>
                </div>

                {/* Terms (signup only) */}
                {mode === "signup" && (
                  <p
                    style={{
                      color: "#5a5a72",
                      fontSize: "11.5px",
                      textAlign: "center",
                      marginTop: "14px",
                      lineHeight: 1.6,
                    }}
                  >
                    By creating an account, you agree to our{" "}
                    <a
                      href="#"
                      style={{ color: "#a78bfa", textDecoration: "none" }}
                    >
                      Terms
                    </a>{" "}
                    and{" "}
                    <a
                      href="#"
                      style={{ color: "#a78bfa", textDecoration: "none" }}
                    >
                      Privacy Policy
                    </a>
                    .
                  </p>
                )}

                {/* Switch mode (mobile-style bottom link) */}
                <p
                  style={{
                    textAlign: "center",
                    marginTop: "20px",
                    color: "#5a5a72",
                    fontSize: "13px",
                    borderTop: "1px solid rgba(255,255,255,0.06)",
                    paddingTop: "18px",
                  }}
                >
                  {mode === "login"
                    ? "Don't have an account? "
                    : "Already have an account? "}
                  <button
                    type="button"
                    onClick={() =>
                      switchMode(mode === "login" ? "signup" : "login")
                    }
                    disabled={isLoading}
                    style={{
                      background: "none",
                      border: "none",
                      color: "#a78bfa",
                      fontWeight: 600,
                      fontSize: "13px",
                      cursor: "pointer",
                      fontFamily: "'Outfit', sans-serif",
                      transition: "color 0.2s",
                    }}
                    onMouseEnter={(e) =>
                      (e.currentTarget.style.color = "#c4b5fd")
                    }
                    onMouseLeave={(e) =>
                      (e.currentTarget.style.color = "#a78bfa")
                    }
                  >
                    {mode === "login" ? "Sign up free →" : "Sign in →"}
                  </button>
                </p>
              </form>
            )}
          </div>
        </div>
      </div>
    </>
  );
};

export default AuthPage;
