import React, { useContext } from "react";
import { ChatContext } from "../../Context/ChatContext";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vs } from "react-syntax-highlighter/dist/esm/styles/prism";
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

const PreviewSection = () => {
  const { getActiveChats } = useContext(ChatContext);
  const chats = getActiveChats();

  const lastUserMessage = [...chats].reverse().find((c) => c.sender === "user");

  return (
    <div className="preview-section">
      <div className="preview-header">
        <h3>Code Preview</h3>
      </div>
      <div className="preview-content">
        {lastUserMessage ? (
          <SyntaxHighlighter
            language="javascript"
            style={document.body.classList.contains("light-theme") ? vs : vscDarkPlus}
            showLineNumbers
            wrapLines
          >
            {lastUserMessage.content}
          </SyntaxHighlighter>
        ) : (
          <div className="empty-preview-placeholder">
            <p>No code preview yet.</p>
            <p>Send a message to see generated code.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default PreviewSection;
