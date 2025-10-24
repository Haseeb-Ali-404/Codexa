import React, { useState, useEffect, useRef, useContext } from "react";
import { FiSend } from "react-icons/fi";
import { ChatContext } from "../../Context/ChatContext";
import RecentProjects from "../RecentProjects/RecentProjects";

const MainSection = ({ recentProjects = [] }) => {
  const [input, setInput] = useState("");
  const chatEndRef = useRef(null);

  const { activeProject, addChat, getActiveChats } = useContext(ChatContext);
  const chats = getActiveChats();

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chats]);

  const handleSend = () => {
    const content = input.trim();
    if (!content) return;
    addChat(activeProject.id, { sender: "user", content });
    setInput("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="main-section">
      <div className="RecentsProjects">
        <p>RECENT  PROJECTS</p>
        <RecentProjects projects={recentProjects} />
      </div>
      <div className="chat-window">
        {chats.length === 0 ? (
          <div className="empty-chat-placeholder">
            <p>Hi! I'm Codexa.</p>
            <p>Ask me to generate, fix, or explain code.</p>
          </div>
        ) : (
          chats.map((chat) => (
            <div
              key={chat.id}
              className={`chat-message ${
                chat.sender === "user" ? "user" : "bot"
              }`}
            >
              <div className="message-content">
                {chat.content.split("\n").map((line, i) => (
                  <span key={i}>
                    {line}
                    <br />
                  </span>
                ))}
              </div>
            </div>
          ))
        )}
        <div ref={chatEndRef} />
      </div>

      <div className="input-section">
        <input
          type="text"
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask Codexa to generate, fix, or explain code..."
        />
        <button className="send-button" onClick={handleSend}>
          <FiSend />
        </button>
      </div>
    </div>
  );
};

export default MainSection;
