import { Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { CallsPage } from "./pages/CallsPage";
import { ConfirmPage } from "./pages/ConfirmPage";
import { HomePage } from "./pages/HomePage";
import { IntakePage } from "./pages/IntakePage";
import { ReportPage } from "./pages/ReportPage";

export function AppRoutes() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/intake" element={<IntakePage />} />
        <Route path="/confirm/:jobId" element={<ConfirmPage />} />
        <Route path="/calls/:jobId" element={<CallsPage />} />
        <Route path="/report/:jobId" element={<ReportPage />} />
      </Routes>
    </Layout>
  );
}
