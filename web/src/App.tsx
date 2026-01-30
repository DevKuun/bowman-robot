import { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { 
  LayoutDashboard, PieChart, History, Settings as SettingsIcon, 
  Menu, Clock, ChevronLeft, ChevronRight
} from 'lucide-react';
import { Dashboard } from './pages/Dashboard';
import { Portfolio } from './pages/Portfolio';
import { Trades } from './pages/Trades';
import { Sessions } from './pages/Sessions';
import { Settings } from './pages/Settings';
import { YachtLogo } from './components/YachtLogo';
import { RealtimeProvider, useRealtime } from './contexts/RealtimeContext';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

type Page = 'dashboard' | 'portfolio' | 'trades' | 'sessions' | 'settings';

// Component to update document title based on bot status
function DocumentTitle() {
  const { status } = useRealtime();
  
  useEffect(() => {
    if (status?.running && status.total_value !== undefined) {
      const totalValue = status.total_value;
      const pnl = status.current_pnl ?? 0;
      const pnlPercent = status.current_pnl_percent ?? 0;
      
      const formatWithCommas = (v: number) => {
        return Math.round(v).toLocaleString('ko-KR');
      };
      
      const pnlSign = pnl >= 0 ? '+' : '';
      const pnlPercentSign = pnlPercent >= 0 ? '+' : '';
      
      document.title = `${formatWithCommas(totalValue)} | ${pnlSign}${formatWithCommas(pnl)} (${pnlPercentSign}${pnlPercent.toFixed(2)}%) | Bowman`;
    } else {
      document.title = 'Bowman Trading Bot';
    }
    
    return () => {
      document.title = 'Bowman Trading Bot';
    };
  }, [status]);
  
  return null;
}

const navItems: { id: Page; label: string; icon: React.ReactNode }[] = [
  { id: 'dashboard', label: '대시보드', icon: <LayoutDashboard className="w-5 h-5" /> },
  { id: 'portfolio', label: '포트폴리오', icon: <PieChart className="w-5 h-5" /> },
  { id: 'trades', label: '거래 내역', icon: <History className="w-5 h-5" /> },
  { id: 'sessions', label: '세션 히스토리', icon: <Clock className="w-5 h-5" /> },
  { id: 'settings', label: '설정', icon: <SettingsIcon className="w-5 h-5" /> },
];

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false); // Mobile
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    // Load from localStorage
    const saved = localStorage.getItem('sidebarCollapsed');
    return saved ? JSON.parse(saved) : false;
  });

  // Save collapsed state to localStorage
  useEffect(() => {
    localStorage.setItem('sidebarCollapsed', JSON.stringify(sidebarCollapsed));
  }, [sidebarCollapsed]);

  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard':
        return <Dashboard />;
      case 'portfolio':
        return <Portfolio />;
      case 'trades':
        return <Trades />;
      case 'sessions':
        return <Sessions />;
      case 'settings':
        return <Settings />;
      default:
        return <Dashboard />;
    }
  };

  return (
    <QueryClientProvider client={queryClient}>
      <RealtimeProvider>
      <DocumentTitle />
      <div className="min-h-screen flex">
        {/* Mobile overlay */}
        {sidebarOpen && (
          <div 
            className="fixed inset-0 bg-black/20 backdrop-blur-sm z-20 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* Sidebar */}
        <aside className={`
          fixed lg:static inset-y-0 left-0 z-30
          bg-white/80 backdrop-blur-xl border-r border-gray-200/50
          transform transition-all duration-300 ease-out
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
          ${sidebarCollapsed ? 'lg:w-20' : 'w-64'}
        `}>
          {/* Header */}
          <div className={`
            flex items-center border-b border-gray-100 relative
            ${sidebarCollapsed ? 'justify-center px-2 py-6' : 'gap-3 px-6 py-6'}
          `}>
            <YachtLogo size={sidebarCollapsed ? "sm" : "md"} />
            {!sidebarCollapsed && (
              <div>
                <h1 className="font-bold text-gray-900 text-lg">Bowman</h1>
                <p className="text-xs text-gray-400">Trading Bot</p>
              </div>
            )}
            
            {/* Collapse toggle button - Desktop only */}
            <button
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              className={`
                hidden lg:flex absolute -right-3 top-1/2 -translate-y-1/2
                w-6 h-6 items-center justify-center
                bg-white border border-gray-200 rounded-full shadow-sm
                text-gray-400 hover:text-gray-600 hover:bg-gray-50
                transition-colors
              `}
              title={sidebarCollapsed ? '사이드바 펼치기' : '사이드바 접기'}
            >
              {sidebarCollapsed ? (
                <ChevronRight className="w-4 h-4" />
              ) : (
                <ChevronLeft className="w-4 h-4" />
              )}
            </button>
          </div>

          <nav className={`space-y-1 ${sidebarCollapsed ? 'p-2' : 'p-4'}`}>
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => {
                  setCurrentPage(item.id);
                  setSidebarOpen(false);
                }}
                title={sidebarCollapsed ? item.label : undefined}
                className={`
                  w-full flex items-center rounded-xl
                  transition-all duration-200
                  ${sidebarCollapsed 
                    ? 'justify-center px-2 py-3' 
                    : 'gap-3 px-4 py-3'
                  }
                  ${currentPage === item.id
                    ? 'bg-gradient-to-r from-blue-500 to-blue-600 text-white shadow-md shadow-blue-500/25'
                    : 'text-gray-600 hover:bg-gray-100/80'
                  }
                `}
              >
                {item.icon}
                {!sidebarCollapsed && (
                  <span className="font-medium">{item.label}</span>
                )}
              </button>
            ))}
          </nav>

          {/* Bottom info */}
          <div className={`
            absolute bottom-0 left-0 right-0 border-t border-gray-100
            ${sidebarCollapsed ? 'p-2' : 'p-4'}
          `}>
            <div className="text-center">
              <p className="text-xs text-gray-400">v1.0.0</p>
              {!sidebarCollapsed && (
                <p className="text-xs text-gray-300 mt-1">KST 기준</p>
              )}
            </div>
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 min-w-0">
          {/* Mobile header */}
          <header className="lg:hidden bg-white/80 backdrop-blur-xl border-b border-gray-200/50 px-4 py-4 flex items-center gap-4 sticky top-0 z-10">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-2 -ml-2 text-gray-600 hover:bg-gray-100 rounded-xl transition-colors"
            >
              <Menu className="w-6 h-6" />
            </button>
            <div className="flex items-center gap-2">
              <YachtLogo size="sm" />
              <h1 className="font-bold text-gray-900">Bowman</h1>
            </div>
          </header>

          {/* Page content */}
          <div className="p-4 lg:p-8">
            {renderPage()}
          </div>
        </main>
      </div>
      </RealtimeProvider>
    </QueryClientProvider>
  );
}

export default App;
