import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { LangProvider } from "@/context/LangContext";
import { AuthProvider } from "@/context/AuthContext";
import Landing from "@/pages/Landing";
import Topic from "@/pages/Topic";
import Briefing from "@/pages/Briefing";
import Simulation from "@/pages/Simulation";
import Debrief from "@/pages/Debrief";
import Demo from "@/pages/Demo";
import Pricing from "@/pages/Pricing";
import Account from "@/pages/Account";
import Legal from "@/pages/Legal";

function App() {
  return (
    <LangProvider>
      <Toaster position="top-center" richColors />
      <BrowserRouter>
        <AuthProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/topic/:topicId" element={<Topic />} />
          <Route path="/briefing/:caseId" element={<Briefing />} />
          <Route path="/sim/:sid" element={<Simulation />} />
          <Route path="/debrief/:sid" element={<Debrief />} />
          <Route path="/demo" element={<Demo />} />
          <Route path="/pricing" element={<Pricing />} />
          <Route path="/account" element={<Account />} />
          <Route path="/legal/:doc" element={<Legal />} />
        </Routes>
        </AuthProvider>
      </BrowserRouter>
    </LangProvider>
  );
}

export default App;
