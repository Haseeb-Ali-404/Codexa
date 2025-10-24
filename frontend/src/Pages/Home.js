import MainSection from "../COMPONENTS/MainSection";
import PreviewSection from "../COMPONENTS/PreviewSection";
import Sidebar from "../COMPONENTS/SideBar";
import '../CSS/Home.css'
import React, {useState} from "react";
const Home = () =>{
    const [previewActive, setpreviewActive] = useState(false)
    return(
        <>
            <div className="HomePage">
                <div className="SideBar">
                    <Sidebar/>
                </div>
                <div className="Preview">
                    {previewActive?<PreviewSection />:""}
                </div>
                <div className="MainSection">
                    <MainSection/>
                </div>
            </div>

        </>
    )
}


export default Home;