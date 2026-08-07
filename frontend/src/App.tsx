import { useEffect, useState } from "react";
import { motion } from "framer-motion";

type Book = {
  book: string;
  equity: number;
  return: number;
  last_run: string;
  retired_at: string | null;
};

export default function App() {
  const [books, setBooks] = useState<Book[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("http://localhost:8000/api/books/summary")
      .then((res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        return res.json();
      })
      .then(setBooks)
      .catch((err) => setError(String(err)));
  }, []);

  const totalEquity = books?.reduce((sum, b) => sum + b.equity, 0) ?? 0;

  return (
    <div className="min-h-screen flex">
      <nav className="w-56 border-r border-white/5 p-6 text-sm text-ink-muted">
        <div className="text-ink font-bold mb-6">tradefabe</div>
        <div className="mb-2">Paper Books</div>
        <div>Research Lab</div>
      </nav>
      <main className="flex-1 p-10">
        {error && <p className="text-red-400">Failed to load: {error}</p>}
        {!books && !error && <p className="text-ink-muted">Loading…</p>}
        {books && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className="bg-surface rounded-card p-8 max-w-sm"
          >
            <div className="text-ink-muted text-xs uppercase tracking-wide mb-2">
              Books live
            </div>
            <div className="text-3xl font-black mb-4">{books.length}</div>
            <div className="text-ink-muted text-xs uppercase tracking-wide mb-2">
              Total equity
            </div>
            <div className="text-3xl font-black">
              ${totalEquity.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </div>
          </motion.div>
        )}
      </main>
    </div>
  );
}
