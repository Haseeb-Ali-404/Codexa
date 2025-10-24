import React, { createContext, useState } from "react";

export const ChatContext = createContext();

export const ChatProvider = ({ children }) => {
  const [projects, setProjects] = useState([
    { id: "1", name: "Python Project" },
    { id: "2", name: "React App" },
    { id: "3", name: "Node API" },
  ]);

  const [activeProject, setActiveProject] = useState(projects[0]);

  const [chats, setChats] = useState([
    {
      id: "1",
      projectId: "1",
      sender: "bot",
      content: "Hi! I'm Codexa. Ask me to generate, fix, or explain code.",
    },
  ]);

  const addChat = (projectId, message) => {
    const newMessage = {
      id: Date.now().toString(),
      projectId,
      ...message,
    };
    setChats((prev) => [...prev, newMessage]);
  };

  const getActiveChats = () =>
    chats.filter((chat) => chat.projectId === activeProject.id);

  return (
    <ChatContext.Provider
      value={{
        projects,
        activeProject,
        setActiveProject,
        chats,
        addChat,
        getActiveChats,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
};
