import React, { useState } from "react";
import Sidebar from "../components/Sidebar/Sidebar";
import MainSection from "../components/MainSection/MainSection";
import PreviewSection from "../components/PreiviewSection/PreviewSection";
import { ChatProvider } from "../Context/ChatContext";
import "../CSS/Home.css";

const App = () => {
  const [previewSection, setpreviewSection] = useState(false);

  return (
    <ChatProvider>
      <div className={`dashboard-layout`}>
        <Sidebar />
        <MainSection
          recentProjects={[
            { id: "p1", name: "Todo App", image:"" },
            { id: "p2", name: "Weather App", preview: "" },
            {
              id: "p3",
              name: "Portfolio Website",
              image: "",
            },
          ]}
        />
        {previewSection ? <PreviewSection /> : ""}
      </div>
    </ChatProvider>
  );
};

export default App;
