import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { LangProvider } from "@/context/LangContext";
import Landing from "@/pages/Landing";
import Briefing from "@/pages/Briefing";
import Simulation from "@/pages/Simulation";
import Debrief from "@/pages/Debrief";
import Demo from "@/pages/Demo";

function App() {
  return (
    <LangProvider>
      <Toaster position="top-center" richColors />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/briefing/:caseId" element={<Briefing />} />
          <Route path="/sim/:sid" element={<Simulation />} />
          <Route path="/debrief/:sid" element={<Debrief />} />
          <Route path="/demo" element={<Demo />} />
        </Routes>
      </BrowserRouter>
    </LangProvider>
  );
}

export default App;
