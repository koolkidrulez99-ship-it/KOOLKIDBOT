import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { HubProvider } from './context/HubContext';
import Shell from './layout/Shell';
import DashboardHome from './pages/DashboardHome';
import DerivPage from './pages/DerivPage';
import OverviewPage from './pages/OverviewPage';
import AccountsPage from './pages/AccountsPage';
import BotLibraryPage from './pages/BotLibraryPage';
import BotPerformancePage from './pages/BotPerformancePage';
import RunningBotsPage from './pages/RunningBotsPage';
import ChartsPage from './pages/ChartsPage';
import PositionsPage from './pages/PositionsPage';
import HistoryPage from './pages/HistoryPage';
import ManualTradePage from './pages/ManualTradePage';
import RiskCenterPage from './pages/RiskCenterPage';
import AIPage from './pages/AIPage';
import SettingsPage from './pages/SettingsPage';
import CopyTradingPage from './pages/CopyTradingPage';
import JournalPage from './pages/JournalPage';
import { routerBase } from './config/runtime';
import HubAuthGate from './components/HubAuthGate';

export default function App() {
  return (
    <HubAuthGate>
      <HubProvider>
        <BrowserRouter basename={routerBase || undefined}>
        <Routes>
          <Route element={<Shell />}>
            <Route path="/" element={<DashboardHome />} />
            <Route path="/deriv" element={<DerivPage />} />
            <Route path="/mt5" element={<OverviewPage />} />
            <Route path="/mt5/accounts" element={<AccountsPage />} />
            <Route path="/mt5/bots" element={<BotLibraryPage />} />
            <Route path="/mt5/bots/:id" element={<BotPerformancePage />} />
            <Route path="/mt5/running" element={<RunningBotsPage />} />
            <Route path="/mt5/charts" element={<ChartsPage />} />
            <Route path="/mt5/positions" element={<PositionsPage />} />
            <Route path="/mt5/history" element={<HistoryPage />} />
            <Route path="/mt5/manual" element={<ManualTradePage />} />
            <Route path="/mt5/risk" element={<RiskCenterPage />} />
            <Route path="/mt5/ai" element={<AIPage />} />
            <Route path="/mt5/copy" element={<CopyTradingPage />} />
            <Route path="/mt5/journal" element={<JournalPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<OverviewPage />} />
          </Route>
        </Routes>
        </BrowserRouter>
      </HubProvider>
    </HubAuthGate>
  );
}
