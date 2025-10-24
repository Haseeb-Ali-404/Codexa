import React, { useContext } from "react";
import { FiPlus, FiUser } from "react-icons/fi";
import { ChatContext } from "../../Context/ChatContext";
import ChatItem from "../ChatItem/ChatItem";

const Sidebar = () => {
  const { projects, activeProject, setActiveProject } = useContext(ChatContext);

  const handleProfileClick = () => {
    // TODO: Add profile or signup logic here
    alert("Profile / Signup Clicked!");
  };

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h2 className="logo-text">CODEXA</h2>
        <button
          className="profile-btn"
          onClick={handleProfileClick}
          title="Profile / Signup"
        >
          <FiUser />
        </button>
      </div>

      <div className="new-chat-btn-wrapper">
        <button className="new-chat-btn">
          <FiPlus /> New Chat
        </button>
      </div>

      <div className="chat-history-container">
        {projects.map((project) => (
          <ChatItem
            key={project.id}
            title={project.name}
            active={activeProject?.id === project.id}
            onClick={() => setActiveProject(project)}
          />
        ))}
      </div>

      <div className="sidebar-footer">© 2025 Codexa</div>
    </div>
  );
};

export default Sidebar;
