import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import LeadDiscovery from "./pages/LeadDiscovery";
import LeadDatabase from "./pages/LeadDatabase";
import LeadDetail from "./pages/LeadDetail";
import OutreachCenter from "./pages/OutreachCenter";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="discover" element={<LeadDiscovery />} />
          <Route path="leads" element={<LeadDatabase />} />
          <Route path="leads/:id" element={<LeadDetail />} />
          <Route path="outreach" element={<OutreachCenter />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
