import React from "react";

const ChatLoader: React.FC = () => {
  
  return (
    <div className="flex justify-center py-6">
      <div style={{ display: "flex", gap: "6px" }}>
        <style>
          {`
          @keyframes sidebarTyping {
            0%,80%,100% { transform: scale(0); opacity: 0.4 }
            40% { transform: scale(1); opacity: 1 }
          }
          `}
        </style>

        <div
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: "#94a3b8",
            animation: "sidebarTyping 1.4s infinite",
          }}
        />

        <div
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: "#94a3b8",
            animation: "sidebarTyping 1.4s infinite",
            animationDelay: "0.2s",
          }}
        />

        <div
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: "#94a3b8",
            animation: "sidebarTyping 1.4s infinite",
            animationDelay: "0.4s",
          }}
        />
      </div>
    </div>
  );
};

export default ChatLoader;
