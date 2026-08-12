import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { MotionConfig } from "framer-motion";
import Nav from "./components/Nav";
import RowList from "./components/RowList";
import DetailPanel from "./components/DetailPanel";
import LiquidMetalField from "./components/LiquidMetalField";
import Intro from "./components/Intro";

function BooksLayout() {
  const { name } = useParams();
  return (
    <div className="h-screen flex overflow-hidden">
      <Nav />
      <div className="flex-1 flex overflow-hidden">
        <div className="w-[30rem] border-r border-white/5 overflow-y-auto">
          <RowList selectedName={name ?? null} />
        </div>
        <main className="flex-1 p-10 overflow-y-auto">
          {name ? <DetailPanel name={name} /> : null}
        </main>
      </div>
    </div>
  );
}

// /books alone has no book selected yet -- RowList knows the default-sorted order
// (fetches it itself), so the redirect target is resolved inside RowList's own data
// rather than duplicating sort logic here. Rendering RowList with no selection lets it
// redirect once its fetch resolves.
function BooksIndexRedirect() {
  return (
    <div className="h-screen flex overflow-hidden">
      <Nav />
      <div className="w-[30rem] border-r border-white/5 overflow-y-auto">
        <RowList selectedName={null} />
      </div>
    </div>
  );
}

export default function App() {
  return (
    // reducedMotion="user" makes every motion.* component (row-select spring,
    // detail-panel entrance, range-control tap) honor prefers-reduced-motion
    // automatically -- the canvas-driven LiquidMetalField/Intro handle their own
    // reduced-motion check separately (see lib/motion.ts's prefersReducedMotion()).
    <MotionConfig reducedMotion="user">
      <LiquidMetalField />
      <Intro />
      <Routes>
        <Route path="/" element={<Navigate to="/books" replace />} />
        <Route path="/books" element={<BooksIndexRedirect />} />
        <Route path="/books/:name" element={<BooksLayout />} />
      </Routes>
    </MotionConfig>
  );
}
