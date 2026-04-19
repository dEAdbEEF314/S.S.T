import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { 
  LayoutDashboard, 
  Activity, 
  MessageSquare, 
  Archive, 
  ClipboardCheck,
  Settings
} from 'lucide-react';
import { cn } from '@/lib/utils';

// Pages
import DashboardPage from '@/pages/Dashboard';
import PipelinePage from '@/pages/Pipeline';
import LLMLogsPage from '@/pages/LLMLogs';
import ArchivePage from '@/pages/Archive';
import ReviewPage from '@/pages/Review';

const queryClient = new QueryClient();

import { LucideIcon } from 'lucide-react';

// ... (other imports)

function SidebarItem({ to, icon: Icon, children }: { to: string, icon: LucideIcon, children: React.ReactNode }) {
  const location = useLocation();
  const isActive = location.pathname === to;
  
  return (
    <Link to={to} className={cn(
      "flex items-center gap-3 px-3 py-2 rounded-lg transition-all",
      isActive 
        ? "text-slate-100 bg-slate-800 shadow-sm border border-slate-700" 
        : "text-slate-400 hover:text-slate-100 hover:bg-slate-800/50"
    )}>
      <Icon size={20} />
      <span className="text-sm font-medium">{children}</span>
    </Link>
  );
}

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-slate-950 text-slate-100 font-sans overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 border-r border-slate-800 p-4 flex flex-col gap-6 bg-slate-900/20">
        <div className="px-3 flex items-center gap-2 mb-2">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center font-bold text-white shadow-lg shadow-blue-900/20">S</div>
          <div className="flex flex-col">
            <h1 className="text-sm font-bold tracking-tight leading-none">S.S.T</h1>
            <span className="text-[10px] text-slate-500 font-mono">DISTRIBUTED</span>
          </div>
        </div>
        
        <nav className="flex flex-col gap-1.5 flex-1">
          <div className="text-[10px] uppercase tracking-widest text-slate-600 font-bold px-3 mb-1">Monitoring</div>
          <SidebarItem to="/" icon={LayoutDashboard}>Dashboard</SidebarItem>
          <SidebarItem to="/pipeline" icon={Activity}>Pipeline</SidebarItem>
          
          <div className="text-[10px] uppercase tracking-widest text-slate-600 font-bold px-3 mt-4 mb-1">Logs & Data</div>
          <SidebarItem to="/llm-logs" icon={MessageSquare}>LLM Logs</SidebarItem>
          <SidebarItem to="/archive" icon={Archive}>Archive</SidebarItem>
          <SidebarItem to="/review" icon={ClipboardCheck}>Review</SidebarItem>
        </nav>

        <div className="pt-4 border-t border-slate-800">
          <SidebarItem to="/settings" icon={Settings}>Settings</SidebarItem>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="h-14 border-b border-slate-800 flex items-center justify-between px-8 bg-slate-950/50 backdrop-blur-md z-10">
          <h2 className="text-xs font-bold text-slate-500 uppercase tracking-widest">System Overview</h2>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
              <span className="text-[10px] font-bold text-slate-400">NODE-PROD-01</span>
            </div>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900/20 via-slate-950 to-slate-950 p-8">
          {children}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/pipeline" element={<PipelinePage />} />
            <Route path="/llm-logs" element={<LLMLogsPage />} />
            <Route path="/archive" element={<ArchivePage />} />
            <Route path="/review" element={<ReviewPage />} />
            <Route path="/settings" element={<div className="text-slate-500 italic text-sm">System configuration pending</div>} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
