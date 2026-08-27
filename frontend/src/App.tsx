import { Navigate, Route, Routes } from "react-router-dom";
import { ConsumeMagicLink } from "./pages/ConsumeMagicLink";
import { RequestLink } from "./pages/RequestLink";
import { ScanScreen } from "./pages/ScanScreen";
import { loadVolunteerSession } from "./auth/session";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={loadVolunteerSession() ? <Navigate to="/scan" replace /> : <RequestLink />} />
      <Route path="/auth/consume" element={<ConsumeMagicLink />} />
      <Route path="/scan" element={<ScanScreen />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
