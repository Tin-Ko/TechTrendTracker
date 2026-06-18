import { Route, Routes } from "react-router-dom";

import ChartPage from "./pages/ChartPage";
import Home from "./pages/Home";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/chart" element={<ChartPage />} />
    </Routes>
  );
}
