import React, { useState } from "react";
import {BrowserRouter as Router, Routes, Route} from 'react-router-dom'
import Home from './Pages/Home'
const App = () => {
  const [previewSection, setpreviewSection] = useState(false);

  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home/>}/>
      </Routes>
    </Router>
  );
};

export default App;
